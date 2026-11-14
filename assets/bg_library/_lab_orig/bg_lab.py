#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态背景实验室：5 种纯程序生成的「活」背景，各 4 秒，拼成一条对比片。
全部 numpy 直出，零素材、零 Remotion，8GB 内存友好。
"""
import os, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = "/Volumes/素材库/广告视频/_样片_信息卡_261101"
CUT = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库"
FONT = "/Users/yourname/.workbuddy/skills/koubo-ad-video/assets/fonts/STHeiti Medium.ttc"

W, H, FPS = 1920, 1080, 30
LW, LH = 960, 540          # 背景层工作分辨率（4 倍缩小后再放大）
SEG = 4.0                  # 每段时长
BASE = np.array([241, 237, 227], np.float32)
BASE_Y = 970
SUB_TEXT = "很多兄弟训练完，只顾猛冲高碳水跟高蛋白。"

yy, xx = np.mgrid[0:LH, 0:LW].astype(np.float32)
NX = xx / LW
NY = yy / LH


def font(sz):
    return ImageFont.truetype(FONT, sz)


# ---------------- 背景层动效 ----------------

def _radial():
    cx, cy = LW * 0.5, LH * 0.42
    r = np.sqrt(((xx - cx) / (LW * 0.78)) ** 2 + ((yy - cy) / (LH * 0.78)) ** 2)
    return r


RAD = _radial()


def base_layer():
    g = np.clip(1.03 - 0.085 * RAD ** 1.6, 1.0, 1.03)
    return BASE[None, None, :] * g[..., None]


def _blob(cx, cy, rad, amp, tint):
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    w = np.exp(-d2 / (2 * rad * rad)) * amp
    return w[..., None] * np.array(tint, np.float32)[None, None, :]


def bg_blobs(t):
    """A 色斑漂移：三个同色系色斑缓慢游动"""
    out = base_layer()
    out += _blob(LW * (0.30 + 0.06 * math.sin(t * 0.45)),
                 LH * (0.34 + 0.05 * math.cos(t * 0.38)),
                 LW * 0.34, 5.2, (5, 4, 0))
    out += _blob(LW * (0.72 + 0.05 * math.cos(t * 0.33)),
                 LH * (0.62 + 0.06 * math.sin(t * 0.41)),
                 LW * 0.36, 4.4, (-3, -2, 4))
    out += _blob(LW * (0.52 + 0.07 * math.sin(t * 0.27 + 1.2)),
                 LH * (0.18 + 0.05 * math.cos(t * 0.31)),
                 LW * 0.30, 3.6, (4, 3, -3))
    return out


def _grid(period, thick, offset, strength):
    """抗锯齿网格线（周期 period，线宽 thick，整体偏移 offset）"""
    fx = np.abs(((xx + offset) % period) - period * 0.5)
    fy = np.abs(((yy + offset * 0.6) % period) - period * 0.5)
    lx = np.clip((period * 0.5 - fx) / thick, 0, 1)
    ly = np.clip((period * 0.5 - fy) / thick, 0, 1)
    return np.maximum(lx, ly) * strength


def bg_grid(t):
    """B 工程网格：两层细网格缓慢斜向漂移"""
    out = base_layer()
    off = (t * 9.0) % 200.0                     # 10 秒漂一格
    g1 = _grid(60.0, 2.2, off, 1.0)
    g2 = _grid(180.0, 3.0, off * 0.6, 1.0)
    shade = (g1 * 6.5 + g2 * 5.0)[..., None]
    out -= shade * np.array([1.0, 0.95, 0.85], np.float32)[None, None, :]
    return out


def bg_sweep(t):
    """C 光线扫：45° 柔光带每 7 秒扫一次"""
    out = base_layer()
    phase = (t % 4.0) / 4.0
    c = -0.5 + phase * 1.8
    u = (NX * 0.707 + NY * 0.707)
    band = np.exp(-((u - c) ** 2) / (2 * 0.10 ** 2))
    out += (band * 34.0)[..., None] * np.array([1.0, 0.99, 0.96], np.float32)[None, None, :]
    return out


def bg_speed(t):
    """D 速度线：从中心向外的放射细线，缓慢旋转 + 呼吸"""
    out = base_layer()
    dx = (xx - LW * 0.5)
    dy = (yy - LH * 0.44)
    ang = np.arctan2(dy, dx) + t * 0.055
    n = 44
    s = np.sin(ang * n)
    line = np.clip(s, 0, 1) ** 6.0
    # 越靠外越淡（避免线条穿过人物身体）
    rad = np.sqrt(dx ** 2 + dy ** 2) / (LW * 0.6)
    edge = np.clip((rad - 0.22) / 0.5, 0, 1)
    breath = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 1.1))
    out -= (line * edge * 5.2 * breath)[..., None] * np.array([1.0, 0.96, 0.88], np.float32)[None, None, :]
    return out


def bg_mix(t):
    """E 组合：色斑 + 光扫 + 极淡速度线（克制的全套）"""
    out = bg_blobs(t)
    phase = (t % 5.0) / 5.0
    c = -0.5 + phase * 1.8
    u = (NX * 0.707 + NY * 0.707)
    band = np.exp(-((u - c) ** 2) / (2 * 0.11 ** 2))
    out += (band * 24.0)[..., None] * np.array([1.0, 0.99, 0.96], np.float32)[None, None, :]
    dx = (xx - LW * 0.5)
    dy = (yy - LH * 0.44)
    ang = np.arctan2(dy, dx) + t * 0.04
    line = np.clip(np.sin(ang * 36), 0, 1) ** 8.0
    rad = np.sqrt(dx ** 2 + dy ** 2) / (LW * 0.6)
    edge = np.clip((rad - 0.28) / 0.5, 0, 1)
    out -= (line * edge * 3.0)[..., None] * np.array([1.0, 0.96, 0.88], np.float32)[None, None, :]
    return out




# ---------------- F 漫画分格墙 ----------------

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

GAL = "/Volumes/素材库/广告视频/分镜图库/小绿人"
_WALL = None


def build_wall():
    """把 16 张分镜图拼成 4x4 的漫画墙，压成「淡纹理」而不是照片"""
    CW, CH = 600, 338
    wall = Image.new("RGB", (CW * 4, CH * 4), tuple(int(v) for v in BASE))
    for i, name in enumerate(WALL_SRC):
        p = os.path.join(GAL, name)
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB")
        sc = max(CW / im.width, CH / im.height)
        im = im.resize((max(CW, int(im.width * sc)), max(CH, int(im.height * sc))), Image.LANCZOS)
        x, y = (im.width - CW) // 2, (im.height - CH) // 2
        im = im.crop((x, y, x + CW, y + CH))
        g = np.asarray(im.convert("L")).astype(np.float32)
        g = 234 + (g - float(g.mean())) * 0.27          # 压扁对比度，变成很淡的纹理
        im = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), "L").convert("RGB")
        wall.paste(im, (CW * (i % 4), CH * (i // 4)))
    # 格线：白粗线 + 浅灰细线，做出「分格」而不是「拼图」
    d = ImageDraw.Draw(wall)
    for c in range(1, 4):
        d.line([(CW * c, 0), (CW * c, wall.height)], fill=(252, 250, 244), width=7)
        d.line([(0, CH * c), (wall.width, CH * c)], fill=(252, 250, 244), width=7)
    for c in range(1, 4):
        d.line([(CW * c, 0), (CW * c, wall.height)], fill=(206, 200, 188), width=1)
        d.line([(0, CH * c), (wall.width, CH * c)], fill=(206, 200, 188), width=1)
    return wall


def bg_collage(t):
    global _WALL
    if _WALL is None:
        _WALL = build_wall().resize((1440, 810), Image.LANCZOS)
    ox = 240 + 110 * math.sin(t * 0.26)          # 缓慢对角漂移
    oy = 135 + 70 * math.cos(t * 0.21)
    crop = _WALL.crop((int(ox), int(oy), int(ox) + LW, int(oy) + LH))
    arr = np.asarray(crop).astype(np.float32)
    arr = arr * (1.0 - 0.055 * RAD[..., None] ** 1.4)     # 轻度暗角，压住边缘格子
    return arr


# ---------------- 贴纸 / 字幕 ----------------

def load_sticker(path, height):
    im = Image.open(path).convert("RGBA")
    h = height
    w = max(8, int(round(im.width * h / im.height)))
    return im.resize((w, h), Image.LANCZOS)


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


def draw_sub(d, text, alpha=255):
    sz = 56
    f = font(sz)
    col = (30, 28, 26, alpha)
    d.text((W // 2, 992), text, font=f, fill=col, anchor="mm",
           stroke_width=5, stroke_fill=(255, 255, 255, int(alpha * 0.88)))
    d.text((W // 2, 992), text, font=f, fill=col, anchor="mm")


# ---------------- 主流程 ----------------

SCENES = [
    ("A  色斑漂移", bg_blobs, "三个同色系色斑缓慢游动 · 最保守"),
    ("B  工程网格", bg_grid, "两层细网格斜向漂移 · 讲成分/数据时最搭"),
    ("C  光线扫", bg_sweep, "45° 柔光每 4 秒扫一次 · 高级感，最不抢"),
    ("F  漫画分格墙", bg_collage, "16 张分镜图拼成墙，缓慢漂移 · 最接近参考图"),
    ("D  速度线", bg_speed, "中心放射细线，缓慢旋转呼吸 · 力量感最强"),
    ("E  全套组合", bg_mix, "色斑 + 光扫 + 淡速度线 · 信息密度最高"),
]


def main():
    stk = load_sticker(os.path.join(CUT, "角色", "展示_半蹲发力浅色_全身.png"), 830)
    sh_w = int(stk.width * 0.52)
    shadow = make_shadow((sh_w, max(12, int(sh_w * 0.16))))

    rng = np.random.default_rng(11)
    NOISE = []
    for _ in range(8):
        n = rng.normal(0, 3.0, (H // 2, W // 2)).astype(np.float32)
        NOISE.append(np.asarray(Image.fromarray(
            np.clip(128 + n, 0, 255).astype(np.uint8), "L"
        ).resize((W, H), Image.BILINEAR)).astype(np.float32) - 128.0)
    per = int(SEG * FPS)
    total = per * len(SCENES)

    out_path = os.path.join(ROOT, "out", "动态背景_对比_V1.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    fi = 0
    for name, fn, desc in SCENES:
        for k in range(per):
            t = k / float(FPS)

            lo = fn(t)
            lo8 = np.clip(lo, 0, 255).astype(np.uint8)
            big = Image.fromarray(lo8, "RGB").resize((W, H), Image.LANCZOS)
            frame = big.convert("RGBA")

            # 颗粒（逐帧变化，静态变活的另一半功劳）
            arr = np.asarray(frame).astype(np.float32)
            arr[..., :3] += NOISE[fi % len(NOISE)][..., None]
            frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

            # 贴纸呼吸
            br = 1.0 + 0.006 * math.sin(t * 2.4)
            s = stk.resize((max(8, int(stk.width * br)), max(8, int(stk.height * br))), Image.BILINEAR) \
                if abs(br - 1.0) > 1e-4 else stk
            cx = W // 2
            sx = cx - s.width // 2
            sy = BASE_Y - s.height
            frame.alpha_composite(shadow, (cx - shadow.width // 2, BASE_Y - shadow.height // 2))
            frame.alpha_composite(s, (sx, sy))

            d = ImageDraw.Draw(frame)
            draw_sub(d, SUB_TEXT)
            d.text((70, 60), name, font=font(52), fill=(34, 58, 44),
                   stroke_width=4, stroke_fill=(255, 255, 255, 220))
            d.text((72, 126), desc, font=font(30), fill=(96, 104, 96),
                   stroke_width=3, stroke_fill=(255, 255, 255, 200))

            proc.stdin.write(frame.convert("RGB").tobytes())
            fi += 1
            if fi % 120 == 0:
                print("  %d/%d" % (fi, total), flush=True)

    proc.stdin.close()
    proc.wait()
    print("→", out_path)


if __name__ == "__main__":
    main()
