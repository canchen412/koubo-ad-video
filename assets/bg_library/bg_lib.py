#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
背景库 · 统一合成器（koubo-ad-video / assets/bg_library）
=======================================================
四组共 24 个预设，全部 numpy+PIL 程序生成，零素材、零 Remotion、8GB 内存友好。

  comic_dark   W1–W7   深底漫画分格墙（★默认 W7 斜贴分格）
  comic_light  P1–P5   浅纸漫画分格墙（暖纸米/冷灰蓝/暖橙/深格线/深炭）
  fx_dark      D0–DE   深底纯动效（纯底/色斑/网格/光扫/速度线/全套）
  fx_light     L0–LE   浅底纯动效（同上一组，按浅暖底调过振幅）

用法：
    from bg_lib import Background
    bg = Background("W7")            # 或 Background() 走默认 W7
    arr = bg.frame(t)                # -> np.uint8 (1080,1920,3)

    from bg_lib import random_preset
    Background(random_preset("comic_dark", exclude=["W7"]))

命令行出片/出静帧见 render_bg.py。

设计约束（踩过坑，别改）
------------------------
1. **逐格归一化**：16 张源图明暗差极大，套同一个线性映射会一块块深浅不一、
   看着像污渍。必须每格先 `norm_lum()` 把自己的灰度拉齐，再上配色。
2. **整墙只放大一次**：先把墙缩到 2880×1620 缓存，每帧只 `crop(1920×1080)`。
   逐帧 resize 会慢 14 倍（510 帧 35s → 500s）。
3. **浅底上加法效果物理不可见**：浅底加 4~5 个亮度值≈2%，看不出来；
   网格/速度线在浅底是减法，深底再减等于没有。所以深底一律改加法发光，
   振幅提到 30~66。别把浅底的参数直接搬到深底。
4. **绿人抢色**：色斑里的墨绿会跟 IP 人物抢，绿 blob 的 amp 压到 0.55、
   tint 用 (8,24,16)。
