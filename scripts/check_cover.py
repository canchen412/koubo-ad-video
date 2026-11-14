#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_cover.py — 封面帧硬闸门（2026-11-04 建，对应 SKILL #256/#259）

为什么需要它：2026-11-04 诺特烟酰胺三版出片时，配置里写了 "cover": false，
日志那句「卷播片不贴静态封面」看着像正常行为，其实是**校验被自己关掉了**，
第 0 帧成了卷播卡片墙，平台按 3:4 抓封面正好切在卡缝上。全流程 PASS=3 FAIL=0，
没有任何一道闸门看得见。本脚本就是补这道闸，带退出码。

用法：
  python check_cover.py 成片.mp4 [成片2.mp4 ...] [--dur 0.5] [--fill auto|blur|black]

判据（任一不过 → exit 1）：
  ① 音轨存在、时长 > 8s
  ② 第 0 帧 == 第 14 帧（封面驻留段内画面不动）        diff < 1.0
  ③ 第 0 帧 != 第 15 帧（第 15 帧已经进正片）          diff > 3.0
  ④ 封面段几乎静音（人声在封面之后才起）              mean_volume <= -60dB
  ⑤ 第 0 帧是「中间清晰 + 两侧填充」构图：
       blur  两侧亮度 > 3（有模糊背景）且均暗于中间
       black 两侧亮度 < 3，中间 > 20
     auto 先按两侧是否 < 3 判模式
"""
import argparse
import os
import subprocess
import sys
import tempfile

FFMPEG = os.environ.get("FFMPEG_BIN", "/Users/yourname/.local/bin/ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "/Users/yourname/.local/bin/ffprobe")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path):
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-show_entries", "format=duration", "-of", "csv=p=0", path])
    lines = [x for x in r.stdout.strip().splitlines() if x]
    dur = 0.0
    for x in lines:
        if "x" not in x and "," not in x:
            try:
                dur = float(x)
            except ValueError:
                pass
    r2 = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", path])
    try:
        dur = float(r2.stdout.strip())
    except Exception:
        pass
    r3 = run([FFPROBE, "-v", "error", "-select_streams", "a",
              "-show_entries", "stream=codec_type", "-of", "csv=p=0", path])
    has_audio = "audio" in r3.stdout
    return dur, has_audio


def frames(path, idxs, tmp):
    """按帧号抽帧，返回 {idx: png}"""
    sel = "+".join("eq(n\\,%d)" % i for i in idxs)
    out = os.path.join(tmp, "f_%02d.png")
    r = run([FFMPEG, "-y", "-v", "error", "-i", path,
             "-vf", "select='%s'" % sel, "-fps_mode", "passthrough", out])
    got = {}
    for k, i in enumerate(idxs):
        p = os.path.join(tmp, "f_%02d.png" % (k + 1))
        if os.path.exists(p):
            got[i] = p
    return got


def luma(png):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(png).convert("L"), dtype="float32")
    h, w = a.shape
    tw = int(round(h * 0.75))
    x0 = (w - tw) // 2
    return a, float(a[:, x0:x0 + tw].mean()), float(a[:, :x0].mean()), float(a[:, x0 + tw:].mean())


def check_one(path, hold, fill):
    import numpy as np
    from PIL import Image
    name = os.path.basename(path)
    fails = []
    dur, has_audio = probe(path)
    if not has_audio:
        fails.append("没有音轨")
    if dur < 8:
        fails.append("时长只有 %.2fs" % dur)

    n14 = int(round(hold * 30)) - 1        # 0.5s → 第14帧
    n_next = int(round(hold * 30))         # 第15帧进正片
    with tempfile.TemporaryDirectory() as tmp:
        fr = frames(path, [0, n14, n_next], tmp)
        if len(fr) < 3:
            fails.append("抽帧失败（%d/3）" % len(fr))
            return fails, {}
        a0 = np.asarray(Image.open(fr[0]).convert("L"), dtype="float32")
        a14 = np.asarray(Image.open(fr[n14]).convert("L"), dtype="float32")
        a15 = np.asarray(Image.open(fr[n_next]).convert("L"), dtype="float32")
        d014 = float(np.abs(a0 - a14).mean())
        d015 = float(np.abs(a0 - a15).mean())

        if d014 >= 1.0:
            fails.append("第0帧与第%d帧不一致（diff %.2f，封面没停住）" % (n14, d014))
        if d015 <= 3.0:
            fails.append("第%d帧与第0帧几乎相同（diff %.2f，正片没进来 = 封面贴太长/整片是静帧）"
                         % (n_next, d015))

        _, mid, left, right = luma(fr[0])
        mode = fill
        if mode == "auto":
            mode = "black" if (left < 3 and right < 3) else "blur"
        if mode == "black":
            if not (left < 3 and right < 3 and mid > 20):
                fails.append("black 版不达标：中间 %.1f / 左 %.2f / 右 %.2f"
                             "（应中间>20、两侧<3）" % (mid, left, right))
        else:
            if mid <= 20:
                fails.append("中间清晰区过暗（%.1f）" % mid)
            if left <= 3 or right <= 3:
                fails.append("两侧像纯黑边（左 %.2f / 右 %.2f），不是 blur 填充" % (left, right))
            if left >= mid or right >= mid:
                fails.append("两侧没有压暗（中间 %.1f / 左 %.1f / 右 %.1f）" % (mid, left, right))

    # 封面段音量
    r = run([FFMPEG, "-hide_banner", "-v", "info", "-i", path,
             "-t", "%.3f" % max(0.1, hold - 0.05),
             "-af", "volumedetect", "-f", "null", "-"])
    vol = None
    for line in r.stderr.splitlines():
        if "mean_volume" in line:
            try:
                vol = float(line.split(":")[-1].strip().replace("dB", "").strip())
            except ValueError:
                pass
    if vol is None:
        fails.append("封面段音量检测失败")
    elif vol > -60:
        fails.append("封面前 %.2fs 不静音（%.1f dB，人声已经进来了）" % (hold, vol))

    return fails, {"dur": round(dur, 2), "d014": round(d014, 2), "d015": round(d015, 1),
                   "mid": round(mid, 1), "left": round(left, 2), "right": round(right, 2),
                   "vol": vol, "mode": fill}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--dur", type=float, default=0.5, help="封面停留秒数，默认 0.5")
    ap.add_argument("--fill", default="auto", choices=["auto", "blur", "black"])
    a = ap.parse_args()

    bad = 0
    for v in a.videos:
        if not os.path.exists(v):
            print("✗ %s 不存在" % v)
            bad += 1
            continue
        fails, info = check_one(v, a.dur, a.fill)
        if fails:
            bad += 1
            print("✗ %s" % os.path.basename(v))
            for f in fails:
                print("    · %s" % f)
        else:
            print("✓ %s ｜ %.2fs ｜ 第0≈第%d帧 %.2f ｜ →下一帧 %.1f ｜ 中间 %.1f 左 %.2f 右 %.2f ｜ 封面 %.1fdB ｜ %s"
                  % (os.path.basename(v), info["dur"], int(round(a.dur * 30)) - 1,
                     info["d014"], info["d015"], info["mid"], info["left"], info["right"],
                     info["vol"], info["mode"]))
    print("\n共 %d 条，通过 %d，失败 %d" % (len(a.videos), len(a.videos) - bad, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
