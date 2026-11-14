#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
漫画分格墙 · 配色实验
原来的墙是纯灰度（234+delta*0.27），在暖米色底上偏冷、发脏。
这里给 5 种配色，先出静帧，选定后再渲动态片。
"""
import os, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = "/Volumes/素材库/广告视频/_样片_信息卡_261101"
CUT = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库"
GAL = "/Volumes/素材库/广告视频/分镜图库/小绿人"
FONT = "/Users/yourname/.workbuddy/skills/koubo-ad-video/assets/fonts/STHeiti Medium.ttc"

W, H, FPS = 1920, 1080, 30
LW, LH = 960, 540
BASE_Y = 970
SUB_TEXT = "很多兄弟训练完，只顾猛冲高碳水跟高蛋白。"

yy, xx = np.mgrid[0:LH, 0:LW].astype(np.float32)
NX = xx / LW
NY = yy / LH
_cx, _cy = LW * 0.5, LH * 0.42
RAD = np.sqrt((xx - _cx) ** 2 / (LW * 0.78) ** 2 + (yy - _cy) ** 2 / (LH * 0.78) ** 2)


def font(sz):
    return ImageFont.truetype(FONT, sz)


WALL_SRC = [
    "开场_健身房光柱顿悟_中景仰拍_16x9.png",
    "举铁_仰卧推举杠铃橙光_中景_16x9.jpg",
    "举铁_站姿推举杠铃白墙_中景_16x9.jpg",
    "举铁_颈前深蹲杠铃_中景_16x9.jpg",
    "举铁_力竭坐凳直视_中景_16x9.png",
    "张力_小绿人_痛点对比_深夜vs清晨_中景_16x9.png",
    "张力_小绿人_痛点对比_瘫坐vs站立_中景_16x9.png",
    "张力_小绿人_痛点对比_镜前两态_中景_16x9.png",
    "张力_小绿人_握拳蓄力金光_全身_16x9.png",
    "展示_出拳金环马步_全景_16x9.png",
    "展示_健身房器械区站姿_中景_16x9.jpg",
    "张力_小绿人_原理讲解_能量充能路径_中景_16x9.png",
    "张力_小绿人_原理讲解_成分网格黑场_中景_16x9.png",
    "开场_黑板指镜头仰拍_男孩指镜头_中景_16x9.png",
    "张力_小绿人_痛点对比_被压垮vs被支撑_全景_16x9.png",
    "张力_小绿人_原理讲解_转化链可视化_全景_16x9.png",
]

CW, CH = 600, 338
_CELLS = []


def load_cells():
    """把 16 张图裁成格子，保留原始 RGB（配色在拼墙时再做）"""
    global _CELLS
    if _CELLS:
        return _CELLS
    for name in WALL_SRC:
        p = os.path.join(GAL, name)
        if not os.path.exists(p):
            _CELLS.append(Image.new("RGB", (CW, CH), (128, 128, 128)))
            continue
        im = Image.open(p).convert("RGB")
        sc = max(CW / im.width, CH / im.height)
        im = im.resize((max(CW, int(im.width * sc)), max(CH, int(im.height * sc))), Image.LANCZOS)
        x, y = (im.width - CW) // 2, (im.height - CH) // 2
        _CELLS.append(im.crop((x, y, x + CW, y + CH)))
    return _CELLS


def norm_lum(im, mean=0.78, std=0.11):
    """逐格归一化：把每一格自己的明暗对比拉齐。
    这是「不发脏」的关键——16 张图原本有的很亮有的很暗，
    套同一个映射就会一块块深浅不一，看着像污渍。"""
    g = np.asarray(im.convert("L")).astype(np.float32) / 255.0
    sd = float(g.std())
    g = mean + (g - float(g.mean())) * (std / max(sd, 1e-3))
    return np.clip(g, 0.0, 1.0)


def tone_duotone(im, dark, light, mean=0.78, std=0.11, gamma=1.0):
    """逐格归一化 → 双色调映射。std 决定格子里的内容有多清楚"""
    g = norm_lum(im, mean, std) ** gamma
    d = np.array(dark, np.float32)
    l = np.array(light, np.float32)
    return d + (l - d) * g[..., None]


def tone_color(im, sat=0.55, paper=(252, 249, 241), w=0.30, mean=0.80, std=0.115):
    """保留原图色彩：逐格归一化亮度 → 加回部分饱和度 → 混向纸色"""
    arr = np.asarray(im).astype(np.float32) / 255.0
    lum = arr.mean(axis=2)
    sd = float(lum.std())
    g = np.clip(mean + (lum - float(lum.mean())) * (std / max(sd, 1e-3)), 0.0, 1.0)
    gain = g / np.maximum(lum, 1e-3)
    out = arr * gain[..., None]
    g3 = g[..., None]
    out = g3 + (out - g3) * sat                       # 降饱和
    pc = np.array(paper, np.float32) / 255.0
    out = out * (1.0 - w) + pc * w                    # 混向纸色，压住鲜艳
    return np.clip(out, 0, 1) * 255.0


VARIANTS = [
    dict(id="P1", name="暖纸米",   fn="duo",
         dark=(156, 141, 120), light=(252, 249, 241), mean=0.80, std=0.115,
         line=(253, 251, 245), hair=(199, 191, 176), label=(46, 40, 32)),
    dict(id="P2", name="冷灰蓝",   fn="duo",
         dark=(126, 136, 148), light=(246, 248, 251), mean=0.82, std=0.105,
         line=(252, 253, 255), hair=(186, 193, 202), label=(38, 44, 52)),
    dict(id="P3", name="暖橙",     fn="duo",
         dark=(178, 138, 104), light=(253, 245, 234), mean=0.80, std=0.115,
         line=(254, 247, 238), hair=(215, 191, 168), label=(74, 44, 22)),
    dict(id="P4", name="暖纸米·深格线", fn="duo",
         dark=(150, 135, 114), light=(252, 249, 241), mean=0.80, std=0.125,
         line=(74, 64, 52), hair=(150, 140, 124), lw=4, label=(46, 40, 32)),
    dict(id="P5", name="深炭",     fn="duo",
         dark=(20, 20, 22),    light=(108, 103, 97),  mean=0.70, std=0.17,
         line=(122, 118, 112), hair=(56, 54, 52), label=(248, 246, 240)),
]


def build_wall(v):
    wall = Image.new("RGB", (CW * 4, CH * 4),
                     tuple(int(x) for x in v.get("light") or v.get("paper")))
    for i, cell in enumerate(load_cells()):
        if v["fn"] == "color":
            arr = tone_color(cell, v["sat"], v["paper"], v["w"], v["mean"], v["std"])
        else:
            arr = tone_duotone(cell, v["dark"], v["light"], v["mean"], v["std"])
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        wall.paste(im, (CW * (i % 4), CH * (i // 4)))
    d = ImageDraw.Draw(wall)
    for c in range(1, 4):
        wln = v.get("lw", 7)
        d.line([(CW * c, 0), (CW * c, wall.height)], fill=v["line"], width=wln)
        d.line([(0, CH * c), (wall.width, CH * c)], fill=v["line"], width=wln)
    for c in range(1, 4):
        d.line([(CW * c, 0), (CW * c, wall.height)], fill=v["hair"], width=1)
        d.line([(0, CH * c), (wall.width, CH * c)], fill=v["hair"], width=1)
    return wall.resize((1440, 810), Image.LANCZOS)


def bg_from_wall(wall, t, dark_vignette=True):
    ox = 240 + 110 * math.sin(t * 0.26)
    oy = 135 + 70 * math.cos(t * 0.21)
    crop = wall.crop((int(ox), int(oy), int(ox) + LW, int(oy) + LH))
    arr = np.asarray(crop).astype(np.float32)
    if dark_vignette:
        arr = arr * (1.0 - 0.055 * RAD[..., None] ** 1.4)
    return arr


# ---------------- 贴纸 / 字幕 ----------------

def load_sticker(path, height):
    im = Image.open(path).convert("RGBA")
    w = max(8, int(round(im.width * height / im.height)))
    return im.resize((w, height), Image.LANCZOS)


def make_shadow(size, op=70):
    w, h = max(8, int(size[0])), max(8, int(size[1]))
    yy2, xx2 = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    r = np.sqrt(((xx2 - cx) / (w / 2.0)) ** 2 + ((yy2 - cy) / (h / 2.0)) ** 2)
    a = (np.clip(1.0 - r, 0, 1) ** 2.0 * op).astype(np.uint8)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = 74, 66, 56
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


def draw_sub(d, text):
    d.text((W // 2, 992), text, font=font(56), fill=(30, 28, 26), anchor="mm",
           stroke_width=5, stroke_fill=(255, 255, 255, 232))
    d.text((W // 2, 992), text, font=font(56), fill=(30, 28, 26), anchor="mm")


def compose(wall, t, stk, shadow, v, title=None, desc=None):
    lo = bg_from_wall(wall, t)
    big = Image.fromarray(np.clip(lo, 0, 255).astype(np.uint8), "RGB").resize((W, H), Image.LANCZOS)
    frame = big.convert("RGBA")

    br = 1.0 + 0.006 * math.sin(t * 2.4)
    s = stk.resize((max(8, int(stk.width * br)), max(8, int(stk.height * br))), Image.BILINEAR) \
        if abs(br - 1.0) > 1e-4 else stk
    cx = W // 2
    frame.alpha_composite(shadow, (cx - shadow.width // 2, BASE_Y - shadow.height // 2))
    frame.alpha_composite(s, (cx - s.width // 2, BASE_Y - s.height))

    d = ImageDraw.Draw(frame)
    draw_sub(d, SUB_TEXT)
    if title:
        dark_label = sum(v["label"]) > 380      # 深色底用浅字，白描边收掉
        sw, sf = (0, None) if dark_label else (4, (255, 255, 255, 220))
        d.text((70, 58), title, font=font(54), fill=v["label"], stroke_width=sw, stroke_fill=sf)
        if desc:
            sw2, sf2 = (0, None) if dark_label else (3, (255, 255, 255, 200))
            d.text((72, 126), desc, font=font(30), fill=v["label"], stroke_width=sw2, stroke_fill=sf2)
    return frame


def main():
    os.makedirs(os.path.join(ROOT, "frames"), exist_ok=True)
    stk = load_sticker(os.path.join(CUT, "角色", "展示_半蹲发力浅色_全身.png"), 830)
    sh_w = int(stk.width * 0.52)
    shadow = make_shadow((sh_w, max(12, int(sh_w * 0.16))))

    walls = {}
    tiles = []
    for v in VARIANTS:
        wall = build_wall(v)
        walls[v["id"]] = wall
        f = compose(wall, 1.4, stk, shadow, v, "  ".join([v["id"], v["name"]]))
        p = os.path.join(ROOT, "frames", "wc_%s.jpg" % v["id"])
        f.convert("RGB").save(p, quality=94)
        tiles.append(f.convert("RGB").resize((W // 2, H // 2), Image.LANCZOS))
        print("  still →", p)

    sheet = Image.new("RGB", (W // 2 * 3 + 16, H // 2 * 2 + 8), (255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 3) * (W // 2 + 8), (i // 3) * (H // 2 + 8)))
    sheet.save(os.path.join(ROOT, "out", "漫画墙_配色总览.jpg"), quality=93)
    print("→ out/漫画墙_配色总览.jpg")

    render_video(walls, stk, shadow)


def render_video(walls, stk, shadow):
    """动态片：先把整面墙放大一次，每帧只做裁切，不再逐帧缩放（快 6 倍）"""
    SEG_S = 3.4
    per = int(SEG_S * FPS)
    total = per * len(VARIANTS)

    BIG_W, BIG_H = 2880, 1620
    big_walls = {k: v.resize((BIG_W, BIG_H), Image.LANCZOS) for k, v in walls.items()}

    yy2, xx2 = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = np.sqrt((xx2 - W * 0.5) ** 2 / (W * 0.78) ** 2 + (yy2 - H * 0.42) ** 2 / (H * 0.78) ** 2)
    VIG = (1.0 - 0.055 * r2 ** 1.4)[..., None].astype(np.float32)

    rng = np.random.default_rng(7)
    NOISE = [rng.normal(0, 3.0, (H // 2, W // 2)).astype(np.int16) for _ in range(4)]
    NOISE = [np.repeat(np.repeat(n, 2, axis=0), 2, axis=1)[:H, :W].astype(np.float32) for n in NOISE]

    out_path = os.path.join(ROOT, "out", "漫画墙_配色对比_V1.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    fi = 0
    for v in VARIANTS:
        wall = big_walls[v["id"]]
        for k in range(per):
            t = k / float(FPS)
            ox = 480 + 220 * math.sin(t * 0.26)
            oy = 270 + 140 * math.cos(t * 0.21)
            crop = wall.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))
            arr = np.asarray(crop).astype(np.float32)
            arr *= VIG
            arr += NOISE[fi % len(NOISE)][..., None]
            frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

            br = 1.0 + 0.006 * math.sin(t * 2.4)
            s = stk.resize((max(8, int(stk.width * br)), max(8, int(stk.height * br))), Image.BILINEAR) \
                if abs(br - 1.0) > 1e-4 else stk
            frame.alpha_composite(shadow, (W // 2 - shadow.width // 2, BASE_Y - shadow.height // 2))
            frame.alpha_composite(s, (W // 2 - s.width // 2, BASE_Y - s.height))

            d = ImageDraw.Draw(frame)
            draw_sub(d, SUB_TEXT)
            dark_label = sum(v["label"]) > 380
            sw = 0 if dark_label else 4
            d.text((70, 58), "  ".join([v["id"], v["name"]]), font=font(54),
                   fill=v["label"], stroke_width=sw,
                   stroke_fill=None if dark_label else (255, 255, 255, 220))

            proc.stdin.write(frame.convert("RGB").tobytes())
            fi += 1
        print("  %s done (%d/%d)" % (v["id"], fi, total), flush=True)

    proc.stdin.close()
    proc.wait()
    print("→", out_path)


if __name__ == "__main__":
    main()
