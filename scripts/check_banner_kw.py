#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_banner_kw.py —— 卷播段「有没有大字」闸门（2026-11-09 燕麦返工后新增）

现象：极简版·卷播版的首版渲染漏传 `--kw-alpha / --kw-t0`，
      卷播段只剩卡列滚动 + 主图放大，一个重点字都没有。
      因为卷播「吃镜1」会整镜替掉 s01，那个重点字在整条片里**一次都不会出现**，
      而 minimal_plan_check / kw_clear_check / cover_frame 三道闸门全绿 —— 它们只看 plan 字段，
      不看渲染结果。这一条就是补那个洞。

判据：大字是米白（约 240,236,226，B 明显低于 R）+ 粗笔画。
      白色碗/白墙是中性白（B≈R），细白边框会被腐蚀掉 —— 三者靠「暖白 + 腐蚀 + 面积」区分开。

用法：
    python3 check_banner_kw.py --video 成片.mp4                 # 默认扫 0~3s（卷播吃镜1 的窗口）
    python3 check_banner_kw.py --video 成片.mp4 --t0 0 --t1 4  # 自定义窗口
    python3 check_banner_kw.py --video 成片.mp4 --report       # 打印逐秒命中率

退出码：0 = 窗口内出现过成块米白大字；1 = 没出现（**当场返工，别交付**）
"""
import argparse
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

CREAM_R, CREAM_G, CREAM_B = 210, 200, 180   # 米白下限
WARM_GAP = 8                                 # B 至少比 R 低这么多，才算「暖白」
MIN_RATIO = 0.004                            # 腐蚀后米白面积占比下限（540 宽 ≈ 1166 px）


def frames(path, t0, t1, fps=10, width=540):
    dur = t1 - t0
    cmd = [
        "ffmpeg", "-v", "error", "-ss", "%.3f" % t0, "-t", "%.3f" % dur, "-i", path,
        "-vf", "fps=%d,scale=%d:-1" % (fps, width),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True).stdout
    if not raw:
        return []
    # 用第一帧推高度
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    w0, h0 = [int(x) for x in probe.split(",")[:2]]
    h = int(round(width * h0 / w0 / 2.0)) * 2
    n = len(raw) // (width * h * 3)
    arr = np.frombuffer(raw[: n * width * h * 3], dtype=np.uint8).reshape(n, h, width, 3)
    return [Image.fromarray(a, "RGB") for a in arr]


def cream_mask(im):
    a = np.asarray(im).astype(np.int16)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = (R > CREAM_R) & (G > CREAM_G) & (B > CREAM_B) & (B < R - WARM_GAP)
    if not m.any():
        return 0.0
    # 腐蚀：去掉 3–5px 的细白框线，只留粗笔画
    thin = Image.fromarray((m * 255).astype(np.uint8), "L").filter(ImageFilter.MinFilter(7))
    e = np.asarray(thin) > 128
    return float(e.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--t0", type=float, default=0.0, help="扫描起点（默认 0，含封面则写 0.5）")
    ap.add_argument("--t1", type=float, default=3.0, help="扫描终点（默认 3.0，卷播吃镜1 一般 ≤2.3 + 封面 0.5）")
    ap.add_argument("--report", action="store_true", help="打印逐帧命中率")
    ap.add_argument("--min-ratio", type=float, default=MIN_RATIO)
    args = ap.parse_args()

    ims = frames(args.video, args.t0, args.t1)
    if not ims:
        print("✗ 抽不到帧，检查 --t0/--t1 与视频时长")
        return 2

    ratios = [cream_mask(im) for im in ims]
    hit = max(ratios) if ratios else 0.0
    idx = int(np.argmax(ratios)) if ratios else 0

    if args.report:
        step = max(1, len(ratios) // 30)
        for i in range(0, len(ratios), step):
            t = args.t0 + i / 10.0
            print("  t=%5.2fs  米白成块占比 %.4f %s" % (t, ratios[i], "←" if i == idx else ""))

    if hit >= args.min_ratio:
        print("✓ [PASS] 卷播段有米白大字：峰值 %.4f @ t=%.2fs（阈值 %.4f）"
              % (hit, args.t0 + idx / 10.0, args.min_ratio))
        return 0

    print("✗ [FAIL] 卷播段没有成块米白大字：峰值仅 %.4f（阈值 %.4f）" % (hit, args.min_ratio))
    print("   → 八成是 banner_onbg.py 漏了 --kw-alpha <hero_alpha.png> --kw-t0 <秒> --kw-chars <字>")
    print("   → 卷播吃镜1 会整镜替掉 s01，漏了这一步，该重点字在整条片里一次都不会出现")
    return 1


if __name__ == "__main__":
    sys.exit(main())
