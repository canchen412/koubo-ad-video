#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hero_label_3d.py —— 「3D 景深大字」三层合成（标准开头也可用，不依赖卷播）

三层：hero_bg（空镜/场景，虚化压暗）→ 字层（金色大字 + 黑描边 + 投影）→ hero_fg（人物抠像）
字被人物躯干遮住一段 = 景深。两个子命令：

  matrix  出 size × top 候选矩阵图，给人眼挑参数（**必须先出矩阵再渲视频**）
  render  按定稿参数逐帧渲成 mp4，直接当 shot_map 的 imgvid 素材用

用法
----
# 1) 候选矩阵（挑 size / top）
python3 hero_label_3d.py matrix \
    --bg "分镜图库/.../场景_空镜健身房_大远景.png" \
    --fg "分镜图库/.../举铁_站姿推举_中景_净边.png" \
    --text 形象投资 --fg-h 1060 --fg-top -20 --out qc/hero_matrix.jpg

# 2) 定稿渲染（参数照矩阵挑出来的填）
python3 hero_label_3d.py render \
    --bg "…空镜健身房…png" --fg "…站姿推举…净边.png" \
    --text 形象投资 --size 390 --gap 34 --top 202 \
    --fg-h 1060 --fg-top -20 --dur 1.24 --out assets/宣言_形象投资_景深.mp4

关键参数（2026-11-06 21金维他烟酰胺 v1 定稿值，四字词）
----
size 390 / gap 34 / top 202 / fg_h 1060 / fg_top -20 /
enter 0.30 / sc_in 1.09 / sc_out 1.03 / blur_in 6.0 / rise 46 / breath 0.012

判据
----
· 字块总宽应落在 **70~78% 屏宽**（左右各留 11~15%），脚本会打印。
  >85% 会压到画面左右边缘；<65% 气势不够。
