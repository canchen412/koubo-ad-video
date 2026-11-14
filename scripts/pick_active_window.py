#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pick_active_window.py — 短镜取素材「活跃段」，而不是从第 0 秒硬截。

背景（2026-11-13 老板反馈）：
  「前面的视频很短，但是那句话还没说完这个视频就放完了，最后一帧一直在那里杵着」
  实测三条片逐帧差分后确认，真冻帧只占 1.9%，真正致命的另有其因：
  **短镜都从素材 ss=0 起播，而 AI 生成的 2 秒片段开头 0.3~0.5s 往往是「起手静止」**
  （人还没动 / 镜头还没推）。0.99s 的镜把这一截全吃进去 ⇒ 整镜帧差分只有 0.07，等于静帧。

  解法：镜长确定后，在素材上滑窗找「帧间运动量最高的 N 秒」，把起点写进 shot_map 的 ss。
  素材本身短、或整段都在动时，ss 自然回到 0，不会画蛇添足。

用法
----
  # 给一个 0.99s 的镜挑起点
  python3 pick_active_window.py --src 素材.mp4 --need 0.99

  # 机器读（给 shot_fit_audit.py / 自己写 shot_map 用）
  python3 pick_active_window.py --src 素材.mp4 --need 0.99 --json

  # 只看运动曲线，不挑窗
  python3 pick_active_window.py --src 素材.mp4 --curve

退出码：0 正常 ｜ 2 输入/环境问题
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np

THUMB_W, THUMB_H = 160, 90      # 缩略尺寸：差分在这个尺度上最稳，也不吃内存
LOW_MOTION = 0.8                # 平均差分低于此值视为「整段几乎不动」，提示换素材


def ff(path=None):
    return (os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
            or ("/Users/yourname/.local/bin/ffmpeg" if os.path.exists("/Users/yourname/.local/bin/ffmpeg") else "ffmpeg"))


def probe_fps(path):
    fp = os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"
    o = subprocess.run([fp, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=r_frame_rate:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    if o.returncode != 0:
        return 30.0, 0.0
    d = json.loads(o.stdout)
    st = (d.get("streams") or [{}])[0]
    num, den = (st.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    dur = float((d.get("format") or {}).get("duration") or 0)
    return (fps if fps > 0 else 30.0), dur


def motion_curve(path, w=THUMB_W, h=THUMB_H):
    """逐帧帧间平均绝对差（灰度、缩略图）。返回 (diff_array, fps, dur, 帧数)"""
    fps, dur = probe_fps(path)
    p = subprocess.run([ff(), "-v", "error", "-i", path,
                        "-vf", f"scale={w}:{h}", "-pix_fmt", "gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    if p.returncode != 0 or not p.stdout:
        print(f"[FAIL] 解帧失败：{path}", file=sys.stderr)
        sys.exit(2)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(a) // (w * h)
    if n < 2:
        return np.zeros(0, dtype=np.float32), fps, dur, n
    fr = a[:n * w * h].reshape(n, h, w).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    return d, (n / dur if dur > 0 else fps), dur, n


def best_window(d, fps, need):
    """在差分曲线上滑窗，返回 (起点秒, 窗口平均差分)。d[i] = 帧 i→i+1 的差分。"""
    if len(d) == 0:
        return 0.0, 0.0
    k = max(1, int(round(need * fps)))
    if k >= len(d):
        return 0.0, float(d.mean())
    c = np.convolve(d, np.ones(k) / k, mode="valid")
    i = int(np.argmax(c))
    return i / fps, float(c[i])


def main():
    ap = argparse.ArgumentParser(description="短镜取素材活跃段（避开 AI 素材起手静止）")
    ap.add_argument("--src", required=True)
    ap.add_argument("--need", type=float, required=True, help="需要的镜长（秒）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（机器读）")
    ap.add_argument("--curve", action="store_true", help="打印逐 0.5s 运动曲线后退出")
    ap.add_argument("--max-head", type=float, default=None,
                    help="限制起点上限（秒）；默认不限制，仅在素材足够长时生效")
    a = ap.parse_args()

    if not os.path.isfile(a.src):
        print(f"[FAIL] 文件不存在：{a.src}", file=sys.stderr)
        sys.exit(2)

    d, fps, dur, n = motion_curve(a.src)
    if len(d) == 0:
        out = {"src": a.src, "need": a.need, "ss": 0.0, "dur": dur,
               "motion": 0.0, "level": "flat", "note": "帧数不足，按 0 起播"}
        print(json.dumps(out, ensure_ascii=False) if a.json else out["note"])
        return

    if a.curve:
        print(f"{os.path.basename(a.src)}  {dur:.2f}s / {n} 帧 / {fps:.1f}fps")
        step = 0.5
        for t in np.arange(0, dur - 1e-6, step):
            i0, i1 = int(t * fps), min(int((t + step) * fps), len(d))
            if i1 <= i0:
                continue
            bar = "#" * int(min(d[i0:i1].mean(), 12) * 2)
            print(f"  {t:5.2f}s  {d[i0:i1].mean():5.2f}  {bar}")
        return

    ss, mo = best_window(d, fps, a.need)
    if a.max_head is not None:
        ss = min(ss, max(0.0, a.max_head))
    ss = round(max(0.0, min(ss, max(0.0, dur - a.need))), 3)

    whole = float(d.mean())
    if whole < LOW_MOTION:
        level = "flat"
        note = "整段几乎不动 ⇒ 建议换素材或改用静图"
    elif ss > 0.05:
        level = "active"
        note = f"跳过开头 {ss:.2f}s 静止，取第 {ss:.2f}s 起"
    else:
        level = "ok"
        note = "从头就在动，ss=0"

    out = {"src": a.src, "need": a.need, "ss": ss, "dur": round(dur, 3),
           "motion": round(mo, 3), "whole_motion": round(whole, 3),
           "level": level, "note": note}

    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"{os.path.basename(a.src)}")
        print(f"  素材 {dur:.2f}s / 需要 {a.need:.2f}s / 全段运动 {whole:.2f}")
        print(f"  ⇒ 建议 ss={ss:.2f}s（该窗口运动 {mo:.2f}）　{note}")
    return


if __name__ == "__main__":
    main()
