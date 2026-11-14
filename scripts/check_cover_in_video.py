#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸门：成片第 0 帧到底是不是指定的封面。

为什么必须有这个脚本（2026-11-10）：
  老板要「封面加到成片里，发视频直接不用调」= 平台抓首帧当封面。
  而 pipeline 的封面帧会在 `os.replace(final_cov → final)` 被拦下后**静默丢失**，
  日志只有一行 ⚠️，成片照常输出、时长只差 0.5s，人眼不看首帧根本发现不了。
  那次三条片交出去第 0 帧全是黑的。所以做成带退出码的闸门。

判据：
  ① 首帧不能是黑帧（灰度均值 ≥ BLACK_Y）；
  ② 首帧中间的 3:4 竖区（平台封面框）与封面图做 NCC，≥ MIN_NCC 才算贴上。
     NCC 用去均值的归一化互相关，对整体亮度差免疫（封面淡出后的帧也能认出来）。

用法：
  python3 check_cover_in_video.py --video a.mp4 --cover a.jpg [--video b.mp4 --cover b.jpg ...]
  退出码 0 = 全过；1 = 有不达标。
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

FF = "/Users/yourname/.local/bin/ffmpeg" if os.path.exists("/Users/yourname/.local/bin/ffmpeg") else "ffmpeg"
STRIP_RATIO = 3 / 4          # 平台封面框 3:4
BLACK_Y = 22.0               # 首帧灰度均值低于此 = 黑帧
MIN_NCC = 0.55               # 与封面图的相关性下限
PROBE_AT = 0.06              # 抽帧时刻：避开第 0 帧与编码边界的抖动


def grab_luma(video, t=PROBE_AT):
    tmp = tempfile.mktemp(suffix=".png")
    subprocess.run([FF, "-y", "-v", "error", "-ss", f"{t}", "-i", video,
                    "-frames:v", "1", tmp], check=True)
    im = Image.open(tmp).convert("L")
    os.remove(tmp)
    return im


def ncc(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    a = a - a.mean()
    b = b - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum())) + 1e-9
    return float((a * b).sum() / den)


def center_strip(im_luma):
    """取画面中间 3:4 竖条 —— 平台抓首帧做封面时裁的就是这一块。"""
    w, h = im_luma.size
    sw = int(round(h * STRIP_RATIO))
    left = (w - sw) // 2
    return im_luma.crop((left, 0, left + sw, h))


def check(video, cover):
    if not os.path.exists(video):
        return False, f"✗ 找不到成片 {video}"
    if not os.path.exists(cover):
        return False, f"✗ 找不到封面图 {cover}"

    f0 = grab_luma(video)
    y = float(np.asarray(f0, dtype=np.float64).mean())
    if y < BLACK_Y:
        return False, f"✗ 首帧是黑帧（均值 {y:.1f} < {BLACK_Y}）—— 封面没进片"

    strip = center_strip(f0)
    ref = Image.open(cover).convert("L").resize(strip.size, Image.LANCZOS)
    score = ncc(strip, ref)
    ok = score >= MIN_NCC
    mark = "✅" if ok else "✗"
    return ok, (f"{mark} 首帧均值 {y:.0f}｜中间 3:4 与封面 NCC {score:.3f}"
                f"（阈值 {MIN_NCC}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", action="append", required=True)
    ap.add_argument("--cover", action="append", required=True)
    a = ap.parse_args()
    if len(a.video) != len(a.cover):
        print("✗ --video 与 --cover 数量必须一致（一一对应）")
        return 1

    bad = 0
    for v, c in zip(a.video, a.cover):
        ok, msg = check(v, c)
        print(f"{os.path.basename(v)[:58]:<58} {msg}")
        if not ok:
            bad += 1
    print(f"\n{'✅ 全部通过' if not bad else f'✗ {bad} 条不达标'}："
          f"{len(a.video) - bad}/{len(a.video)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
