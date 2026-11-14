#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态背景 · 深底版
原来的 5 种效果是按浅色底调的（色斑只加 4~5 个亮度值、网格是减法），
在暖米底上等于看不见。这里换深底，并把所有效果改成「加法发光」。
"""
import os, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = "/Volumes/素材库/广告视频/_样片_信息卡_261101"
CUT = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库"
FONT = "/Users/yourname/.workbuddy/skills/koubo-ad-video/assets/fonts/STHeiti Medium.ttc"

W, H, FPS = 1920, 1080, 30
LW, LH = 960, 540
BASE_Y = 970
BASE = np.array([22, 21, 20], np.float32)     # 深炭（微暖，不是死黑）
SUB_TEXT = "很多兄弟训练完，只顾猛冲高碳水跟高蛋白。"

yy, xx = np.mgrid[0:LH, 0:LW].astype(np.float32)
NX = xx / LW
NY = yy / LH
_cx, _cy = LW * 0.5, LH * 0.42
RAD = np.sqrt((xx - _cx) ** 2 / (LW * 0.80) ** 2 + (yy - _cy) ** 2 / (LH * 0.80) ** 2)


def font(sz):
    return ImageFont.truetype(FONT, sz)


def base_layer():
    # 中心亮一点、四周压暗，深底才不会像一块黑板
    g = np.clip(1.28 - 0.30 * RAD ** 1.5, 0.62, 1.30)
    return BASE[None, None, :] * g[..., None]


def _blob(cx, cy, rad, amp, tint):
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    w = np.exp(-d2 / (2 * rad * rad)) * amp
    return w[..., None] * np.array(tint, np.float32)[None, None, :]


def bg_blobs(t):
    """A 色斑漂移：三团发光色斑缓慢游动"""
    out = base_layer()
    out += _blob(LW * (0.30 + 0.06 * math.sin(t * 0.45)),
                 LH * (0.34 + 0.05 * math.cos(t * 0.38)),
                 LW * 0.34, 1.0, (66, 46, 22))          # 暖橙
    out += _blob(LW * (0.72 + 0.05 * math.cos(t * 0.33)),
                 LH * (0.62 + 0.06 * math.sin(t * 0.41)),
                 LW * 0.36, 1.0, (16, 50, 28))          # 墨绿
    out += _blob(LW * (0.52 + 0.07 * math.sin(t * 0.27 + 1.2)),
                 LH * (0.18 + 0.05 * math.cos(t * 0.31)),
                 LW * 0.30, 1.0, (20, 28, 58))          # 冷蓝
    return out


def _grid(period, thick, offset, strength):
    fx = np.abs(((xx + offset) % period) - period * 0.5)
    fy = np.abs(((yy + offset * 0.6) % period) - period * 0.5)
    lx = np.clip((period * 0.5 - fx) / thick, 0, 1)
    ly = np.clip((period * 0.5 - fy) / thick, 0, 1)
    return np.maximum(lx, ly) * strength


def bg_grid(t):
    """B 工程网格：两层细网格缓慢斜向漂移（深底上改为加法发光）"""
    out = base_layer()
    off = (t * 9.0) % 200.0
    g1 = _grid(60.0, 2.2, off, 1.0)
    g2 = _grid(180.0, 3.0, off * 0.6, 1.0)
    shade = (g1 * 38.0 + g2 * 30.0)[..., None]
    out += shade * np.array([0.90, 1.0, 1.05], np.float32)[None, None, :]
    return out


def bg_sweep(t):
    """C 光线扫：45° 柔光带每 4 秒扫一次（深底上最出效果）"""
    out = base_layer()
    phase = (t % 4.0) / 4.0
    c = -0.5 + phase * 1.8
    u = (NX * 0.707 + NY * 0.707)
    band = np.exp(-((u - c) ** 2) / (2 * 0.10 ** 2))
    out += (band * 62.0)[..., None] * np.array([1.0, 0.96, 0.88], np.float32)[None, None, :]
    return out


def bg_speed(t):
    """D 速度线：中心放射细线，缓慢旋转 + 呼吸"""
    out = base_layer()
    dx = (xx - LW * 0.5)
    dy = (yy - LH * 0.44)
    ang = np.arctan2(dy, dx) + t * 0.055
    line = np.clip(np.sin(ang * 44), 0, 1) ** 6.0
    rad = np.sqrt(dx ** 2 + dy ** 2) / (LW * 0.6)
    edge = np.clip((rad - 0.20) / 0.5, 0, 1)
    breath = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 1.1))
    out += (line * edge * 44.0 * breath)[..., None] * np.array([1.0, 0.95, 0.85], np.float32)[None, None, :]
    return out


def bg_mix(t):
    """E 全套组合：色斑 + 光扫 + 淡速度线"""
    out = bg_blobs(t)
    phase = (t % 5.0) / 5.0
    c = -0.5 + phase * 1.8
    u = (NX * 0.707 + NY * 0.707)
    band = np.exp(-((u - c) ** 2) / (2 * 0.11 ** 2))
    out += (band * 40.0)[..., None] * np.array([1.0, 0.98, 0.94], np.float32)[None, None, :]
    dx = (xx - LW * 0.5)
    dy = (yy - LH * 0.44)
    ang = np.arctan2(dy, dx) + t * 0.04
    line = np.clip(np.sin(ang * 36), 0, 1) ** 8.0
    rad = np.sqrt(dx ** 2 + dy ** 2) / (LW * 0.6)
    edge = np.clip((rad - 0.28) / 0.5, 0, 1)
    out += (line * edge * 26.0)[..., None] * np.array([1.0, 0.95, 0.85], np.float32)[None, None, :]
    return out


def bg_flat(t):
    """0 纯深底：什么都不加，作为对照（告诉你「死板」长什么样）"""
    return base_layer()


# ---------------- 贴纸 / 字幕 ----------------

def load_sticker(path, height):
    im = Image.open(path).convert("RGBA")
    w = max(8, int(round(im.width * height / im.height)))
    return im.resize((w, height), Image.LANCZOS)


def make_shadow(size, op=90):
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
    """深底 → 米白字 + 深色描边（黑字白边在深底上又重又丑）"""
    d.text((W // 2, 996), text, font=font(58), fill=(8, 8, 8), anchor="mm",
           stroke_width=9, stroke_fill=(8, 8, 8, 130))
    d.text((W // 2, 992), text, font=font(58), fill=(252, 250, 244), anchor="mm",
           stroke_width=6, stroke_fill=(14, 14, 14, 255))
    d.text((W // 2, 992), text, font=font(58), fill=(252, 250, 244), anchor="mm")


SCENES = [
    ("0  纯深底（对照）", bg_flat, "不加任何动效 · 让你看「死板」到底长什么样"),
    ("A  色斑漂移", bg_blobs, "三团发光色斑缓慢游动 · 最保守"),
    ("B  工程网格", bg_grid, "两层细网格斜向漂移 · 讲成分/数据时最搭"),
    ("C  光线扫", bg_sweep, "45° 柔光每 4 秒扫一次 · 高级感，最不抢"),
    ("D  速度线", bg_speed, "中心放射细线，缓慢旋转呼吸 · 力量感最强"),
    ("E  全套组合", bg_mix, "色斑 + 光扫 + 淡速度线 · 信息密度最高"),
]


def main():
    stk = load_sticker(os.path.join(CUT, "角色", "展示_半蹲发力浅色_全身.png"), 830)
    sh_w = int(stk.width * 0.52)
    shadow = make_shadow((sh_w, max(12, int(sh_w * 0.16))))

    rng = np.random.default_rng(3)
    NOISE = []
    for _ in range(6):
        n = rng.normal(0, 3.4, (H // 2, W // 2)).astype(np.float32)
        NOISE.append(np.asarray(Image.fromarray(
            np.clip(128 + n, 0, 255).astype(np.uint8), "L"
        ).resize((W, H), Image.BILINEAR)).astype(np.float32) - 128.0)

    SEG = 4.0
    per = int(SEG * FPS)
    total = per * len(SCENES)
    out_path = os.path.join(ROOT, "out", "动态背景_深底_对比_V1.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    fi = 0
    for name, fn, desc in SCENES:
        for k in range(per):
            t = k / float(FPS)
            lo = np.clip(fn(t), 0, 255).astype(np.uint8)
            frame = Image.fromarray(lo, "RGB").resize((W, H), Image.BILINEAR).convert("RGBA")

            arr = np.asarray(frame).astype(np.float32)
            arr[..., :3] += NOISE[fi % len(NOISE)][..., None]
            frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

            br = 1.0 + 0.006 * math.sin(t * 2.4)
            s = stk.resize((max(8, int(stk.width * br)), max(8, int(stk.height * br))), Image.BILINEAR) \
                if abs(br - 1.0) > 1e-4 else stk
            frame.alpha_composite(shadow, (W // 2 - shadow.width // 2, BASE_Y - shadow.height // 2))
            frame.alpha_composite(s, (W // 2 - s.width // 2, BASE_Y - s.height))

            d = ImageDraw.Draw(frame)
            draw_sub(d, SUB_TEXT)
            d.text((70, 56), name, font=font(54), fill=(250, 246, 238))
            d.text((72, 124), desc, font=font(30), fill=(186, 178, 164))

            proc.stdin.write(frame.convert("RGB").tobytes())
            fi += 1
        print("  %s ok (%d/%d)" % (name, fi, total), flush=True)

    proc.stdin.close()
    proc.wait()
    print("→", out_path)


if __name__ == "__main__":
    main()
