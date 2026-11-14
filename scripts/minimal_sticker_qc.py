#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贴纸深底质检（极简版专用闸门）
============================
浅底会掩盖一切白色残留 —— 白底配白羽化，肉眼看不出来；
一放到深炭背景上，白边/光晕立刻变成一圈毛。

判据：把贴纸合成到深底上，统计「不透明像素里接近纯白」的占比。
  正常贴纸：< 1.2%（白护腕、白色高光算正常）
  脏贴纸  ：> 1.8%（手指外圈光晕、脚下扬尘这类）

用法：
    python3 minimal_sticker_qc.py --cut "$CUT/角色" "$CUT/物品"
    python3 minimal_sticker_qc.py --cut ... --sheet /tmp/qc.jpg   # 出对比图给人看
退出码：有脏贴纸 → 1（可直接当出片前置）
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

DARK = np.array([22, 21, 20], np.float32)
WARN, BAD = 0.10, 0.18


def qc_one(path, band_px=0.035):
    """只看「贴边一圈」的白色 —— 白瓶子、白药片内部是正常白，
    真正的问题是手指外圈光晕、脚下扬尘这种贴在轮廓上的白毛。"""
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    rgb, al = a[..., :3], a[..., 3] / 255.0
    opaque = al > 0.6
    if opaque.sum() == 0:
        return None
    k = max(3, int(round(min(im.width, im.height) * band_px)))
    k += (k + 1) % 2                                    # MinFilter 要奇数
    mask = Image.fromarray((opaque * 255).astype(np.uint8), "L")
    eroded = np.asarray(mask.filter(ImageFilter.MinFilter(k))) > 127
    band = opaque & ~eroded
    if band.sum() == 0:
        return None
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    white = band & (mn > 205) & ((mx - mn) < 26)
    ratio = float(white.sum()) / float(band.sum())
    return {"file": os.path.basename(path), "ratio": ratio, "w": im.width, "h": im.height}


def preview(path, box=(380, 380)):
    im = Image.open(path).convert("RGBA")
    sc = min(box[0] / im.width, box[1] / im.height)
    im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
    bg = Image.new("RGBA", box, tuple(int(v) for v in DARK) + (255,))
    bg.alpha_composite(im, ((box[0] - im.width) // 2, (box[1] - im.height) // 2))
    return bg.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut", nargs="+", required=True)
    ap.add_argument("--sheet", default=None, help="出一张深底对比图")
    a = ap.parse_args()

    files = []
    for d in a.cut:
        for f in sorted(os.listdir(d)):
            if f.endswith(".png") and not f.startswith("."):
                files.append(os.path.join(d, f))

    rows, bad = [], []
    for p in files:
        r = qc_one(p)
        if r is None:
            continue
        lvl = "OK  " if r["ratio"] < WARN else ("注意" if r["ratio"] < BAD else "脏  ")
        rows.append((lvl, r))
        if r["ratio"] >= BAD:
            bad.append(r)

    for lvl, r in sorted(rows, key=lambda x: -x[1]["ratio"]):
        print("%s %.2f%%  %s" % (lvl, r["ratio"] * 100, r["file"]))

    if a.sheet:
        cols = 6
        cell = 380
        n = len(rows)
        sheet = Image.new("RGB", (cell * cols, cell * ((n + cols - 1) // cols)), (10, 10, 10))
        for i, (lvl, r) in enumerate(sorted(rows, key=lambda x: -x[1]["ratio"])):
            p = next(f for f in files if os.path.basename(f) == r["file"])
            sheet.paste(preview(p, (cell, cell)), ((i % cols) * cell, (i // cols) * cell))
        sheet.save(a.sheet, quality=92)
        print("→", a.sheet)

    if bad:
        print("\n❌ %d 张脏贴纸（深底会露白毛），先去重抠再出片：%s"
              % (len(bad), ", ".join(r["file"] for r in bad)))
        sys.exit(1)
    print("\n✅ 贴纸深底质检通过")


if __name__ == "__main__":
    main()
