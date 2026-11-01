# -*- coding: utf-8 -*-
"""逐镜画面唯一性闸门（2026-11-01 立，对应自检清单第 28 条）。

为什么不能只靠 dup_shot_check.py：
  那个脚本比的是**文件**（同路径 / 同 md5 / 文件名同系列），跨目录的两张不同图
  哪怕构图动作几乎一样，它也判 ✅。本脚本比的是**画面本身**：按 shot_bounds 逐镜
  中点抽帧 → 64×36 灰度 → 去均值归一化 → 两两算空间相关（Pearson）。

判据（两条都要过）：
  ① 任意两镜  相关 < --fail   （默认 0.90）
  ② 相邻两镜  相关 < --adjacent（默认 0.85）  ← 灿爹 2026-11-01 加严：相邻不许同图

⚠️ 直方图相关不能用来判这个：两个不同的暗场镜可能给出 1.00。必须用空间相关。

⚠️ 本脚本只抓「几乎是同一张图」。**同动作不同图**（两张不同的"指着黑板"）
   相关通常只有 0.6~0.7，脚本放行 —— 必须靠抽帧拼版人眼看（清单 28b）。

用法：
    python shot_uniqueness_check.py --final 成片.mp4 --bounds 工程/audio/shot_bounds.json
    # 片头被卷播盖住的镜对只告警不判废（卷播期间观众看不到这两镜）
    python shot_uniqueness_check.py --final 成片.mp4 --bounds b.json --banner-until 4.13

退出码：有 FAIL → 1；只有 WARN → 0。
"""
import argparse
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

W, H = 64, 36          # 16:9 小图，够判构图又不怕编码噪声
PROBE_WARN = 0.50      # 低于此值不打印，免得刷屏


def find_ffmpeg():
    for p in ("/Users/mac/.local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(p):
            return p
    w = shutil.which("ffmpeg")
    if w:
        return w
    sys.exit("❌ 找不到 ffmpeg")


def grab(ff, video, t, out):
    subprocess.run(
        [ff, "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
         "-vf", f"scale={W}:{H}:flags=area", out],
        capture_output=True,
    )
    if not os.path.isfile(out):
        return None
    return np.asarray(Image.open(out).convert("L")).astype(float).ravel()


def load_bounds(path):
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, dict):
        for k in ("bounds", "shots", "shot_bounds"):
            if k in d:
                d = d[k]
                break
    return [(float(a), float(b)) for a, b in d]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", required=True, help="成片 mp4")
    ap.add_argument("--bounds", required=True, help="shot_bounds.json（list of [start,end]）")
    ap.add_argument("--offset", type=float, default=0.5,
                    help="取样点 = 镜中点 + offset，避开镜首转场（默认 0.5s）")
    ap.add_argument("--fail", type=float, default=0.90, help="任意两镜上限（默认 0.90）")
    ap.add_argument("--adjacent", type=float, default=0.85, help="相邻两镜上限（默认 0.85）")
    ap.add_argument("--banner-until", type=float, default=0.0,
                    help="卷播持续到的时刻；该时刻之前结束的镜对只告警")
    ap.add_argument("--keep", action="store_true", help="保留抽出的帧（调试用）")
    a = ap.parse_args()

    ff = find_ffmpeg()
    bounds = load_bounds(a.bounds)
    n = len(bounds)
    if n < 2:
        sys.exit("❌ 镜数 < 2，没什么可比的")

    # 整段落在卷播内的镜：抽到的是卷播画面，比它没有意义 → 排除
    muted = [i for i, (s, e) in enumerate(bounds) if a.banner_until > 0 and e <= a.banner_until]
    active = [i for i in range(n) if i not in muted]

    tmpd = tempfile.mkdtemp(prefix="uniq_")
    vecs, picks = {}, {}
    for i in active:
        s, e = bounds[i]
        t = (s + e) / 2.0 + a.offset
        lo, hi = s + 0.15, e - 0.15
        if hi > lo:
            t = min(max(t, lo), hi)
        p = os.path.join(tmpd, f"f{i}.png")
        v = grab(ff, a.final, max(t, 0.0), p)
        if v is None:
            sys.exit(f"❌ 镜{i + 1} 抽帧失败 @ {t:.2f}s")
        v = (v - v.mean()) / (v.std() + 1e-9)
        vecs[i], picks[i] = v, t

    print("=" * 72)
    print("逐镜画面唯一性闸门  shot_uniqueness_check")
    print("=" * 72)
    print(f"成片 {os.path.basename(a.final)} ｜ {n} 镜 ｜ 判据：任意 <{a.fail:.2f} 且相邻 <{a.adjacent:.2f}")
    print("取样点：" + "  ".join(f"镜{i + 1}@{picks[i]:.2f}s" for i in active))
    if muted:
        names = "、".join(f"镜{i + 1}" for i in muted)
        print(f"⏭  跳过 {names}：整段在片头卷播（0~{a.banner_until:.2f}s）内，抽到的是卷播画面")
        print("   这几镜的素材重复问题**只有换开头才看得见**，换开头时必须重跑本闸门")

    fails, shown = [], []
    for i, j in itertools.combinations(active, 2):
        c = float(np.dot(vecs[i], vecs[j]) / len(vecs[i]))
        if c < PROBE_WARN:
            continue
        adj = (j - i == 1)
        lim = a.adjacent if adj else a.fail
        shown.append((c, i + 1, j + 1, adj, c >= lim))
        if c >= lim:
            fails.append((c, i + 1, j + 1, adj))

    if shown:
        print(f"\n{'相关':>5}  {'镜对':<10}{'相邻':<6}{'判定'}")
        for c, i, j, adj, bad in sorted(shown, reverse=True):
            print(f"{c:5.2f}  镜{i} vs 镜{j:<3}{'是' if adj else '否':<6}"
                  f"{'❌ FAIL' if bad else '✅ 过'}")

    print("\n" + "-" * 72)
    if fails:
        for c, i, j, adj in fails:
            kind = "相邻" if adj else "任意"
            print(f"❌ 镜{i} 与 镜{j}（{kind}）相关 {c:.2f} ≥ 阈值 —— 观众会看成同一镜")
        print(f"❌ FAIL {len(fails)} 处")
        print("   改法：换掉其中一镜的画面/构图/主体朝向，别只改文件名。")
        rc = 1
    else:
        worst = max(shown)[0] if shown else 0.0
        print(f"✅ PASS ｜ 最像一对 {worst:.2f}")
        rc = 0

    if not a.keep:
        for f in os.listdir(tmpd):
            try:
                os.remove(os.path.join(tmpd, f))
            except OSError:
                pass
        try:
            os.rmdir(tmpd)
        except OSError:
            pass
    else:
        print(f"（帧保留在 {tmpd}）")
    return rc


if __name__ == "__main__":
    sys.exit(main())