· 入场 `sc_in` 不要超过 1.15 —— 字块本就宽，起始放大过大会顶出画面上沿。
· `enter` 必须 > 该镜转场时长（fx 模式 hblur 0.34s）。否则整个入场被 xfade 吃掉，字是"突然出现"。
· 人物 `fg_h` 取画面高 95~100%（近景才压得住字）；`fg_top` 允许 −30~0（头顶微出框）。
"""
import argparse
import os
import subprocess
import sys
import math

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W_DEF, H_DEF = 1920, 1080
FPS_DEF = 30

FONT_CANDIDATES = [
    os.path.expanduser("~/Library/Fonts/新青年体.ttf"),
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]


def pick_font(explicit=None):
    if explicit:
        if not os.path.isfile(explicit):
            sys.exit(f"✗ 字体不存在：{explicit}")
        return explicit
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    sys.exit("✗ 找不到可用中文字体，请用 --font 指定")


# ---------------------------------------------------------------- 底层 / 前层
def make_bg(path, W, H, blur=2.6, bright=0.72, contrast=1.08, color=0.92, y_bias=0.42):
    """底层：cover 铺满 + 高斯虚化 + 压暗。虚化是为了让字和人物都跳出来。"""
    im = Image.open(path).convert("RGB")
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r + 1), int(im.height * r + 1)), Image.LANCZOS)
    x = (im.width - W) // 2
    y = int((im.height - H) * y_bias)      # 偏上，保住地面光斑
    im = im.crop((x, y, x + W, y + H))
    im = im.filter(ImageFilter.GaussianBlur(blur))
    im = ImageEnhance.Brightness(im).enhance(bright)
    im = ImageEnhance.Contrast(im).enhance(contrast)
    im = ImageEnhance.Color(im).enhance(color)
    return im


def make_fg(path, h_px):
    """前层：人物抠像（必须净边 PNG），等比缩放到指定高度"""
    fg = Image.open(path).convert("RGBA")
    r = h_px / fg.height
    return fg.resize((int(fg.width * r), h_px), Image.LANCZOS)


# ---------------------------------------------------------------- 字层
def draw_text_layer(text, size, gap, top, font_path, W, H, color=(255, 210, 74)):
    """金色大字 + 8 向黑描边 + 高斯投影，返回 (整幅 RGBA, 字块总宽)

    8 向描边是「压在虚化背景上仍能读清」的保证；投影给纵深。禁外发光（会糊）。
    """
    font = ImageFont.truetype(font_path, size)
    widths = [font.getbbox(c)[2] - font.getbbox(c)[0] for c in text]
    total = sum(widths) + gap * (len(text) - 1)
    x0 = (W - total) // 2

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # ① 投影
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    cx = x0
    for c, w in zip(text, widths):
        ds.text((cx - font.getbbox(c)[0], top), c, font=font, fill=(0, 0, 0, 235))
        cx += w + gap
    layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(18)))

    # ② 8 向黑描边
    stroke = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dst = ImageDraw.Draw(stroke)
    offs = [(-4, 0), (4, 0), (0, -4), (0, 4), (-3, -3), (3, -3), (-3, 3), (3, 3)]
    cx = x0
    for c, w in zip(text, widths):
        ox = cx - font.getbbox(c)[0]
        for dx, dy in offs:
            dst.text((ox + dx, top + dy), c, font=font, fill=(12, 10, 6, 255))
        cx += w + gap
    layer = Image.alpha_composite(layer, stroke)

    # ③ 主体字
    face = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    df = ImageDraw.Draw(face)
    cx = x0
    for c, w in zip(text, widths):
        df.text((cx - font.getbbox(c)[0], top), c, font=font, fill=tuple(color) + (255,))
        cx += w + gap
    layer = Image.alpha_composite(layer, face)
    return layer, total


# ---------------------------------------------------------------- 子命令 1：矩阵
def cmd_matrix(a):
    W, H = a.width, a.height
    font_path = pick_font(a.font)
    sizes = [int(s) for s in a.sizes.split(",")]
    tops = [int(s) for s in a.tops.split(",")]
    bg = make_bg(a.bg, W, H).convert("RGBA")
    fg = make_fg(a.fg, a.fg_h)

    cw, ch = 560, 315
    canvas = Image.new("RGB", (cw * len(sizes), ch * len(tops) + 30), (12, 12, 12))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(font_path, 20)
    for i, s in enumerate(sizes):
        d.text((i * cw + 8, 4), f"size {s}", font=f, fill=(255, 225, 120))

    for j, tp in enumerate(tops):
        d.text((8, 32 + j * ch + 4), f"top {tp}", font=f, fill=(255, 225, 120))
        for i, s in enumerate(sizes):
            tl, total = draw_text_layer(a.text, s, a.gap, tp, font_path, W, H)
            out = Image.alpha_composite(bg.copy(), tl)
            out.alpha_composite(fg, ((W - fg.width) // 2, a.fg_top))
            print(f"size={s} top={tp}  字块总宽={total}px ({total / W * 100:.0f}% 屏宽)")
            canvas.paste(out.convert("RGB").resize((cw, ch)), (i * cw, 32 + j * ch))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    canvas.save(a.out, quality=93)
    print("→", a.out, canvas.size)


# ---------------------------------------------------------------- 子命令 2：渲视频
def _ease_out_cubic(u):
    u = min(1.0, max(0.0, u))
    return 1.0 - (1.0 - u) ** 3


def _ease_in_out_sine(u):
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


def cmd_render(a):
    W, H, FPS = a.width, a.height, a.fps
    font_path = pick_font(a.font)
    bg = make_bg(a.bg, W, H).convert("RGBA")
    fg = make_fg(a.fg, a.fg_h)

    # 字层按 1.25 倍画布预渲，留放大余量（放大时不掉边缘）
    k = 1.25
    tl_big, total = draw_text_layer(a.text, int(a.size * k), int(a.gap * k), int(a.top * k),
                                    font_path, int(W * k), int(H * k))
    print(f"字块总宽 {total / k:.0f}px（{total / k / W * 100:.0f}% 屏宽）  人物宽 {fg.width}")

    n = max(2, round(a.dur * FPS))
    tmp = f"/tmp/_hero3d_{os.getpid()}"
    os.makedirs(tmp, exist_ok=True)

    for fi in range(n):
        t = fi / FPS
        im = bg.copy()

        t0 = a.t0
        ta = t - t0
        if t < t0:
            show = False
        elif ta < a.enter:
            show = True
            u = _ease_out_cubic(ta / a.enter)
            sc = a.sc_in + (1.0 - a.sc_in) * u
            blur = a.blur_in * (1.0 - u)
            op = a.op_in + (1.0 - a.op_in) * u
            sfrom = {"left": -a.slide_px, "right": a.slide_px}.get(a.slide, 0)
            dx = int(round(sfrom * (1.0 - u)))
            dy = int(round(a.rise * (1.0 - u)))
        else:
            show = True
            u = _ease_in_out_sine((t - (t0 + a.enter))
                                  / max(0.01, a.dur - (t0 + a.enter)))
            sc = 1.0 + (a.sc_out - 1.0) * u
            blur = 0.0
            op = 1.0
            dx = dy = 0

        if show:
            tw, th = int(tl_big.width * sc / k), int(tl_big.height * sc / k)
            tl = tl_big.resize((tw, th), Image.LANCZOS)
            if blur > 0.15:                   # 降采样做模糊，快得多
                small = tl.resize((max(1, tw // 4), max(1, th // 4)), Image.BILINEAR)
                small = small.filter(ImageFilter.GaussianBlur(blur / 4))
                tl = small.resize((tw, th), Image.BILINEAR)
            if op < 1.0:
                tl.putalpha(tl.getchannel("A").point(lambda v: int(v * op)))
            im.alpha_composite(tl, ((W - tw) // 2 + dx, (H - th) // 2 + dy))

        # 人物极轻微呼吸（1 + breath），避免整帧像静态图
        u2 = _ease_in_out_sine(t / max(0.01, a.dur))
        fs = 1.0 + a.breath * u2
        f2 = fg.resize((int(fg.width * fs), int(fg.height * fs)), Image.LANCZOS)
        im.alpha_composite(f2, ((W - f2.width) // 2, a.fg_top - int((f2.height - a.fg_h) * 0.5)))

        im.convert("RGB").save(f"{tmp}/f{fi:04d}.png")
        if fi % 10 == 0:
            print(f"  帧 {fi}/{n}")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
           "-i", f"{tmp}/f%04d.png", "-an",
           "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p",
           "-r", str(FPS), a.out]
    if a.audio:                              # 入库原稿要带音轨 → 铺一条静音
        cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
               "-i", f"{tmp}/f%04d.png", "-f", "lavfi",
               "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
               "-c:v", "libx264", "-crf", "15", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-shortest", "-r", str(FPS), a.out]
    subprocess.run(cmd, check=True)
    print("→", a.out)

    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="3D 景深大字三层合成（bg → 字 → 人物）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("matrix", "render"):
        p = sub.add_parser(name)
        p.add_argument("--bg", required=True, help="底层场景图（空镜/背景）")
        p.add_argument("--fg", required=True, help="前层人物抠像（净边 PNG）")
        p.add_argument("--text", required=True, help="大字内容，如 形象投资")
        p.add_argument("--out", required=True)
        p.add_argument("--size", type=int, default=390)
        p.add_argument("--gap", type=int, default=34, help="字间距")
        p.add_argument("--top", type=int, default=202, help="字层基线 y")
        p.add_argument("--fg-h", type=int, default=1060, help="人物高")
        p.add_argument("--fg-top", type=int, default=-20, help="人物头顶 y（负值=出框）")
        p.add_argument("--width", type=int, default=W_DEF)
        p.add_argument("--height", type=int, default=H_DEF)
        p.add_argument("--font", default=None)

    m = sub.choices["matrix"]
    m.add_argument("--sizes", default="340,380,420")
    m.add_argument("--tops", default="150,250,350")

    r = sub.choices["render"]
    r.add_argument("--dur", type=float, default=1.24)
    r.add_argument("--fps", type=int, default=FPS_DEF)
    r.add_argument("--enter", type=float, default=0.30, help="入场时长，须 > 转场时长")
    r.add_argument("--sc-in", dest="sc_in", type=float, default=1.09)
    r.add_argument("--sc-out", dest="sc_out", type=float, default=1.03)
    r.add_argument("--blur-in", dest="blur_in", type=float, default=6.0)
    r.add_argument("--rise", type=float, default=46, help="入场时字从下往上浮的像素")
    r.add_argument("--breath", type=float, default=0.012, help="人物呼吸缩放幅度")
    r.add_argument("--audio", action="store_true", help="铺一条静音音轨（入库原稿用）")
    r.add_argument("--t0", type=float, default=0.0,
                   help="入场延迟起点（秒）：t<t0 不显示字，说到该时刻才出来")
    r.add_argument("--op-in", dest="op_in", type=float, default=0.55,
                   help="入场起始不透明度")
    r.add_argument("--slide", choices=("none", "left", "right"), default="none",
                   help="水平滑入方向：left=从左往右推进来，right=从右往左推进来")
    r.add_argument("--slide-px", dest="slide_px", type=int, default=320,
                   help="水平滑入起始位移像素")

    a = ap.parse_args()
    (cmd_matrix if a.cmd == "matrix" else cmd_render)(a)


if __name__ == "__main__":
    main()
