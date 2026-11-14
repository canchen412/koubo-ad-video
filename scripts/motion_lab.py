#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动效 demo 生成器
================
把 motion_kit 里的 8 套入场动效，用真实素材（小绿人贴纸 + 16:9 卡片 + W7 漫画墙）
各演一遍，拼成一条片子给老板挑。

    python3 motion_lab.py --out /path/入场动效_8版.mp4
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "assets", "bg_library"))

import bg_lib                      # noqa: E402
import motion_kit as MK            # noqa: E402
import minimal_render as MR        # noqa: E402

W, H, FPS = 1920, 1080, 30
FONT = os.path.join(HERE, "..", "assets", "fonts", "STHeiti Medium.ttc")

STK = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库/角色/展示_半蹲发力浅色_全身.png"
CARD = "/Volumes/素材库/广告视频/分镜图库/小绿人/姜黄素/VORSE/图片/科普段_猛塞蛋白堆_抓食送嘴_16x9.png"

T_LEAD = 0.50          # 空场
T_ANIM = MK.DUR        # 动效
T_HOLD = 1.34          # 静止展示
SEG = T_LEAD + T_ANIM + T_HOLD


def font(sz):
    return ImageFont.truetype(FONT, sz)


def apply_layer(canvas, layer, prm, cx, cy, bottom=None):
    """按 Motion 变换后，以 (cx, cy) 为锚点贴到 img 上。
    bottom 不为 None 时改为「底边对齐 bottom」（贴纸用，弹入时脚不离地）。
    iris 为 0→1 的圆形展开比例。"""
    im = layer
    if prm.blur > 0.4:
        im = im.filter(ImageFilter.GaussianBlur(prm.blur))

    w = max(4, int(round(im.width * prm.sx)))
    h = max(4, int(round(im.height * prm.sy)))
    if (w, h) != im.size:
        im = im.resize((w, h), Image.LANCZOS)

    # 遮罩：wipe（从下往上）或 iris（圆形张开）
    mask = None
    if prm.wipe is not None:
        mask = Image.new("L", im.size, 0)
        top = int(im.height * (1.0 - prm.wipe))
        ImageDraw.Draw(mask).rectangle([0, top, im.width, im.height], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(max(2, im.height // 90)))
    if prm.iris is not None:
        mask = Image.new("L", im.size, 0)
        r = max(2.0, prm.iris * math.hypot(im.width, im.height) * 0.60)
        ImageDraw.Draw(mask).ellipse(
            [im.width // 2 - r, im.height // 2 - r,
             im.width // 2 + r, im.height // 2 + r], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(4))

    if mask is not None:
        from PIL import ImageChops
        im = im.copy()
        im.putalpha(ImageChops.multiply(im.getchannel("A"), mask))

    if abs(prm.rot) > 0.05:
        im = im.rotate(prm.rot, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))

    if prm.alpha < 0.999:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v, k=prm.alpha: int(v * k)))

    w, h = im.size
    x = cx - w // 2 + int(round(prm.dx))
    if bottom is not None:
        y = bottom - h + int(round(prm.dy))
    else:
        y = cy - h // 2 + int(round(prm.dy))
    canvas.alpha_composite(im, (max(-w, x), max(-h, y)))


def label(frame, idx, kind, name, desc, total):
    d = ImageDraw.Draw(frame)
    f_big = font(46)
    f_sml = font(26)
    text = "%s · %s" % (chr(ord("A") + idx), name)
    tw = d.textlength(text, font=f_big)
    pad = 26
    x0, y0 = 52, 44
    d.rounded_rectangle([x0 - 18, y0 - 12, x0 + tw + pad, y0 + 62],
                        radius=16, fill=(14, 14, 18, 190))
    d.text((x0, y0), text, font=f_big, fill=(255, 214, 72))
    # 说明
    dw = d.textlength(desc, font=f_sml)
    d.rounded_rectangle([x0 - 18, y0 + 66, x0 + max(dw, tw) + pad, y0 + 112],
                        radius=12, fill=(14, 14, 18, 150))
    d.text((x0, y0 + 76), desc, font=f_sml, fill=(226, 230, 238))
    # 右上角计数
    cnt = "%d / %d" % (idx + 1, total)
    cw = d.textlength(cnt, font=f_sml)
    d.text((W - 60 - cw, 52), cnt, font=f_sml, fill=(190, 196, 208))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/入场动效_8版.mp4")
    ap.add_argument("--only", default="", help="只跑指定 kind，逗号分隔")
    a = ap.parse_args()

    bg = bg_lib.Background(bg_lib.DEFAULT)
    base = Image.fromarray(bg.frame(0.0), "RGB").convert("RGBA")

    stickers = MR.StickerLib()
    cards = MR.CardFactory()

    stk = stickers.load(STK)
    stk_h = 742
    stk = stk.resize((int(stk.width * stk_h / stk.height), stk_h), Image.LANCZOS)
    # 贴纸自带投影
    sh = MR.radial_shadow((int(stk.width * 0.55), int(stk.width * 0.55 * 0.16)), op=100)
    s_l = stk.copy()
    s_l.alpha_composite(sh, ((s_l.width - sh.width) // 2, s_l.height - sh.height // 2 - 6))

    cw, ch = 820, 461
    card_im = cards.make(MR.fit_crop(Image.open(CARD), cw, ch, "16x9"), cw, ch)

    kinds = [k for k, _, _ in MK.KINDS]
    if a.only:
        kinds = [k.strip() for k in a.only.split(",") if k.strip()]
    names = {k: (n, d) for k, n, d in MK.KINDS}

    tmp = tempfile.mkdtemp(prefix="motionlab_")
    out = a.out
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
         "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE)

    CX_L, CX_R = int(W * 0.29), int(W * 0.73)
    BASE_Y, CARD_CY = 968, 520
    total = len(kinds)
    print("渲染 %d 段，每段 %.2fs，共 %.1fs" % (total, SEG, total * SEG))

    for idx, kind in enumerate(kinds):
        name, desc = names[kind]
        nf = int(round(SEG * FPS))
        for f in range(nf):
            t = f / float(FPS)
            frame = base.copy()
            p = 0.0 if t < T_LEAD else min(1.0, (t - T_LEAD) / T_ANIM)
            prm = MK.params(kind, p, direction=-1 if idx % 2 else 1)
            if p > 0 or t >= T_LEAD:
                apply_layer(frame, s_l, prm, CX_L, CARD_CY, bottom=BASE_Y)
                apply_layer(frame, card_im, prm, CX_R, CARD_CY)
            label(frame, idx, kind, name, desc, total)
            proc.stdin.write(frame.convert("RGB").tobytes())
        if (idx + 1) % 2 == 0:
            print("  %d/%d  %s" % (idx + 1, total, kind), flush=True)

    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise SystemExit("ffmpeg 失败")
    print("→", out)


if __name__ == "__main__":
    main()