"""
import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---------------- 全局 ----------------

W, H = 1920, 1080
WORK_W, WORK_H = 960, 540          # 纯动效的工作分辨率（4 倍缩小后再放大）
BIG_W, BIG_H = 2880, 1620          # 漫画墙缓存分辨率

GAL = os.environ.get("XIAOLVREN_GAL", "/Volumes/素材库/广告视频/分镜图库/小绿人")

DEFAULT = "W7"                     # ★ 老板 2026-11-03 定：极简版默认斜贴分格

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

CW, CH, GRID_N = 600, 338, 4
WALL_W, WALL_H = CW * GRID_N, CH * GRID_N     # 2400 × 1352

# ---------------- 工作坐标网格 ----------------

_yy, _xx = np.mgrid[0:WORK_H, 0:WORK_W].astype(np.float32)
_NX, _NY = _xx / WORK_W, _yy / WORK_H
_cx, _cy = WORK_W * 0.5, WORK_H * 0.42
RAD = np.sqrt((_xx - _cx) ** 2 / (WORK_W * 0.78) ** 2 + (_yy - _cy) ** 2 / (WORK_H * 0.78) ** 2)

# 屏幕空间暗角（1920×1080，随 Background 尺寸缓存）
_VIG_CACHE = {}


def _vignette(w, h, amt):
    key = (w, h, round(amt, 3))
    if key in _VIG_CACHE:
        return _VIG_CACHE[key]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt((xx - w * 0.5) ** 2 / (w * 0.82) ** 2 + (yy - h * 0.44) ** 2 / (h * 0.82) ** 2)
    v = (1.0 - amt * r ** 1.5)[..., None].astype(np.float32)
    _VIG_CACHE[key] = v
    return v


# ================================================================
# 一、漫画分格墙（深底 / 浅底）
# ================================================================

_CELLS = []


def load_cells():
    """16 张源图裁成 4×4 格子（只做一次，全局复用）"""
    if _CELLS:
        return _CELLS
    for name in WALL_SRC:
        p = os.path.join(GAL, name)
        if not os.path.exists(p):
            _CELLS.append(Image.new("RGB", (CW, CH), (40, 38, 35)))
            continue
        im = Image.open(p).convert("RGB")
        sc = max(CW / im.width, CH / im.height)
        im = im.resize((max(CW, int(im.width * sc)), max(CH, int(im.height * sc))), Image.LANCZOS)
        x, y = (im.width - CW) // 2, (im.height - CH) // 2
        _CELLS.append(im.crop((x, y, x + CW, y + CH)))
    return _CELLS


def norm_lum(im, mean, std, gamma=1.0):
    """逐格归一化亮度 —— 「不发脏」的关键"""
    g = np.asarray(im.convert("L")).astype(np.float32) / 255.0
    sd = float(g.std())
    g = mean + (g - float(g.mean())) * (std / max(sd, 1e-3))
    return np.clip(g, 0.0, 1.0) ** gamma


def tone_duo(im, dark, light, mean, std, gamma=1.0):
    g = norm_lum(im, mean, std, gamma)
    d = np.array(dark, np.float32)
    l = np.array(light, np.float32)
    return d + (l - d) * g[..., None]


def _spotlight(i):
    """个别格轻微提亮，避免整墙平均死板"""
    return 1.0 + (0.34 if i % 5 == 2 else 0.0) + (0.18 if i == 7 else 0.0)


def _wall_grid(v):
    """规整分格：格内容 + 黑沟 + 发光缝（三层）"""
    wall = Image.new("RGB", (WALL_W, WALL_H), tuple(v["gutter"]))
    for i, cell in enumerate(load_cells()):
        if v.get("fn") == "press":
            arr = _tone_press(cell, v)
        else:
            arr = tone_duo(cell, v["dark"], v["light"], v["mean"], v["std"], v.get("gamma", 1.0))
        arr = np.clip(arr * _spotlight(i), 0, 255).astype(np.uint8)
        wall.paste(Image.fromarray(arr, "RGB"), (CW * (i % GRID_N), CH * (i // GRID_N)))

    glow = Image.new("RGB", (WALL_W, WALL_H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for c in range(1, GRID_N):
        gd.line([(CW * c, 0), (CW * c, WALL_H)], fill=v["glow"], width=5)
        gd.line([(0, CH * c), (WALL_W, CH * c)], fill=v["glow"], width=5)
    small = glow.resize((WALL_W // 8, WALL_H // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    glow = small.resize((WALL_W, WALL_H), Image.BILINEAR)

    a = np.asarray(wall).astype(np.float32) + np.asarray(glow).astype(np.float32) * v.get("glow_amt", 0.55)
    wall = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")

    d = ImageDraw.Draw(wall)
    for c in range(1, GRID_N):
        d.line([(CW * c, 0), (CW * c, WALL_H)], fill=v["gutter"], width=v.get("gut", 9))
        d.line([(0, CH * c), (WALL_W, CH * c)], fill=v["gutter"], width=v.get("gut", 9))
    for c in range(1, GRID_N):
        d.line([(CW * c, 0), (CW * c, WALL_H)], fill=v["line"], width=2)
        d.line([(0, CH * c), (WALL_W, CH * c)], fill=v["line"], width=2)
    return wall


def _wall_tilt(v):
    """斜贴分格（W7）：每格轻微旋转 + 压边，像贴满墙的分镜小卡"""
    wall = Image.new("RGB", (WALL_W, WALL_H), tuple(v["gutter"]))
    angs = [-4.6, 3.2, -2.4, 4.4, -3.4, 2.6, 4.8, -2.8,
            3.6, -4.2, 2.2, -3.0, -2.2, 4.2, -4.8, 3.0]
    for i, cell in enumerate(load_cells()):
        arr = tone_duo(cell, v["dark"], v["light"], v["mean"], v["std"], v.get("gamma", 1.0))
        arr = np.clip(arr * _spotlight(i), 0, 255).astype(np.uint8)
        # 1.16 倍放大：旋转后四角不露底（小于 1.12 会看到三角空洞）
        c = Image.fromarray(arr, "RGB").resize((int(CW * 1.16), int(CH * 1.16)), Image.LANCZOS)
        rim = Image.new("RGB", (c.width + 6, c.height + 6), tuple(v["line"]))
        rim.paste(c, (3, 3))
        r = rim.rotate(angs[i % len(angs)], resample=Image.BICUBIC, expand=False)
        wall.paste(r, (CW * (i % GRID_N) + CW // 2 - r.width // 2,
                       CH * (i // GRID_N) + CH // 2 - r.height // 2))
    return wall


def _tone_press(cell, v):
    """暖纸米墙直接压暗：保留纸质感，只是整体降下来"""
    g = norm_lum(cell, v.get("mean", 0.80), v.get("std", 0.115))
    d = np.array([44, 41, 37], np.float32)
    l = np.array([176, 167, 150], np.float32)
    return (d + (l - d) * g[..., None]) * v.get("press", 0.66)


# ================================================================
# 二、纯动效（深底 / 浅底）
# ================================================================

DARK_BASE = np.array([22, 21, 20], np.float32)      # 深炭（微暖，不是死黑）
LIGHT_BASE = np.array([241, 237, 227], np.float32)  # 暖纸米


def _base_layer(base, dark=False):
    if dark:
        g = np.clip(1.28 - 0.30 * RAD ** 1.5, 0.62, 1.30)
    else:
        g = np.clip(1.03 - 0.085 * RAD ** 1.6, 1.0, 1.03)
    return base[None, None, :] * g[..., None]


def _blob(cx, cy, rad, amp, tint):
    d2 = (_xx - cx) ** 2 + (_yy - cy) ** 2
    return (np.exp(-d2 / (2 * rad * rad)) * amp)[..., None] * np.array(tint, np.float32)[None, None, :]


def _grid(period, thick, offset, strength=1.0):
    fx = np.abs(((_xx + offset) % period) - period * 0.5)
    fy = np.abs(((_yy + offset * 0.6) % period) - period * 0.5)
    lx = np.clip((period * 0.5 - fx) / thick, 0, 1)
    ly = np.clip((period * 0.5 - fy) / thick, 0, 1)
    return np.maximum(lx, ly) * strength


def _speed_lines(t, n=44, rot=0.055, inner=0.20, amp=44.0, breath_on=True):
    dx, dy = _xx - WORK_W * 0.5, _yy - WORK_H * 0.44
    ang = np.arctan2(dy, dx) + t * rot
    line = np.clip(np.sin(ang * n), 0, 1) ** 6.0
    rad = np.sqrt(dx ** 2 + dy ** 2) / (WORK_W * 0.6)
    edge = np.clip((rad - inner) / 0.5, 0, 1)
    breath = 1.0
    if breath_on:
        breath = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 1.1))
    return (line * edge * amp * breath)[..., None]


def _sweep(t, period=4.0, width=0.10, amp=62.0):
    c = -0.5 + ((t % period) / period) * 1.8
    u = _NX * 0.707 + _NY * 0.707
    band = np.exp(-((u - c) ** 2) / (2 * width ** 2))
    return (band * amp)[..., None]


# ---- 深底 ----

def fx_dark_flat(t):
    return _base_layer(DARK_BASE, True)


def fx_dark_blobs(t):
    out = _base_layer(DARK_BASE, True)
    out += _blob(WORK_W * (0.30 + 0.06 * math.sin(t * 0.45)),
                 WORK_H * (0.34 + 0.05 * math.cos(t * 0.38)), WORK_W * 0.34, 1.0, (66, 46, 22))
    out += _blob(WORK_W * (0.72 + 0.05 * math.cos(t * 0.33)),
                 WORK_H * (0.62 + 0.06 * math.sin(t * 0.41)), WORK_W * 0.36, 1.0, (16, 50, 28))
    out += _blob(WORK_W * (0.52 + 0.07 * math.sin(t * 0.27 + 1.2)),
                 WORK_H * (0.18 + 0.05 * math.cos(t * 0.31)), WORK_W * 0.30, 1.0, (20, 28, 58))
    return out


def fx_dark_grid(t):
    out = _base_layer(DARK_BASE, True)
    off = (t * 9.0) % 200.0
    shade = (_grid(60.0, 2.2, off) * 38.0 + _grid(180.0, 3.0, off * 0.6) * 30.0)[..., None]
    return out + shade * np.array([0.90, 1.0, 1.05], np.float32)[None, None, :]


def fx_dark_sweep(t):
    return _base_layer(DARK_BASE, True) + _sweep(t, 4.0, 0.10, 62.0) * \
        np.array([1.0, 0.96, 0.88], np.float32)[None, None, :]


def fx_dark_speed(t):
    return _base_layer(DARK_BASE, True) + _speed_lines(t, 44, 0.055, 0.20, 44.0) * \
        np.array([1.0, 0.95, 0.85], np.float32)[None, None, :]


def fx_dark_mix(t):
    out = fx_dark_blobs(t)
    out += _sweep(t, 5.0, 0.11, 40.0) * np.array([1.0, 0.98, 0.94], np.float32)[None, None, :]
    out += _speed_lines(t, 36, 0.04, 0.28, 26.0, breath_on=False) * \
        np.array([1.0, 0.95, 0.85], np.float32)[None, None, :]
    return out


# ---- 浅底（振幅全部降档：浅底上加法效果超过 5 就发脏） ----

def fx_light_flat(t):
    return _base_layer(LIGHT_BASE)


def fx_light_blobs(t):
    out = _base_layer(LIGHT_BASE)
    out += _blob(WORK_W * (0.30 + 0.06 * math.sin(t * 0.45)),
                 WORK_H * (0.34 + 0.05 * math.cos(t * 0.38)), WORK_W * 0.34, 5.2, (5, 4, 0))
    out += _blob(WORK_W * (0.72 + 0.05 * math.cos(t * 0.33)),
                 WORK_H * (0.62 + 0.06 * math.sin(t * 0.41)), WORK_W * 0.36, 4.4, (-3, -2, 4))
    out += _blob(WORK_W * (0.52 + 0.07 * math.sin(t * 0.27 + 1.2)),
                 WORK_H * (0.18 + 0.05 * math.cos(t * 0.31)), WORK_W * 0.30, 3.6, (4, 3, -3))
    return out


def fx_light_grid(t):
    out = _base_layer(LIGHT_BASE)
    off = (t * 9.0) % 200.0
    shade = (_grid(60.0, 2.2, off) * 6.5 + _grid(180.0, 3.0, off * 0.6) * 5.0)[..., None]
    return out - shade * np.array([1.0, 0.95, 0.85], np.float32)[None, None, :]


def fx_light_sweep(t):
    return _base_layer(LIGHT_BASE) + _sweep(t, 4.0, 0.10, 34.0) * \
        np.array([1.0, 0.99, 0.96], np.float32)[None, None, :]


def fx_light_speed(t):
    return _base_layer(LIGHT_BASE) - _speed_lines(t, 44, 0.055, 0.22, 5.2) * \
        np.array([1.0, 0.96, 0.88], np.float32)[None, None, :]


def fx_light_mix(t):
    out = fx_light_blobs(t)
    out += _sweep(t, 5.0, 0.11, 24.0) * np.array([1.0, 0.99, 0.96], np.float32)[None, None, :]
    out -= _speed_lines(t, 36, 0.04, 0.28, 3.0, breath_on=False) * \
        np.array([1.0, 0.96, 0.88], np.float32)[None, None, :]
    return out


# ================================================================
# 三、预设注册表
# ================================================================

# 深底漫画墙
_DARK = dict(dark=(10, 9, 8), light=(122, 110, 94), mean=0.26, std=0.155,
             gutter=(8, 7, 7), glow=(120, 96, 60), glow_amt=0.75,
             line=(226, 206, 172), gut=9, vig=0.16)

COMIC_DARK = {
    "W1": dict(name="深炭·暖格线", **{**_DARK}),
    "W2": dict(name="深炭·主光移动", ambient="spot", **{**_DARK}),
    "W3": dict(name="冷墨蓝", dark=(8, 10, 14), light=(96, 112, 132), mean=0.25, std=0.15,
               gutter=(7, 8, 11), glow=(52, 78, 118), glow_amt=0.85,
               line=(186, 206, 232), gut=9, vig=0.16),
    "W4": dict(name="墨线稿", dark=(6, 6, 6), light=(168, 158, 141), mean=0.30, std=0.20,
               gamma=2.1, gutter=(0, 0, 0), glow=(96, 78, 52), glow_amt=0.55,
               line=(230, 214, 186), gut=11, vig=0.18),
    "W5": dict(name="深炭·色斑", ambient="blobs", dark=(10, 9, 8), light=(116, 104, 88),
               mean=0.24, std=0.15, gutter=(8, 7, 7), glow=(120, 96, 60), glow_amt=0.70,
               line=(220, 200, 168), gut=9, vig=0.16),
    "W6": dict(name="暖纸压暗", fn="press", press=0.66, gutter=(24, 22, 18),
               glow=(110, 92, 66), glow_amt=0.40, line=(186, 174, 152), gut=7, vig=0.16),
    "W7": dict(name="斜贴分格", tilt=True, ambient="spot", dark=(9, 8, 8),
               light=(126, 114, 98), mean=0.25, std=0.15, gutter=(6, 6, 6),
               glow=(0, 0, 0), glow_amt=0.0, line=(168, 150, 120), gut=0, vig=0.16),
}

# 浅纸漫画墙
COMIC_LIGHT = {
    "P1": dict(name="暖纸米", dark=(156, 141, 120), light=(252, 249, 241), mean=0.80, std=0.115,
               gutter=(252, 249, 241), glow=(0, 0, 0), glow_amt=0.0,
               line=(253, 251, 245), gut=7, vig=0.055),
    "P2": dict(name="冷灰蓝", dark=(126, 136, 148), light=(246, 248, 251), mean=0.82, std=0.105,
               gutter=(246, 248, 251), glow=(0, 0, 0), glow_amt=0.0,
               line=(252, 253, 255), gut=7, vig=0.055),
    "P3": dict(name="暖橙", dark=(178, 138, 104), light=(253, 245, 234), mean=0.80, std=0.115,
               gutter=(253, 245, 234), glow=(0, 0, 0), glow_amt=0.0,
               line=(254, 247, 238), gut=7, vig=0.055),
    "P4": dict(name="暖纸米·深格线", dark=(150, 135, 114), light=(252, 249, 241),
               mean=0.80, std=0.125, gutter=(252, 249, 241), glow=(0, 0, 0), glow_amt=0.0,
               line=(74, 64, 52), gut=4, vig=0.055),
    "P5": dict(name="深炭", dark=(20, 20, 22), light=(108, 103, 97), mean=0.70, std=0.17,
               gutter=(108, 103, 97), glow=(0, 0, 0), glow_amt=0.0,
               line=(122, 118, 112), gut=7, vig=0.055),
}

FX_DARK = {
    "D0": dict(name="纯深底（对照）", fn=fx_dark_flat),
    "DA": dict(name="色斑漂移", fn=fx_dark_blobs),
    "DB": dict(name="工程网格", fn=fx_dark_grid),
    "DC": dict(name="光线扫", fn=fx_dark_sweep),
    "DD": dict(name="速度线", fn=fx_dark_speed),
    "DE": dict(name="全套组合", fn=fx_dark_mix),
}

FX_LIGHT = {
    "L0": dict(name="纯浅底（对照）", fn=fx_light_flat),
    "LA": dict(name="色斑漂移", fn=fx_light_blobs),
    "LB": dict(name="工程网格", fn=fx_light_grid),
    "LC": dict(name="光线扫", fn=fx_light_sweep),
    "LD": dict(name="速度线", fn=fx_light_speed),
    "LE": dict(name="全套组合", fn=fx_light_mix),
}

GROUPS = {
    "comic_dark": (COMIC_DARK, "深底漫画分格墙"),
    "comic_light": (COMIC_LIGHT, "浅纸漫画分格墙"),
    "fx_dark": (FX_DARK, "深底纯动效"),
    "fx_light": (FX_LIGHT, "浅底纯动效"),
}

REGISTRY = {}
for _g, (_tbl, _label) in GROUPS.items():
    for _pid, _p in _tbl.items():
        REGISTRY[_pid] = dict(_p, id=_pid, group=_g, group_label=_label)


# ================================================================
# 四、环境光（屏幕空间低分辨率 → 放大；比全分辨率快十几倍）
# ================================================================

GX, GY = 320, 180
_gy, _gx = np.mgrid[0:GY, 0:GX].astype(np.float32)
_GNX, _GNY = _gx / GX, _gy / GY


def _lo_blob(cx, cy, rad, amp, tint):
    d2 = (_GNX - cx) ** 2 * (GX / GY) ** 2 + (_GNY - cy) ** 2
    return (np.exp(-d2 / (2 * rad * rad)) * amp)[..., None] * np.array(tint, np.float32)[None, None, :]


def _glow_spot(t):
    return _lo_blob(0.50 + 0.16 * math.sin(t * 0.28), 0.34 + 0.10 * math.cos(t * 0.22),
                    0.30, 1.0, (52, 34, 14))


def _glow_blobs(t):
    out = _lo_blob(0.28 + 0.06 * math.sin(t * 0.40), 0.36 + 0.05 * math.cos(t * 0.34),
                   0.26, 1.0, (46, 30, 12))
    out += _lo_blob(0.74 + 0.05 * math.cos(t * 0.31), 0.64 + 0.06 * math.sin(t * 0.37),
                    0.28, 0.55, (8, 24, 16))
    out += _lo_blob(0.55 + 0.07 * math.sin(t * 0.25 + 1.1), 0.16 + 0.05 * math.cos(t * 0.29),
                    0.24, 0.75, (12, 20, 44))
    return out


AMBIENT = {"spot": _glow_spot, "blobs": _glow_blobs}


def _ambient_layer(kind, t, w, h):
    lo = np.clip(AMBIENT[kind](t), 0, 32).astype(np.float32)
    chs = []
    for c in range(3):
        im = Image.fromarray((lo[..., c] / 32.0 * 255.0).clip(0, 255).astype(np.uint8), "L")
        chs.append(np.asarray(im.resize((w, h), Image.BILINEAR)).astype(np.float32) / 255.0 * 32.0)
    return np.stack(chs, axis=2)


# ================================================================
# 五、对外 API
# ================================================================

class Background:
    """一个预设的连续背景。先 construct，再逐帧 frame(t)。

    >>> bg = Background("W7")
    >>> arr = bg.frame(0.0)      # np.uint8 (1080,1920,3)
    """

    def __init__(self, pid=None, w=W, h=H, drift=True):
        self.pid = pid or DEFAULT
        if self.pid not in REGISTRY:
            raise KeyError("未知背景预设 %r，可选：%s" % (self.pid, ", ".join(sorted(REGISTRY))))
        self.p = REGISTRY[self.pid]
        self.w, self.h = w, h
        self.drift = drift
        self._wall = None
        self._vig = _vignette(w, h, self.p.get("vig", 0.0))

    # ---- 内部 ----
    @property
    def is_comic(self):
        return self.p["group"].startswith("comic")

    def _wall_big(self):
        if self._wall is None:
            v = self.p
            self._wall = _wall_tilt(v) if v.get("tilt") else _wall_grid(v)
            self._wall = self._wall.resize((BIG_W, BIG_H), Image.LANCZOS)
        return self._wall

    def _comic_frame(self, t):
        wall = self._wall_big()
        if self.drift:
            ox = 480 + 220 * math.sin(t * 0.26)
            oy = 270 + 140 * math.cos(t * 0.21)
        else:
            ox, oy = 480, 270
        crop = wall.crop((int(ox), int(oy), int(ox) + self.w, int(oy) + self.h))
        arr = np.asarray(crop).astype(np.float32)
        kind = self.p.get("ambient")
        if kind:
            arr += _ambient_layer(kind, t, self.w, self.h)
        return arr

    def _fx_frame(self, t):
        lo = np.clip(self.p["fn"](t), 0, 255).astype(np.uint8)
        im = Image.fromarray(lo, "RGB").resize((self.w, self.h), Image.LANCZOS)
        return np.asarray(im).astype(np.float32)

    # ---- 对外 ----
    def frame(self, t):
        arr = self._comic_frame(t) if self.is_comic else self._fx_frame(t)
        if self.p.get("vig"):
            arr = arr * self._vig
        return np.clip(arr, 0, 255).astype(np.uint8)

    def free(self):
        self._wall = None


def list_presets(group=None):
    ids = [k for k, v in REGISTRY.items() if group is None or v["group"] == group]
    return [(k, REGISTRY[k]["name"]) for k in ids]


def random_preset(group="comic_dark", exclude=None, rng=None):
    """随机抽一个预设 —— 极简版「漫画墙样式随机」用这个。

    exclude 里可以传「已用过」的，保证同批多条不撞墙。
    """
    exclude = set(exclude or [])
    pool = [k for k in REGISTRY if REGISTRY[k]["group"] == group and k not in exclude]
    if not pool:
        pool = [k for k in REGISTRY if REGISTRY[k]["group"] == group]
    rng = rng or np.random.default_rng()
    return pool[int(rng.integers(0, len(pool)))]
