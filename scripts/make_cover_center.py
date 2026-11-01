#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
封面帧：产品水平居中版（2026-11-01 灿爹铁律「产品只要出现在封面里，必须居中对齐」）

原理：不动主体、不抠图补背景；只移动「景观取窗」，让产品瓶心落在取窗中心，
     取窗再几何居中贴到 16:9 画布 → 产品即落在画面中线 x=960。
     3:4 竖窗装不下人物双手时，加宽清晰区（本例 810 → 1188），
     两侧用同源图模糊压暗 + 正弦缓入渐变消融。

用法：
  python3 make_cover_center.py \
    --src gen/产品_..._16x9.png --cx 843.5 \
    --out16 封面_16比9_居中.png --out34 封面_3比4.jpg
"""
import argparse
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np


def measure_bottle(src, x_lo=500, x_hi=1100, mx_thr=170, sat_thr=40):
    """白瓶水平中心。搜索必须限制在中区，两侧白护腕会把 bbox 撑到 550~1150。"""
    a = np.array(src.convert("RGB")).astype(np.int16)
    mx, mn = a.max(2), a.min(2)
    mask = (mx > mx_thr) & ((mx - mn) < sat_thr)
    cols = mask[:, x_lo:x_hi].sum(0)
    cov = np.where(cols > 60)[0]
    if len(cov) == 0:
        raise SystemExit("白瓶检测失败，改 mx_thr/sat_thr 或手动给 --cx")
    return (cov.min() + cov.max()) / 2 + x_lo, cov.min() + x_lo, cov.max() + x_lo


def build(src, cx, card_w=1188, scale=1.25, fade=90,
          blur=40, bright=0.65, W=1920, H=1080):
    base = src.resize((W, H), Image.LANCZOS)
    bg = ImageEnhance.Brightness(base.filter(ImageFilter.GaussianBlur(blur))).enhance(bright)

    win_w = int(round(card_w / scale))
    win_h = src.size[1]
    x0 = int(round(cx - win_w / 2))
    x0 = max(0, min(x0, src.size[0] - win_w))
    fg = src.crop((x0, 0, x0 + win_w, win_h)).resize((card_w, H), Image.LANCZOS)

    px = (W - card_w) // 2
    canvas = bg.copy()
    canvas.paste(fg, (px, 0))

    mask = np.zeros((H, W), dtype=np.float32)
    mask[:, px + fade:px + card_w - fade] = 1.0
    t = np.linspace(0, 1, fade, dtype=np.float32)
    ramp = (np.sin(t * np.pi / 2)) ** 2
    mask[:, px:px + fade] = ramp
    mask[:, px + card_w - fade:px + card_w] = ramp[::-1]
    m3 = np.repeat(mask[:, :, None], 3, axis=2)
    out = np.array(bg, np.float32) * (1 - m3) + np.array(canvas, np.float32) * m3
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    landed = px + (cx - x0) * (card_w / win_w)
    return img, dict(x0=x0, win=win_w, px=px, landed=landed, scale=card_w / win_w)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--cx", type=float, help="产品水平中心（源图坐标）；不给则自动量")
    p.add_argument("--card-w", type=int, default=1188)
    p.add_argument("--scale", type=float, default=1.25)
    p.add_argument("--fade", type=int, default=90)
    p.add_argument("--out16", required=True)
    p.add_argument("--out34", help="另出 3:4 居中裁切图（平台封面用）")
    a = p.parse_args()

    src = Image.open(a.src).convert("RGB")
    if a.cx is None:
        cx, lo, hi = measure_bottle(src)
        print(f"自动测得瓶心 {cx:.1f}（bbox {lo}~{hi}）")
    else:
        cx = a.cx

    img, info = build(src, cx, a.card_w, a.scale, a.fade)
    img.save(a.out16)
    print(f"取窗 x0={info['x0']} 宽={info['win']} 贴 x={info['px']} "
          f"尺度={info['scale']:.3f} → 瓶心落 {info['landed']:.1f}（目标 960，"
          f"偏差 {info['landed'] - 960:+.1f}）")

    if a.out34:
        cw = 810
        x = (img.size[0] - cw) // 2
        img.crop((x, 0, x + cw, img.size[1])).save(a.out34, quality=95, subsampling=0)
        print(f"3:4 封面 {cw}×1080 → {a.out34}")


if __name__ == "__main__":
    main()
