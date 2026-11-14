#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
漫画分格墙 · 深底版
浅纸漫画墙的问题：底太亮，绿色小人压不住画面。
这里把同样的分格墙做成深底，格线改成「发光缝」，让墙退到后面、人跳到前面。

6 版：
  W1 深炭·暖格线     基准
  W2 深炭·主光移动    基准 + 一道慢移柔光（最耐看）
  W3 冷墨蓝          冷调，讲成分/原理时更"科技"
  W4 墨线稿          极高对比，几乎只有轮廓，最漫画
  W5 深炭·色斑       基准 + 环境色斑（最不空）
  W6 暖纸压暗        P4 暖纸米墙直接压暗（保留纸质感，但不过曝）
"""
import os, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = "/Volumes/素材库/广告视频/_样片_信息卡_261101"
CUT = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库"
GAL = "/Volumes/素材库/广告视频/分镜图库/小绿人"
FONT = "/Users/yourname/.workbuddy/skills/koubo-ad-video/assets/fonts/STHeiti Medium.ttc"

W, H, FPS = 1920, 1080, 30
BASE_Y = 970
SUB_TEXT = "很多兄弟训练完，只顾猛冲高碳水跟高蛋白。"

CW, CH = 600, 338
GRID_N = 4
WALL_W, WALL_H = CW * GRID_N, CH * GRID_N      # 2400 x 1352
BIG_W, BIG_H = 2880, 1620

_CSS = ()


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

_CELLS = []


def load_cells():
    global _CELLS
    if _CELLS:
        return _CELLS
    for name in WALL_SRC:
        p = os.path.join(GAL, name)
        if not os.path.exists(p):
            print("  !! missing", name)
            _CELLS.append(Image.new("RGB", (CW, CH), (40, 38, 35)))
            continue
        im = Image.open(p).convert("RGB")
        sc = max(CW / im.width, CH / im.height)
        im = im.resize((max(CW, int(im.width * sc)), max(CH, int(im.height * sc))), Image.LANCZOS)
        x, y = (im.width - CW) // 2, (im.height - CH) // 2
        _CELLS.append(im.crop((x, y, x + CW, y + CH)))
    return _CELLS


def norm_lum(im, mean, std, gamma=1.0):
    """逐格归一化亮度：16 张原图明暗差极大，不逐格拉齐就会斑驳发脏"""
    g = np.asarray(im.convert("L")).astype(np.float32) / 255.0
    sd = float(g.std())
    g = mean + (g - float(g.mean())) * (std / max(sd, 1e-3))
    return np.clip(g, 0.0, 1.0) ** gamma


def tone_duo(im, dark, light, mean, std, gamma=1.0):
    g = norm_lum(im, mean, std, gamma)
    d = np.array(dark, np.float32)
    l = np.array(light, np.float32)
    return d + (l - d) * g[..., None]


def pick_spotlight(i, total=16):
    """给一小部分格子轻微提亮 —— 像有几块墙面被打到光，避免整墙平均"""
    return 1.0 + (0.34 if i % 5 == 2 else 0.0) + (0.18 if i == 7 else 0.0)


def build_wall(v):
    if v.get("tilt"):
        return build_wall_tilt(v)
    wall = Image.new("RGB", (WALL_W, WALL_H), tuple(v["gutter"]))
    cells = load_cells()
    for i, cell in enumerate(cells):
        if v["fn"] == "press":
            arr = tone_press(cell, v)
        else:
            arr = tone_duo(cell, v["dark"], v["light"], v["mean"], v["std"], v.get("gamma", 1.0))
            arr = arr * v.get("gain_grid", 1.0)
        arr = np.clip(arr * pick_spotlight(i) * v.get("gain", 1.0), 0, 255).astype(np.uint8)
        wall.paste(Image.fromarray(arr, "RGB"), (CW * (i % GRID_N), CH * (i // GRID_N)))

    # 格缝：黑沟 + 内嵌发光细线 + 柔晕
    glow = Image.new("RGB", (WALL_W, WALL_H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for c in range(1, GRID_N):
        gd.line([(CW * c, 0), (CW * c, WALL_H)], fill=v["glow"], width=5)
        gd.line([(0, CH * c), (WALL_W, CH * c)], fill=v["glow"], width=5)
    small = glow.resize((WALL_W // 8, WALL_H // 8), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(3))
    glow = small.resize((WALL_W, WALL_H), Image.BILINEAR)

    a = np.asarray(wall).astype(np.float32)
    a += np.asarray(glow).astype(np.float32) * v.get("glow_amt", 0.55)
    wall = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")

    d = ImageDraw.Draw(wall)
    for c in range(1, GRID_N):          # 黑沟压边
        d.line([(CW * c, 0), (CW * c, WALL_H)], fill=v["gutter"], width=v.get("gut", 9))
        d.line([(0, CH * c), (WALL_W, CH * c)], fill=v["gutter"], width=v.get("gut", 9))
    for c in range(1, GRID_N):          # 发光细线
        d.line([(CW * c, 0), (CW * c, WALL_H)], fill=v["line"], width=2)
        d.line([(0, CH * c), (WALL_W, CH * c)], fill=v["line"], width=2)

    return wall.resize((1440, 810), Image.LANCZOS)


def build_wall_tilt(v):
    """斜贴分格：每格轻微旋转 + 压边，像贴满墙的分镜小卡，不是规整壁纸"""
    wall = Image.new("RGB", (WALL_W, WALL_H), tuple(v["gutter"]))
    cells = load_cells()
    angs = [-4.6, 3.2, -2.4, 4.4, -3.4, 2.6, 4.8, -2.8,
            3.6, -4.2, 2.2, -3.0, -2.2, 4.2, -4.8, 3.0]
    for i, cell in enumerate(cells):
        arr = tone_duo(cell, v["dark"], v["light"], v["mean"], v["std"], v.get("gamma", 1.0))
        arr = np.clip(arr * pick_spotlight(i) * v.get("gain", 1.0), 0, 255).astype(np.uint8)
        c = Image.fromarray(arr, "RGB").resize((int(CW * 1.16), int(CH * 1.16)), Image.LANCZOS)
        rim = Image.new("RGB", (c.width + 6, c.height + 6), tuple(v["line"]))
        rim.paste(c, (3, 3))
        r = rim.rotate(angs[i % len(angs)], resample=Image.BICUBIC, expand=False)
        wall.paste(r, (CW * (i % GRID_N) + CW // 2 - r.width // 2,
                       CH * (i // GRID_N) + CH // 2 - r.height // 2))
    return wall.resize((1440, 810), Image.LANCZOS)


def tone_press(cell, v):
    """暖纸米墙直接压暗：保留纸质底色，只是整体降下来"""
    g = norm_lum(cell, v.get("mean", 0.80), v.get("std", 0.115))
    d = np.array([44, 41, 37], np.float32)
    l = np.array([176, 167, 150], np.float32)
    base = d + (l - d) * g[..., None]
    return base * v.get("press", 0.62)


VARIANTS = [
    dict(id="W1", name="深炭·暖格线", fn="duo",
         dark=(10, 9, 8), light=(122, 110, 94), mean=0.26, std=0.155,
         gutter=(8, 7, 7), glow=(120, 96, 60), glow_amt=0.75,
         line=(226, 206, 172), gut=9, label=(246, 241, 231)),
    dict(id="W2", name="深炭·主光移动", fn="duo", ambient="spot",
         dark=(10, 9, 8), light=(122, 110, 94), mean=0.26, std=0.155,
         gutter=(8, 7, 7), glow=(120, 96, 60), glow_amt=0.75,
         line=(226, 206, 172), gut=9, label=(246, 241, 231)),
    dict(id="W3", name="冷墨蓝", fn="duo",
         dark=(8, 10, 14), light=(96, 112, 132), mean=0.25, std=0.15,
         gutter=(7, 8, 11), glow=(52, 78, 118), glow_amt=0.85,
         line=(186, 206, 232), gut=9, label=(238, 243, 250)),
    dict(id="W4", name="墨线稿", fn="duo", gamma=2.1,
         dark=(6, 6, 6), light=(168, 158, 141), mean=0.30, std=0.20,
         gutter=(0, 0, 0), glow=(96, 78, 52), glow_amt=0.55,
         line=(230, 214, 186), gut=11, label=(248, 244, 236)),
    dict(id="W5", name="深炭·色斑", fn="duo", ambient="blobs",
         dark=(10, 9, 8), light=(116, 104, 88), mean=0.24, std=0.15,
         gutter=(8, 7, 7), glow=(120, 96, 60), glow_amt=0.70,
         line=(220, 200, 168), gut=9, label=(246, 241, 231)),
    dict(id="W6", name="暖纸压暗", fn="press", press=0.66,
         gutter=(24, 22, 18), glow=(110, 92, 66), glow_amt=0.40,
         line=(186, 174, 152), gut=7, label=(246, 241, 231)),
    dict(id="W7", name="斜贴分格", fn="duo", tilt=True, ambient="spot",
         dark=(9, 8, 8), light=(126, 114, 98), mean=0.25, std=0.15,
         gutter=(6, 6, 6), glow=(0, 0, 0), glow_amt=0.0,
         line=(168, 150, 120), gut=0, label=(246, 241, 231)),
]

# ---------------- 环境光（屏幕空间低分辨率 → 放大） ----------------

GX, GY = 320, 180
gy, gx = np.mgrid[0:GY, 0:GX].astype(np.float32)
GNX, GNY = gx / GX, gy / GY


def _lo_blob(cx, cy, rad, amp, tint):
    d2 = (GNX - cx) ** 2 * (GX / GY) ** 2 + (GNY - cy) ** 2
    w = np.exp(-d2 / (2 * rad * rad)) * amp
    return w[..., None] * np.array(tint, np.float32)[None, None, :]


def glow_spot(t):
    out = np.zeros((GY, GX, 3), np.float32)
    out += _lo_blob(0.50 + 0.16 * math.sin(t * 0.28), 0.34 + 0.10 * math.cos(t * 0.22),
                    0.30, 1.0, (52, 34, 14))
    return out


def glow_blobs(t):
    out = np.zeros((GY, GX, 3), np.float32)
    out += _lo_blob(0.28 + 0.06 * math.sin(t * 0.40), 0.36 + 0.05 * math.cos(t * 0.34),
                    0.26, 1.0, (46, 30, 12))
    out += _lo_blob(0.74 + 0.05 * math.cos(t * 0.31), 0.64 + 0.06 * math.sin(t * 0.37),
                    0.28, 0.55, (8, 24, 16))
    out += _lo_blob(0.55 + 0.07 * math.sin(t * 0.25 + 1.1), 0.16 + 0.05 * math.cos(t * 0.29),
                    0.24, 0.75, (12, 20, 44))
    return out


AMBIENT = {"spot": glow_spot, "blobs": glow_blobs}


def ambient_layer(fn, t):
    """低分辨率算好 → 放大成 (H,W,3) uint8 加法层"""
    lo = np.clip(fn(t), 0, 32).astype(np.float32)
    ch = []
    for c in range(3):
        im = Image.fromarray(np.clip(lo[..., c] / 32.0 * 255.0, 0, 255).astype(np.uint8), "L")
        ch.append(np.asarray(im.resize((W, H), Image.BILINEAR)).astype(np.float32) / 255.0 * 32.0)
    return np.stack(ch, axis=2)


# ---------------- 贴纸 / 字幕 ----------------

def load_sticker(path, height):
    im = Image.open(path).convert("RGBA")
    w = max(8, int(round(im.width * height / im.height)))
    return im.resize((w, height), Image.LANCZOS)


def make_shadow(size, op=95):
    w, h = max(8, int(size[0])), max(8, int(size[1]))
    yy2, xx2 = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    r = np.sqrt(((xx2 - cx) / (w / 2.0)) ** 2 + ((yy2 - cy) / (h / 2.0)) ** 2)
    a = (np.clip(1.0 - r, 0, 1) ** 2.0 * op).astype(np.uint8)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = 6, 6, 6
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


def draw_sub(d, text):
    d.text((W // 2, 996), text, font=font(58), fill=(6, 6, 6), anchor="mm",
           stroke_width=10, stroke_fill=(6, 6, 6, 120))
    d.text((W // 2, 992), text, font=font(58), fill=(252, 250, 244), anchor="mm",
           stroke_width=6, stroke_fill=(12, 12, 12, 255))
    d.text((W // 2, 992), text, font=font(58), fill=(252, 250, 244), anchor="mm")


def compose_still(wall, t, stk, shadow, v, title, desc):
    big = wall.resize((BIG_W, BIG_H), Image.LANCZOS)
    ox = 480 + 220 * math.sin(t * 0.26)
    oy = 270 + 140 * math.cos(t * 0.21)
    crop = big.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))
    arr = np.asarray(crop).astype(np.float32)
    fn = AMBIENT.get(v.get("ambient", ""))
    if fn:
        arr += ambient_layer(fn, t)
    frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    frame.alpha_composite(shadow, (W // 2 - shadow.width // 2, BASE_Y - shadow.height // 2))
    frame.alpha_composite(stk, (W // 2 - stk.width // 2, BASE_Y - stk.height))
    d = ImageDraw.Draw(frame)
    draw_sub(d, SUB_TEXT)
    d.text((70, 56), title, font=font(54), fill=v["label"])
    d.text((72, 124), desc, font=font(30), fill=tuple(int(c * 0.72) for c in v["label"]))
    return frame


def main():
    os.makedirs(os.path.join(ROOT, "frames"), exist_ok=True)
    stk = load_sticker(os.path.join(CUT, "角色", "展示_半蹲发力浅色_全身.png"), 810)
    sh_w = int(stk.width * 0.52)
    shadow = make_shadow((sh_w, max(12, int(sh_w * 0.16))))

    walls, tiles = {}, []
    for v in VARIANTS:
        wall = build_wall(v)
        walls[v["id"]] = wall
        f = compose_still(wall, 1.4, stk, shadow, v, "%s  %s" % (v["id"], v["name"]), "深底漫画分格墙")
        p = os.path.join(ROOT, "frames", "wd_%s.jpg" % v["id"])
        f.convert("RGB").save(p, quality=94)
        tiles.append(f.convert("RGB").resize((W // 2, H // 2), Image.LANCZOS))
        print("  still →", p)

    sheet = Image.new("RGB", (W // 2 * 3 + 16, H // 2 * 2 + 8), (16, 15, 14))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 3) * (W // 2 + 8), (i // 3) * (H // 2 + 8)))
    sheet.save(os.path.join(ROOT, "out", "漫画墙_深底_总览.jpg"), quality=93)
    print("→ out/漫画墙_深底_总览.jpg")

    render_video(walls, stk, shadow)


def render_video(walls, stk, shadow):
    SEG = 4.0
    per = int(SEG * FPS)
    total = per * len(VARIANTS)

    big_walls = {k: v.resize((BIG_W, BIG_H), Image.LANCZOS) for k, v in walls.items()}

    yy2, xx2 = np.mgrid[0:H, 0:W].astype(np.float32)
    RAD = np.sqrt((xx2 - W * 0.5) ** 2 / (W * 0.82) ** 2 + (yy2 - H * 0.44) ** 2 / (H * 0.82) ** 2)
    VIG = (1.0 - 0.16 * RAD ** 1.5)[..., None].astype(np.float32)

    rng = np.random.default_rng(11)
    NOISE = []
    for _ in range(6):
        n = rng.normal(0, 3.0, (H // 2, W // 2)).astype(np.float32)
        NOISE.append(np.asarray(Image.fromarray(
            np.clip(128 + n, 0, 255).astype(np.uint8), "L").resize((W, H), Image.BILINEAR)
        ).astype(np.float32) - 128.0)

    out_path = os.path.join(ROOT, "out", "漫画墙_深底_对比_V1.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    fi = 0
    for v in VARIANTS:
        wall = big_walls[v["id"]]
        fn = AMBIENT.get(v.get("ambient", ""))
        for k in range(per):
            t = k / float(FPS)
            ox = 480 + 220 * math.sin(t * 0.26)
            oy = 270 + 140 * math.cos(t * 0.21)
            crop = wall.crop((int(ox), int(oy), int(ox) + W, int(oy) + H))
            arr = np.asarray(crop).astype(np.float32)
            if fn:
                arr += ambient_layer(fn, t)
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
            d.text((70, 56), "%s  %s" % (v["id"], v["name"]), font=font(54), fill=v["label"])

            proc.stdin.write(frame.convert("RGB").tobytes())
            fi += 1
        print("  %s ok (%d/%d)" % (v["id"], fi, total), flush=True)

    proc.stdin.close()
    proc.wait()
    print("→", out_path)


if __name__ == "__main__":
    main()
