#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简版渲染器 · 漫画墙 + 贴纸
============================
一条片 = 一张会动的漫画分格墙 + 逐句弹入的抠图贴纸 + 逐句字幕。
不做 zoompan 运镜、不做重点字、不做详情卡、不铺满 AI 分镜。

输入
----
  --plan     plan.json        逐句要放什么（见 references/极简版_贴纸模式.md）
  --vo       vo_index.json    逐句文案与时长（由 minimal_audio.py 生成）
  --out      xxx.mp4          无音轨成片（音频由 minimal_audio.py 混回去）

输出
----
  成片 mp4（静音）+ timeline.json（每句起止，给混音/字幕用）

plan.json 结构
--------------
{
  "bg": "W7",                       // 或 "random"；缺省走 bg_lib.DEFAULT
  "shots": [
    {"id": "s01", "kind": "sticker",
     "src": "角色/展示_张臂指镜头_全身.png",
     "zone": "C", "h": 860, "off": 0.02, "sfx": "kw_pop"},
    {"id": "s02", "kind": "card", "src": "/abs/x.jpg", "ar": "16x9", "zone": "C",
     "sfx": "kw_ding"},
    {"id": "s03", "kind": "vcard", "src": "/abs/x.mp4", "ar": "16x9"},
    {"id": "s04", "kind": "full", "src": "/abs/x.jpg"}       // 兜底：整屏铺满
  ]
}
一句最多两个元素时写 "els": [ {...}, {...} ]，一帧不超过 2 个。
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "assets", "bg_library"))
sys.path.insert(0, HERE)
import bg_lib     # noqa: E402
import motion_kit as MK   # noqa: E402

# ---------------- 定版参数（改之前先看 references/极简版_贴纸模式.md） ----------------

W, H, FPS = 1920, 1080, 30
BASE_Y = 970          # 贴纸脚底基线（不预留字幕安全区，元素下沉吃满画面）
SUB_Y = 1046          # 字幕底边
PULL = 0.36           # 旧弹入时长（仅兼容旧 plan；贴纸现按 MOTION_DUR 走）
MOTION_DUR = MK.DUR   # 贴纸入场动效时长 0.62s
HARD_IN = 0.06        # 图片硬切：这个点之后的第 1 帧整张出现，不缩放不淡入
OVERLAP = 96          # 有图片时，贴纸压住卡片边缘的像素（前后层次）
STICKER_H = 940       # 贴纸默认高（plan 没写 h 时用）。老板 2026-11-03：「可以再大一点」
TELLER_H = 740        # 讲解位默认高（图片旁边那个人，比主体小一档但不许太弱）
GAP = 0.04            # 句间微间隙
BOTTOM_PAD = 24       # 贴纸自带底部留白（1000px 基准下）
Z = {"L": 0.27, "C": 0.50, "R": 0.73}

CUT = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库"
FONT = os.path.join(HERE, "..", "assets", "fonts", "STHeiti Medium.ttc")
# 重点字 / 左右拆字专用字体（老板 2026-11-03 从 6 款样张里选 D＝思源宋体 Heavy）。
# 字幕仍用 FONT 黑体（字幕要「读得清」，宋体横画在 58 号会被 H.264 糊掉）。
# 想换回黑体：把 FONT_KW 指回 FONT；想试得意黑：SmileySans-Oblique.otf。
FONT_KW = os.path.join(HERE, "..", "assets", "fonts", "SHSerif-Heavy.otf")

CARD_MAX_W, CARD_MAX_H = 1020, 574     # 单元素卡片：留出顶部重点字带（原 1180×660 顶到 y154，重点字没地方站）
CARD_CY = 516            # 卡片顶 229：上方 0–217 整条留给重点字
CARD_MIN_W, CARD_MIN_H = 820, 500     # 一帧两个元素时用这套

# 方图居中 + 左右拆字（老板 2026-11-03 参考 IMG_3303：情绪/场景类图片走这套）
SQ_SIZE, SQ_CY, SQ_RADIUS, SQ_PAD = 760, 500, 26, 40
SQ_CHAR = 320          # 左右大字字号；长字自动降到 240
SQ_GAP = 26            # 字与图之间的缝
SQ_RED = (232, 34, 26)

# 重点字（与标准版同语言：大号粗字 + 厚黑边；但版位改成「上角斜贴块」避免压主体）
KW_SIZE = 142         # 字号（长词自动降到 76）。
                      # 老板 2026-11-03：「重点字太小了，做大一点」——92→142 实测：
                      # 块高 149→230px（占画面 13.8%→21.3%）；166 会压到人物肩臂，不上
KW_MAX_W = 1180       # 块宽上限（随字号同步放宽；否则长词被压回 52 号反而更小）
KW_Y_STICKER = 196    # 贴纸镜：上角带中心 y
KW_Y_CARD = 112       # 卡片镜：顶部条中心 y（卡片顶 229，上留白 217）
KW_MARGIN = 64        # 距画边
KW_KEEP_MARGIN = 44   # 重点字避让主体时距画边的最小距离（比 KW_MARGIN 放得开一点，宽字才塞得下）
KW_GAP = 12           # 字块底边与卡片上沿的最小缝
KW_SHAKE_PAD = 30     # 判遮挡时向外扩的容差：贴纸落定后还有 ±2° 摇晃 + 呼吸
KW_SCALES = (1.0, 0.88, 0.76, 0.64)   # 放不下就逐档缩字号（跟 make_kw 的 scale 对应）
KW_IN = 0.14          # 重点字最早入场时间（下限，实际按时序自动顺延，见 kw_delay）
KW_SETTLE = 0.06      # 元素全部落定后再等 0.06s 才出字
KW_PULL = 0.20        # 入场只给 6 帧，少几次重采样就不会“闪”
KW_SCALE_FROM = 1.16  # 从 1.16 收回到 1.0（无过冲曲线，不抖）
KW_OUT = 0.16         # 句末淡出

# 两套配色（老板 2026-11-03：一条片至少两种颜色样式，按底图色调/段落轮换）
KW_STYLES = {
    "sun": dict(bg=(255, 198, 26), fg=(22, 18, 12), edge=(20, 16, 10)),   # 暖黄黑字
    "ice": dict(bg=(240, 246, 255), fg=(18, 24, 34), edge=(16, 20, 28)),  # 冷白深字
    "red": dict(bg=(226, 64, 44), fg=(255, 250, 242), edge=(24, 10, 8)),  # 砖红白字（价格/数字专用）
}

# 中景/半身贴纸在大腿处截断、悬浮物品离地 —— 画地面投影会很假
NO_SHADOW_HINT = ("中景", "特写", "半身")
FADE_HINT = ("中景", "特写", "半身")


def font(sz):
    return ImageFont.truetype(FONT, sz)


def font_kw(sz):
    """重点字 / 左右拆字用（默认为思源宋体 Heavy）。"""
    return ImageFont.truetype(FONT_KW, sz)


def ease_out_back(p, overshoot=1.06):
    """缓出带过冲：前 40% 时间走完 85% 位移，落地 6% 过冲"""
    p = max(0.0, min(1.0, p))
    if p >= 1.0:
        return 1.0
    e = 1 - (1 - p) ** 3
    return e + overshoot * math.sin(math.pi * p) * (1 - p) ** 1.4 * 0.55


# ================================================================
# 贴纸
# ================================================================

class StickerLib:
    """只缓存「满尺寸母版 + 投影」，逐帧按缩放比临时缩。
    早期版本把每个缩放档都缓存一张，9 张贴纸 ×24 档 ≈ 300MB，
    8GB 机器上直接被 SIGTERM 杀掉（exit 137）。"""

    def __init__(self, root=CUT):
        self.root = root
        self.cache = {}
        self.masters = {}

    def path(self, src):
        return src if os.path.isabs(src) else os.path.join(self.root, src)

    def load(self, src):
        if src not in self.cache:
            p = self.path(src)
            # 边缘净化版优先：同目录下有 xxx_净边.png 就用它。
            # 原图人物自带白色画风描边，抠出来在深色漫画墙上一圈发亮；净化版剥掉了。
            if "_净边" not in p:
                clean = os.path.splitext(p)[0] + "_净边.png"
                if os.path.exists(clean):
                    p = clean
            if not os.path.exists(p):
                raise FileNotFoundError("贴纸不存在：%s" % p)
            im = Image.open(p).convert("RGBA")
            if any(k in os.path.basename(p) for k in FADE_HINT):
                a = np.asarray(im).astype(np.float32)
                h = a.shape[0]
                fade = max(8, int(h * 0.09))
                ramp = np.linspace(1.0, 0.0, fade, dtype=np.float32).reshape(-1, 1)
                a[h - fade:, :, 3] *= ramp
                im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
            self.cache[src] = im
        return self.cache[src]

    def master(self, src, height, flip=False):
        """满尺寸母版（height 为最终高度）+ 对应投影，一个 (src,h,flip) 只算一次"""
        key = (src, height, bool(flip))
        if key not in self.masters:
            st = self.load(src)
            if flip:                                   # 讲解位要让他朝着卡片，只能镜像
                st = st.transpose(Image.FLIP_LEFT_RIGHT)
            hh = max(8, int(round(height)))
            ww = max(8, int(round(st.width * hh / st.height)))
            im = st.resize((ww, hh), Image.BILINEAR)
            sh = None
            if not any(k in os.path.basename(src) for k in NO_SHADOW_HINT):
                sh_w = max(24, int(ww * 0.52))
                sh = radial_shadow((sh_w, max(12, int(sh_w * 0.16))), op=95)
            self.masters[key] = (im, sh)
        return self.masters[key]

    def frame(self, src, height, p, flip=False):
        """按弹入进度 p 出 (贴纸, 阴影或 None)"""
        sc = max(0.40, ease_out_back(p))          # 起始不给 0，否则头 3 帧是空画面
        im, sh = self.master(src, height, flip)
        ww = max(8, int(round(im.width * sc)))
        hh = max(8, int(round(im.height * sc)))
        s = im if (ww, hh) == im.size else im.resize((ww, hh), Image.BILINEAR)
        if sh is not None:
            sh = sh if sc >= 0.999 else sh.resize(
                (max(8, int(sh.width * sc)), max(8, int(sh.height * sc))), Image.BILINEAR)
        return s, sh

    def frame_m(self, src, height, flip, prm):
        """按 motion_kit 的 Motion 出 (贴纸, 地面阴影)。
        顺序有讲究：先缩放 → 再遮罩（wipe/iris）→ 再模糊 → 最后旋转。
        反过来先把小图模糊再放大，会糊成一片；先旋转再缩放，脚底位置对不上。"""
        im, sh = self.master(src, height, flip)
        ww = max(8, int(round(im.width * prm.sx)))
        hh = max(8, int(round(im.height * prm.sy)))
        s = im if (ww, hh) == im.size else im.resize((ww, hh), Image.BILINEAR)
        if sh is not None and (ww, hh) != im.size:
            sh = sh.resize((max(8, int(sh.width * prm.sx)),
                            max(8, int(sh.height * prm.sy))), Image.BILINEAR)

        if prm.wipe is not None or prm.iris is not None:
            m = Image.new("L", s.size, 0)
            md = ImageDraw.Draw(m)
            if prm.wipe is not None:                  # 从脚下往上长
                top = int(s.height * (1.0 - max(0.0, min(1.0, prm.wipe))))
                md.rectangle([0, top, s.width, s.height], fill=255)
                m = m.filter(ImageFilter.GaussianBlur(max(2, s.height // 110)))
            else:                                     # 圆形展开
                r = max(2.0, prm.iris * math.hypot(s.width, s.height) * 0.60)
                md.ellipse([s.width // 2 - r, s.height // 2 - r,
                            s.width // 2 + r, s.height // 2 + r], fill=255)
                m = m.filter(ImageFilter.GaussianBlur(3))
            s = s.copy()
            s.putalpha(ImageChops.multiply(s.getchannel("A"), m))

        if prm.blur > 0.4:
            s = s.filter(ImageFilter.GaussianBlur(prm.blur))

        if abs(prm.rot) > 0.05:
            s = s.rotate(prm.rot, resample=Image.BICUBIC, expand=True,
                         fillcolor=(0, 0, 0, 0))

        if prm.alpha < 0.999:
            s = s.copy()
            s.putalpha(s.getchannel("A").point(lambda v: int(v * prm.alpha)))
        return s, sh

    def clear(self):
        self.cache.clear()
        self.masters.clear()


def radial_shadow(size, op=95):
    """径向渐隐椭圆：比「实心椭圆+模糊」干净，扁椭圆也不会糊成方块"""
    w, h = max(8, int(size[0])), max(8, int(size[1]))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    r = np.sqrt(((xx - cx) / (w / 2.0)) ** 2 + ((yy - cy) / (h / 2.0)) ** 2)
    a = (np.clip(1.0 - r, 0, 1) ** 2.0 * op).astype(np.uint8)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = 4, 4, 4
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


# ================================================================
# 圆角卡片（图片 / 视频共用）
# ================================================================

class CardFactory:
    """先把「投影 + 圆角蒙版 + 细边」做成模板，再往里面贴内容。
    视频逐帧也走这条路，一帧只做一次 paste，不重复造框。"""

    def __init__(self, radius=38, border=3):
        self.radius = radius
        self.border = border
        self._tpl = {}

    def _build(self, w, h):
        key = (w, h)
        if key in self._tpl:
            return self._tpl[key]
        pad = 44
        cw, ch = w + pad * 2, h + pad * 2
        # 投影
        sh = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(sh).rounded_rectangle(
            [pad, pad + 14, pad + w, pad + h + 14], radius=self.radius, fill=190)
        sh = sh.filter(ImageFilter.GaussianBlur(26))
        shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        shadow.putalpha(sh.point(lambda v: int(v * 0.62)))
        # 蒙版 + 边
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                               radius=self.radius, fill=255)
        edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle(
            [0, 0, w - 1, h - 1], radius=self.radius,
            outline=(232, 222, 202, 190), width=self.border)
        self._tpl[key] = (shadow, mask, edge, pad)
        return self._tpl[key]

    def make(self, content, w, h):
        shadow, mask, edge, pad = self._build(w, h)
        body = content.convert("RGB").resize((w, h), Image.LANCZOS).convert("RGBA")
        body.putalpha(mask)
        body.alpha_composite(edge)
        out = shadow.copy()
        out.alpha_composite(body, (pad, pad))
        return out


# ================================================================
# 卡片上的动态红圈（口播报价格/券额时，把那个数「画」出来）
# ================================================================
# 静态圈的问题（老板 2026-11-05）：「用红圈标记的重点，圈圈要有动态，
# 才能看出它圈的是哪个」。所以这里不是贴一张画好圈的图，而是逐帧把圈画出来：
#   起笔（半径大一圈）→ 顺时针扫满 360° → 收拢到目标大小 → 敲两下 → 常亮微呼吸。
# 坐标一律归一化（相对卡片内容宽高），换卡片尺寸不用重算。
RING_T0, RING_DUR, RING_W = 0.10, 0.44, 13
RING_RED = (228, 28, 42)


def _ring_overlay(content, ring, lt):
    """在卡片内容上叠一圈「正在画出来」的红圈，返回 RGB 图（不改入参）。

    ring 字段（都可省）：
      cx/cy  圈心（0–1，相对内容宽高）
      rx/ry  半径（0–1）
      w      线宽（内容像素，默认 13）
      t0     起笔时刻（相对本元素 off 后的秒数，默认 0.10）
      dur    画完一圈用时（默认 0.44）
      pulse  画完后敲几下（默认 2，0 = 不敲）
      color  RGB 三元组
    """
    w, h = content.size
    cx = float(ring.get("cx", 0.5)) * w
    cy = float(ring.get("cy", 0.5)) * h
    rx = float(ring.get("rx", 0.10)) * w
    ry = float(ring.get("ry", 0.08)) * h
    lw = float(ring.get("w", RING_W))
    t0 = float(ring.get("t0", RING_T0))
    dur = float(ring.get("dur", RING_DUR))
    npulse = int(ring.get("pulse", 2))
    color = tuple(ring.get("color") or RING_RED)

    if lt < t0:
        return content                      # 还没起笔，画面保持干净

    p = min(1.0, (lt - t0) / max(1e-3, dur))
    e = 1.0 - (1.0 - p) ** 2                # 起笔快、收笔稳
    sweep = 360.0 * e
    k = 1.0 + 0.26 * (1.0 - e)              # 起笔时大一圈，逐渐收拢到目标
    pd = lt - (t0 + dur)
    if pd > 0 and npulse > 0:               # 画完敲两下：1.0 → 1.05 → 1.0，逐次衰减
        ph = (pd % 0.62) / 0.62
        decay = max(0.0, 1.0 - pd / (0.62 * npulse))
        k += 0.05 * math.sin(math.pi * ph) * decay
    k += 0.010 * math.sin(2 * math.pi * lt / 1.6)   # 常亮微呼吸，圈不会「死」在画上

    S = 2                                    # 2 倍超采样：线边不出锯齿
    layer = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bx = [cx * S - rx * S * k, cy * S - ry * S * k,
          cx * S + rx * S * k, cy * S + ry * S * k]
    a0 = -90.0                               # 12 点起笔，顺时针
    a1 = a0 + sweep
    lwp = lw * S
    d.arc(bx, a0, a1, fill=(255, 255, 255, 240), width=int(round(lwp + 8)))
    d.arc(bx, a0, a1, fill=color + (255,), width=int(round(lwp)))
    if p < 0.999:                            # 笔尖：弧头压一个小圆点，像刚落笔
        th = math.radians(a1)
        px = cx * S + rx * S * k * math.cos(th)
        py = cy * S + ry * S * k * math.sin(th)
        r = lwp * 0.5
        d.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 255, 246))
        d.ellipse([px - r * 0.58, py - r * 0.58, px + r * 0.58, py + r * 0.58],
                  fill=color + (255,))
    layer = layer.resize((w, h), Image.LANCZOS)
    out = content.convert("RGBA").copy()
    out.alpha_composite(layer)
    return out.convert("RGB")


def _ar(ar):
    """'16x9' → (16.0, 9.0)"""
    a, b = [float(x) for x in ar.split("x")]
    return a, b


def fit_crop(im, w, h, ar=None):
    """先按目标比例裁，再铺满 —— 不拉伸"""
    if ar:
        a, b = [float(x) for x in ar.split("x")]
        target = a / b
        cur = im.width / im.height
        if cur > target:                        # 太宽，切左右
            nw = int(round(im.height * target))
            x = (im.width - nw) // 2
            im = im.crop((x, 0, x + nw, im.height))
        else:                                   # 太高，切上下
            nh = int(round(im.width / target))
            y = (im.height - nh) // 2
            im = im.crop((0, y, im.width, y + nh))
    return im


class VideoCard:
    """把视频抽成 jpg 序列，逐帧当卡片内容用（循环播放）"""

    def __init__(self, src, ar, w, h, fps=FPS, workdir=None):
        self.src, self.w, self.h, self.fps = src, w, h, fps
        self.dir = workdir or tempfile.mkdtemp(prefix="vcard_")
        os.makedirs(self.dir, exist_ok=True)
        vf = "fps=%d" % fps
        if ar:
            a, b = [float(x) for x in ar.split("x")]
            vf += ",scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (
                w * 2, h * 2, w * 2, h * 2)
            # 先按 2 倍抽，卡片缩小时更抗锯齿
        else:
            vf += ",scale=%d:-2" % (w * 2)
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", vf,
               "-q:v", "3", os.path.join(self.dir, "%05d.jpg")]
        subprocess.run(cmd, check=True)
        self.files = sorted(f for f in os.listdir(self.dir) if f.endswith(".jpg"))
        if not self.files:
            raise RuntimeError("视频抽帧失败：%s" % src)
        self._cur = {}

    def frame(self, i):
        f = self.files[i % len(self.files)]
        if f not in self._cur:
            im = Image.open(os.path.join(self.dir, f)).convert("RGB")
            self._cur = {f: im}                 # 只留一张，省内存
        return self._cur[f]


# ================================================================
# 字幕（深底规格：米白字 + 深描边）
# ================================================================

def tokenize(s):
    toks, buf = [], ""
    for ch in s:
        if ch.isascii() and (ch.isalnum() or ch in "%.+-/"):
            buf += ch
        else:
            if buf:
                toks.append(buf)
                buf = ""
            toks.append(ch)
    if buf:
        toks.append(buf)
    return toks


PUNCT = "，。！？、：；）】》"


def _orphan_fix(lines):
    """末行只剩一个字时，从前一行搬一个字下来（禁孤字行）。
    2026-11-05：A/B 两条片的 s04/s05 出现过「挑。」「住。」这种一行只剩一个字的尾巴，
    读起来像排版事故。只在末行实字 ≤1 时触发，不改变字号/行宽，只挪断行位置。"""
    if len(lines) < 2:
        return lines
    if sum(1 for ch in lines[-1] if ch not in PUNCT) > 1:
        return lines
    toks = tokenize(lines[-2])
    if len(toks) < 2:
        return lines
    moved = toks[-1]
    rest = toks[:-1]
    if moved in PUNCT:                     # 别让末行以逗号句号开头
        if len(toks) < 3:
            return lines
        moved = toks[-2] + toks[-1]
        rest = toks[:-2]
    lines[-2] = "".join(rest)
    lines[-1] = moved + lines[-1]
    return lines


# 行首禁字：虚词/助词/数词。中文按字断行偶尔会把词劈开
# （「配料表头 / 一位就写着」「想怎 / 么搭」「由不由 / 得自己」），看着像排版事故。
# 2026-11-05：只在**行首撞禁首字**时把上一行末字搬下来，不做「均衡搬运」——
# 试过均衡，反而把「生椰拿铁」「剑盾」这类专名拆开、还把「、」搬到行首，更难看。
HEAD_FORBID = "的了得地么着过们个种些就都还也而但并和与及或吗呢吧啊是" \
              "一二三四五六七八九十百千万"


def _balance(lines, f, max_w):
    """行首撞禁首字 → 把这个字**推回上一行**（不是把上一行的字搬下来）。

    方向搞反过：搬下来只是把「第|一行」变成「第|一行」的另一种切法，
    推上去才能得到「配料表第一行|就是」→「配料表第一行就是|全麦粉」。

    三条硬保护：上一行加字后不超宽；本行不能被掏空；行数严格不变
    （draw_sub 只渲染前两行，行数一变就丢字）。"""
    if len(lines) < 2:
        return lines
    for i in range(len(lines) - 1, 0, -1):
        guard = 0
        while (lines[i] and lines[i][0] in HEAD_FORBID
               and len(lines[i]) > 2 and guard < 4):
            # ★ 上一行已经停在标点上，说明断点本来就是合规的，别再去动它。
            #   踩过的坑：「…生椰拿铁，」/「三个味，随手挑。」被「三」「个」是数词
            #   这条规则一路推回去，最后推成「…三个」/「味，随手挑。」，反而拆了词。
            if lines[i - 1][-1] in PUNCT:
                break
            ch = lines[i][0]
            if f.getlength(lines[i - 1] + ch) > max_w:
                break
            if sum(1 for c in lines[i][1:] if c not in PUNCT) <= 1:
                break                       # 别把末行推成孤字
            lines[i - 1] += ch
            lines[i] = lines[i][1:]
            guard += 1
    return lines


def _last_punct_cut(s):
    """最后一个标点之后的切点（没有标点返回 0）。"""
    for i in range(len(s) - 1, -1, -1):
        if s[i] in PUNCT:
            return i + 1
    return 0


def wrap_text(text, f, max_w):
    lines, cur = [], ""
    for t in tokenize(text):
        cand = cur + t
        if not cur or f.getlength(cand) <= max_w:
            cur = cand
            continue
        if t in PUNCT:                       # 标点跟着上一行走，不甩到行首
            lines.append(cur + t)
            cur = ""
            continue
        # ★ 优先断在最近的标点后（2026-11-05）
        #   按字断行会把「配料表第一行|就是」「想怎|么搭」「由不由|得自己」劈开，
        #   而口播句逗号密，断在标点后既合规又像人排的。
        #   两个保险：切点不能太靠前（否则首行过短），余下部分 + 本字不能超宽。
        cut = _last_punct_cut(cur)
        if cut and cut >= len(cur) * 0.35 and f.getlength(cur[cut:] + t) <= max_w:
            lines.append(cur[:cut])
            cur = cur[cut:] + t
        else:
            lines.append(cur)
            cur = t
    if cur:
        lines.append(cur)
    lines = _balance(lines, f, max_w)
    return _orphan_fix(lines)


def draw_sub(d, text, alpha=255, size=58):
    f = font(size)
    lines = wrap_text(text, f, int(W * 0.84))[:2]
    lh = int(size * 1.32)
    top = SUB_Y - lh * len(lines)
    for i, ln in enumerate(lines):
        y = top + lh * i + lh // 2
        d.text((W // 2, y), ln, font=f, fill=(6, 6, 6), anchor="mm",
               stroke_width=10, stroke_fill=(6, 6, 6, int(alpha * 0.45)))
        d.text((W // 2, y), ln, font=f, fill=(252, 250, 244, alpha), anchor="mm",
               stroke_width=5, stroke_fill=(12, 12, 12, alpha))
        d.text((W // 2, y), ln, font=f, fill=(252, 250, 244, alpha), anchor="mm")


# ================================================================
# 重点字
# ================================================================

_kw_cache = {}


def kw_style(spec, idx, text):
    """颜色：plan 里显式写 > 数字/价格类用砖红 > 其余暖黄/冷白隔句轮换。"""
    if isinstance(spec, dict) and spec.get("color") in KW_STYLES:
        return spec["color"]
    if any(k in text for k in ("mg", "%", "拍", "元", "折", "瓶")):
        return "red"
    return "sun" if idx % 2 == 0 else "ice"


def make_kw(text, style="sun", scale=1.0):
    """斜贴块 + 黑边。底色做一道极轻竖向渐变：纯平色块在 H.264 里会“呼吸”，
    加了渐变与内描边，亮部就不会逐帧抽动（老板反馈的“闪”就是这个）。

    scale：放不下时整体缩一档（1.0 / 0.88 / 0.76 / 0.64），字型不变只缩放，
           比「硬塞到某个角落」体面得多。"""
    key = (text, style, round(scale, 3))
    if key in _kw_cache:
        return _kw_cache[key]
    st = KW_STYLES[style]
    sz = KW_SIZE
    f = font_kw(sz)
    while f.getlength(text) > KW_MAX_W and sz > 52:
        sz -= 4
        f = font_kw(sz)
    tw = int(f.getlength(text))
    w, h = tw + 72, int(sz * 1.62)
    pad = 30
    # 底：竖向微渐变（纯平色块在 H.264 里会「呼吸」，加渐变+内描边就不抖了）
    grad = Image.new("RGB", (1, h), tuple(st["bg"]))
    px = grad.load()
    for y in range(h):
        k = 1.045 - 0.095 * (y / max(1, h - 1))
        px[0, y] = tuple(max(0, min(255, int(c * k))) for c in st["bg"])
    body = grad.resize((w, h), Image.BILINEAR)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1],
                                           radius=int(h * 0.24), fill=255)
    body = body.convert("RGBA")
    body.putalpha(mask)
    d0 = ImageDraw.Draw(body)
    d0.rounded_rectangle([0, 0, w - 1, h - 1], radius=int(h * 0.24),
                         outline=st["edge"] + (255,), width=7)
    d0.rounded_rectangle([9, 9, w - 10, h - 10], radius=int(h * 0.18),
                         outline=(255, 255, 255, 40), width=2)
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle(
        [pad + 4, pad + 9, pad + w + 4, pad + h + 9], radius=int(h * 0.24), fill=120)
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(sh)
    img.alpha_composite(shadow)
    img.alpha_composite(body, (pad, pad))
    dd = ImageDraw.Draw(img)
    dd.text((pad + w // 2, pad + h // 2 - 2), text, font=f, fill=st["fg"] + (255,),
            anchor="mm")
    img = img.rotate(-3.2, expand=True, resample=Image.BICUBIC)
    if abs(scale - 1.0) > 1e-3:
        nw = max(8, int(round(img.width * scale)))
        nh = max(8, int(round(img.height * scale)))
        img = img.resize((nw, nh), Image.LANCZOS)
    _kw_cache[key] = img
    return img


def sq_crop(im, size):
    """方图：先缩到刚好盖满，再居中裁 1:1（不拉伸、不留白）"""
    sc = max(size / float(im.width), size / float(im.height))
    im2 = im.resize((max(size, int(im.width * sc) + 1),
                     max(size, int(im.height * sc) + 1)), Image.LANCZOS)
    x, y = (im2.width - size) // 2, (im2.height - size) // 2
    return im2.crop((x, y, x + size, y + size))


def sq_card(im, size, radius=SQ_RADIUS):
    """方图卡：圆角 + 浅色细边 + 柔投影，跟参考图一样「贴在墙上的一张照片」"""
    pad = SQ_PAD
    cv = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    sh = Image.new("L", cv.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle(
        [pad, pad + 12, pad + size, pad + size + 12], radius=radius, fill=170)
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    shadow = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    shadow.putalpha(sh.point(lambda v: int(v * 0.65)))
    cv.alpha_composite(shadow)
    body = sq_crop(im, size).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    body.putalpha(mask)
    cv.alpha_composite(body, (pad, pad))
    ImageDraw.Draw(cv).rounded_rectangle([pad, pad, pad + size - 1, pad + size - 1],
                                         radius=radius, outline=(248, 244, 236, 235), width=5)
    return cv, pad


_big_cache = {}


def big_char(ch, size=SQ_CHAR):
    """参考图那种纯红大字：暗投影 + 奶油细边，深底上也立得住"""
    key = (ch, size)
    if key in _big_cache:
        return _big_cache[key]
    f = font_kw(size)
    pad = 60
    im = Image.new("RGBA", (size * 2 + pad * 2, size * 2 + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((im.width // 2 + 6, im.height // 2 + 9), ch, font=f, anchor="mm",
           fill=(0, 0, 0, 150), stroke_width=0)
    im = im.filter(ImageFilter.GaussianBlur(6))
    sharp = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d2 = ImageDraw.Draw(sharp)
    d2.text((im.width // 2, im.height // 2), ch, font=f, anchor="mm",
            fill=(0, 0, 0, 70), stroke_width=6)      # 极淡的暗边，压住背景细节
    d2.text((im.width // 2, im.height // 2), ch, font=f, anchor="mm",
            fill=SQ_RED + (255,), stroke_width=2)
    im.alpha_composite(sharp)
    box = im.getbbox()
    im = im.crop(box)
    _big_cache[key] = im
    return im


def ease_out_cubic(p):
    p = max(0.0, min(1.0, p))
    return 1.0 - (1.0 - p) ** 3


def _hit(a, b, gap=12):
    return not (a[2] + gap < b[0] or b[2] + gap < a[0]
                or a[3] + gap < b[1] or b[3] + gap < a[1])


def kw_delay(shot):
    """重点字什么时候出：**所有元素都落定之后**再等 KW_SETTLE。

    老板 2026-11-03：「出现两个画面的时候，要先把这两个画面弹出来之后再显示重点字，
    不然这个重点字就在飘」。早字落在元素还在长大时，一是抢镜，二是 kw_place 拿
    半成品 bbox 定位，元素落定后字会被迫跳位 —— 看起来就是「飘」。

    ⚠️ 贴纸走路是 MOTION_DUR（0.62s），图片是硬切（HARD_IN 0.06s）—— 两者必须分开算，
    统一按 PULL 算会让重点字插在贴纸动效中间。
    """
    els = shot["els"]
    tail = 0.0
    for el in els:
        dur = MOTION_DUR if el.get("kind", "sticker") == "sticker" else HARD_IN
        tail = max(tail, float(el.get("off", 0.02)) + dur)
    return max(KW_IN, tail + KW_SETTLE)


# ---------------- 入场动效分派 ----------------
# 老板 2026-11-03：「这 8 版动效都可以」—— 全部启用，按镜轮换。
MOTION_CYCLE = ["slide_up", "focus", "pop", "slide_in",
                "wipe", "squash", "swing", "iris"]
# 有图片的镜：卡片硬切先到场，人物再「走进画面压上去」。
# 排除 iris —— 人物身上开圆洞展开会像马赛克，且和硬切的图抢戏。
MOTION_WITH_CARD = ["slide_in", "slide_up", "focus", "pop", "wipe", "slide_in"]


def pick_motion(idx, has_card, prev=None):
    """按镜号确定性分派，保证**相邻两句实际用的不是同一种**（prev 传上一镜真正用的那种）。"""
    pool = MOTION_WITH_CARD if has_card else MOTION_CYCLE
    kind = pool[idx % len(pool)]
    for shift in (1, 2):
        if kind != prev:
            break
        kind = pool[(idx + shift) % len(pool)]
    return kind


def assign_motions(tl):
    """全片动效一次性排好，写进 shot["_motion"]。
    不能在渲染循环里靠「上一镜索引」反推 —— 相邻两镜可能落在不同的候选池里，
    那样会排出一模一样的连续两句（实测 s01/s02 都是 slide_up、s10/s11 都是 pop）。"""
    last = None
    for i, s in enumerate(tl):
        els = s.get("els") or [s]
        has_sticker = any(e.get("kind", "sticker") == "sticker" for e in els)
        has_card = any(e.get("kind", "sticker") != "sticker" for e in els)
        if not has_sticker:                  # 纯图镜没人动，不占动效名额、也不更新 last
            s["_motion"] = None
            continue
        k = pick_motion(i, has_card, last)
        s["_motion"] = k
        last = k
    return tl


def build_clear_mask(items, card_top=None):
    """把本镜所有元素合成一张「不许压」的布尔图（1920×1080）。

    ★ 贴纸用**真实 alpha 轮廓**，不用外接矩形 —— 矩形会把腋下、腿间那些大片
      透明区也算成障碍，逼得重点字处处「撞墙」，最后只能兜底糊到脸上。
      老板 2026-11-03：「重点字挡住人物的脸了」，根因就是这个。
    卡片是实心矩形，整块算障碍。
    """
    m = np.zeros((H, W), bool)
    for it in items:
        if it[0] == "rect":
            l, t, r, b = it[1]
            l, t = max(0, int(l)), max(0, int(t))
            r, b = min(W, int(r)), min(H, int(b))
            if r > l and b > t:
                m[t:b, l:r] = True
        else:                                        # ("sticker", sx, sy, alpha01)
            _, sx, sy, al = it
            hh, ww = al.shape
            ys, xs = np.nonzero(al > 0.30)
            if len(ys):
                yy = np.clip(sy + ys, 0, H - 1)
                xx = np.clip(sx + xs, 0, W - 1)
                m[yy, xx] = True
    return m


def kw_place(w, h, mask, kind, zone, idx, card_top=None, strict=True):
    """给重点字找一个**真正压不到主体**的位置。

    候选：两侧（离主体远的那侧优先）× 多档高度，另外加一档「贴着卡片上沿」。
    strict=True 时一个重叠像素都不接受，找不到返回 None，由上层缩字号重试；
    strict=False 时返回重叠最小的位置（兜底，闸门会报错）。

    ⚠️ 位置只能由**镜号 + 静态布局**决定，绝不能拿「上一帧站在哪边」当输入：
    那样每帧都会反转候选顺序，字会左右横跳——老板说的「重点字在闪」就是这个。
    """
    margin = KW_KEEP_MARGIN
    left = margin + w // 2
    right = W - margin - w // 2
    if left - w // 2 < 0 or right + w // 2 > W:      # 字比整条还宽，塞不进
        return None

    order = [right, left] if zone == "L" else ([left, right] if zone == "R"
                                              else ([left, right] if idx % 2 == 0
                                                    else [right, left]))
    # 高度候选：卡片镜先「底边贴卡片上沿」，再往上抬；贴纸镜从上角带往下排
    ys = []
    if card_top is not None:
        ys.append(card_top - KW_GAP - h // 2)
    base = KW_Y_CARD if kind in ("card", "vcard") else KW_Y_STICKER
    # 2026-11-03 字号放大到 142 后，原来 4 个高度档不够用（块高 230，举铁双手举高
    # 那类镜两个角全占）→ 改成沿纵向每 40px 扫一遍，先近后远，找到空位就停。
    ys += [base] + [base + d for d in range(-160, 361, 40) if d != 0]
    seen = set()
    best = None
    for y in ys:
        y = max(h // 2 + 6, int(y))
        if y in seen:
            continue
        seen.add(y)
        for cx in order:
            box = (cx - w // 2, y - h // 2, cx + w // 2, y + h // 2)
            if box[1] < 4 or box[3] > SUB_Y - 24 or box[0] < 4 or box[2] > W - 4:
                continue
            # 外扩 30px 再判：贴纸落定后还有 ±2° 摇晃和呼吸，光算静态轮廓会在
            # 摇晃到最外侧那几帧被"啃"掉一个角。
            l, t = max(0, box[0] - KW_SHAKE_PAD), max(0, box[1] - KW_SHAKE_PAD)
            r, b = min(W, box[2] + KW_SHAKE_PAD), min(H, box[3] + KW_SHAKE_PAD)
            overlap = int(mask[t:b, l:r].sum())
            if overlap == 0:
                return cx, y, ("LT" if cx < W // 2 else "RT")
            if best is None or overlap < best[0]:
                best = (overlap, cx, y, ("LT" if cx < W // 2 else "RT"))
    if strict:
        return None
    return (best[1], best[2], best[3]) if best else (W // 2, 6 + h // 2, "C")


# ================================================================
# 主流程
# ================================================================

def build_timeline(plan, vo):
    t = 0.0
    out = []
    for i, s in enumerate(plan["shots"]):
        rec = vo.get(s["id"])
        if rec is None:
            raise KeyError("vo_index 里没有 %r —— 配音没跑或 id 对不上" % s["id"])
        dur = float(rec["dur"])
        text = s.get("text") or rec.get("text") or ""
        items = s.get("els") or [s]
        out.append({"id": s["id"], "text": text, "start": round(t, 3),
                    "end": round(t + dur, 3), "dur": round(dur, 3),
                    "els": items, "kind": s.get("kind", "sticker"),
                    "kw": s.get("kw"),
                    # 音效要一路带到 timeline，混音那步才拿得到（2026-11-03 补：
                    # 之前只有 plan 里有，mix 读 timeline 时全丢了，13 镜全靠轮换）
                    "sfx": s.get("sfx"), "sfx_vol": s.get("sfx_vol")})
        t += dur + (GAP if i < len(plan["shots"]) - 1 else 0)
    return round(t, 3), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--vo", required=True, help="vo_index.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bg", default=None, help="预设 id / random；缺省走 bg_lib.DEFAULT")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--crf", type=int, default=18,
                    help="默认 18；交付体积要压到 40MB 以内时用 20（实测 36s 片 47MB→34MB）")
    ap.add_argument("--flush", action="store_true", help="每段打印一次进度")
    ap.add_argument("--start", type=float, default=0.0,
                    help="从第 N 秒开始渲染（跳帧，不改变时间轴语义）。"
                         "用于「片头由别的段落吃掉」时分段渲再拼接，避免二次压缩")
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    vo = {v["id"]: v for v in json.load(open(a.vo, encoding="utf-8"))}

    bg_id = a.bg or plan.get("bg") or bg_lib.DEFAULT
    if bg_id == "random":
        rng = np.random.default_rng(a.seed)
        bg_id = bg_lib.random_preset(plan.get("bg_group", "comic_dark"), rng=rng)
    total, tl = build_timeline(plan, vo)
    assign_motions(tl)
    print("背景 %s（%s）｜%d 句｜%.2fs｜%d 帧" % (
        bg_id, bg_lib.REGISTRY[bg_id]["name"], len(tl), total,
        int(round(total * a.fps))))
    print("动效 " + " ".join("%s:%s" % (s["id"], s.get("_motion")) for s in tl
                            if any(e.get("kind", "sticker") == "sticker"
                                   for e in (s.get("els") or [s]))))

    bg = bg_lib.Background(bg_id, W, H)
    stickers = StickerLib()
    cards = CardFactory()
    vcards = {}

    nf = int(round(total * a.fps))
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", str(a.fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
           "-pix_fmt", "yuv420p", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    rng = np.random.default_rng(a.seed or 7)
    grains = []
    for _ in range(4):
        n = rng.normal(0, 2.6, (H // 2, W // 2)).astype(np.float32)
        grains.append(np.asarray(Image.fromarray(
            np.clip(128 + n, 0, 255).astype(np.uint8), "L").resize((W, H), Image.BILINEAR)
        ).astype(np.float32) - 128.0)

    cur_i = -1
    prev_kw_side = None
    skip = int(round(max(0.0, a.start) * a.fps))
    if skip:
        print("从 %.3fs（第 %d 帧）起渲，前面交给片头段" % (a.start, skip))
    for fi in range(skip, nf):
        tt = fi / float(a.fps)
        if cur_i < 0 or not (tl[cur_i]["start"] <= tt < tl[cur_i]["end"]):
            new_i = next((i for i, s in enumerate(tl) if s["start"] <= tt < s["end"]), len(tl) - 1)
            if new_i != cur_i:                 # 换镜时把上一镜的缓存丢掉，峰值内存才压得住
                cards_cache.clear()
                if len(stickers.masters) > 4:
                    stickers.masters.clear()
            cur_i = new_i
        shot = tl[cur_i]

        arr = bg.frame(tt).astype(np.float32) + grains[fi % len(grains)][..., None]
        frame = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

        # ---- 整屏铺满（兜底） ----
        subj = []
        subj_masks = []          # 兜底为空，避免 full 分支描字时未定义
        if shot["kind"] == "full":
            el = shot["els"][0]
            im = Image.open(el["src"]).convert("RGB")
            sc = max(W / im.width, H / im.height)
            im = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.LANCZOS)
            frame = im.crop(((im.width - W) // 2, (im.height - H) // 2,
                             (im.width - W) // 2 + W, (im.height - H) // 2 + H)).convert("RGBA")
        else:
            two = len(shot["els"]) > 1
            kdel = kw_delay(shot)              # 重点字/拆字：等所有元素落定之后
            subj = []
            # ★ 图层顺序：图片在后（硬切、先画）、贴纸在前（动效、后画、压住图边）
            #   老板 2026-11-03：「人物动效进来的时候可以占住图片的一部分，就显出层次感了」
            els_ordered = sorted(shot["els"],
                                 key=lambda e: 1 if e.get("kind", "sticker") == "sticker" else 0)
            card_box = None
            subj_masks = []          # 给重点字避让用：贴纸存真实 alpha，卡片存矩形
            for el in els_ordered:
                kind = el.get("kind", "sticker")
                lt = tt - shot["start"] - float(el.get("off", 0.02))
                if lt < 0:
                    continue
                zone = el.get("zone", "C")
                cx = int(W * Z[zone])

                if kind == "sticker":
                    is_teller = el.get("role") == "teller"
                    h = int(el.get("h") or (TELLER_H if is_teller else STICKER_H))
                    st = stickers.load(el["src"])
                    asp = st.width / float(st.height)
                    max_w = 2 * min(cx - 40, W - 40 - cx)
                    h = min(h, int(max_w / asp))
                    base = BASE_Y - int(el.get("lift", 0))     # 讲解位抬高，脚不被字幕压
                    # 入场动效：plan 可指定 motion / dir，否则按镜号轮换
                    mk_kind = el.get("motion") or shot.get("_motion") or "slide_up"
                    # 人物从自己那一侧的画外走进来，不横穿卡片
                    dirv = int(el.get("dir", 1 if zone in ("R", "C") else -1))
                    prm = MK.params(mk_kind, min(1.0, lt / MOTION_DUR), dirv)
                    # ★ 落定后常驻微动：呼吸 + 轻微摇晃（老板 2026-11-03）
                    #   只叠在入场之上，不参与 wipe/iris 的遮罩阶段；seed 按镜号错相位，
                    #   同一个姿势在两条片里不会同步摆，看着就不像循环素材。
                    if lt > MOTION_DUR:
                        MK.idle_apply(prm, lt - MOTION_DUR,
                                      seed=cur_i * 3 + (5 if zone == "R" else 0), h=h)
                    s, sh = stickers.frame_m(el["src"], h, el.get("flip", False), prm)
                    # ★ 有图片时人物压住图边 OVERLAP 像素：先把图当背景，人当前景
                    if card_box is not None:
                        c_left, c_right = card_box[0], card_box[2]
                        # 压边量按卡片宽自适应：小卡片别压掉 1/4，大卡片压 96 又不明显
                        ov = min(OVERLAP, int((c_right - c_left) * 0.16))
                        if (c_left + c_right) // 2 >= W // 2:      # 图在右 → 人压图左边
                            cx = c_left + ov - s.width // 2
                        else:                                       # 图在左 → 人压图右边
                            cx = c_right - ov + s.width // 2
                        cx = max(s.width // 2 + 16, min(W - 16 - s.width // 2, cx))
                    cx += int(round(prm.dx))
                    pad = int(round(BOTTOM_PAD * h / 1000.0))
                    sy = base - s.height + pad + int(round(prm.dy))
                    sx = cx - s.width // 2
                    if sh is not None:
                        frame.alpha_composite(sh, (sx, base - sh.height // 2 + int(round(prm.dy * 0.4))))
                    # 压图时给人物一圈柔和分离阴影，人才「浮」在图片前面
                    if card_box is not None and prm.alpha > 0.45:
                        sil = s.getchannel("A").filter(ImageFilter.GaussianBlur(7))
                        sil = sil.point(lambda v: int(v * 0.55))
                        shadow = Image.new("RGBA", s.size, (6, 6, 8, 0))
                        shadow.putalpha(sil)
                        frame.alpha_composite(shadow, (sx + 8, sy + 10))
                    frame.alpha_composite(s, (sx, sy))
                    subj.append((sx, sy, sx + s.width, sy + s.height))
                    subj_masks.append(("sticker", sx, sy,
                                       np.asarray(s.getchannel("A"), np.float32) / 255.0))

                elif kind == "sqcard":
                    # 方图居中 + 左右拆字（参考图 IMG_3303）。这两个大字就是本镜的重点字，
                    # 不再另叠上角便签 —— 一帧的元素数也不许破 2。
                    size = int(el.get("s") or SQ_SIZE)
                    content = Image.open(el["src"]).convert("RGB")
                    skey = ("sq", el["src"], size)
                    if skey not in cards_cache:
                        cards_cache[skey] = sq_card(content, size)
                    card, cpad = cards_cache[skey]
                    cy = int(el.get("cy", SQ_CY))
                    cxx = int(el.get("cx", W // 2))
                    frame.alpha_composite(card, (cxx - card.width // 2, cy - card.height // 2))
                    card_box = (cxx - card.width // 2, cy - card.height // 2,
                                cxx + card.width // 2, cy + card.height // 2)
                    subj.append(card_box)
                    kwd = shot.get("kw")
                    if isinstance(kwd, dict) and (kwd.get("l") or kwd.get("r")):
                        csz = int(kwd.get("size") or min(SQ_CHAR, int(size * 0.42)))
                        half = size // 2 + cpad
                        avail = int(W / 2 - half - SQ_GAP - 44)   # 每侧可用宽度（留 44px 安全边，贴边就显裁）
                        # 拆字跟重点字同一口径：图先落定，再出左右大字
                        cp = min(1.0, max(0.0, (lt - (kdel - float(el.get("off", 0.02)))) / 0.22))
                        for ch, side in ((kwd.get("l"), -1), (kwd.get("r"), 1)):
                            if not ch:
                                continue
                            cimg = big_char(ch, csz)
                            # 多字符（300mg / SGS）按可用宽度自动缩字号，不许溢出画边
                            if cimg.width > avail:
                                cimg = big_char(ch, max(56, int(csz * avail / float(cimg.width))))
                            if cp < 1.0:
                                ca = int(255 * cp)
                                cimg = cimg.copy()
                                cimg.putalpha(cimg.getchannel("A").point(lambda v: int(v * ca)))
                            x = (cxx - half - SQ_GAP - cimg.width // 2 if side < 0
                                 else cxx + half + SQ_GAP + cimg.width // 2)
                            frame.alpha_composite(cimg, (x - cimg.width // 2,
                                                         cy - cimg.height // 2))
                else:                                    # card / vcard —— 一律硬切，不做动效
                    ar = el.get("ar", "16x9")
                    aw, ah = _ar(ar)
                    bw = int(el.get("w") or (CARD_MIN_W if two else CARD_MAX_W))
                    bp = int(el.get("h") or (CARD_MIN_H if two else CARD_MAX_H))
                    bw = min(bw, int(bp * aw / ah))
                    if zone != "C":                      # 左右区的卡片不许顶到画边
                        bw = min(bw, 2 * min(cx - 40, W - 40 - cx))
                    bh = int(round(bw * ah / aw))
                    ring = el.get("ring")             # 动态红圈：逐帧画，不画死在素材里
                    if kind == "vcard":
                        key = el["src"]
                        if key not in vcards:
                            vcards[key] = VideoCard(el["src"], ar, bw, bh, a.fps)
                        content = vcards[key].frame(int(round(lt * a.fps)))
                        if ring:
                            content = _ring_overlay(content, ring, lt)
                        card = cards.make(content, bw, bh)      # 视频逐帧现做，不缓存
                    elif ring:
                        # 带圈的静图不能进普通缓存（圈每帧都在变），只缓存裁好的底图
                        bkey = ("ringbase", el["src"], bw, bh)
                        if bkey not in cards_cache:
                            cards_cache[bkey] = fit_crop(Image.open(el["src"]), bw, bh, ar)
                        card = cards.make(
                            _ring_overlay(cards_cache[bkey], ring, lt), bw, bh)
                    else:
                        key = ("ic", el["src"], bw, bh)
                        if key not in cards_cache:
                            cards_cache[key] = cards.make(
                                fit_crop(Image.open(el["src"]), bw, bh, ar), bw, bh)
                        card = cards_cache[key]
                    cy = int(el.get("cy", CARD_CY))
                    frame.alpha_composite(card, (cx - card.width // 2, cy - card.height // 2))
                    card_box = (cx - card.width // 2, cy - card.height // 2,
                                cx + card.width // 2, cy + card.height // 2)
                    subj.append(card_box)
                    subj_masks.append(("rect", card_box))
                    shot["_card_top"] = card_box[1]

        lt = tt - shot["start"]
        if lt > 0.06:
            alpha = int(255 * min(1.0, (lt - 0.06) / 0.16))
            draw_sub(ImageDraw.Draw(frame), shot["text"], alpha)

        # ---- 重点字：所有元素落定后才出，不压主体，句末跟着淡出 ----
        kws = shot.get("kw")
        if kws and shot["kind"] != "sqcard":
            kdel = kw_delay(shot)
        else:
            kdel = KW_IN
        if kws and lt > kdel and shot["kind"] != "sqcard":
            kt = kws if isinstance(kws, str) else (kws.get("t") or kws.get("text") or "")
            if kt:
                kstyle = kw_style(kws, cur_i, kt)
                # ★ 位置与字号每镜只算一次：所有元素此时都已落定，subj_masks 是全的。
                #   判尺寸用「满尺寸 kimg」（动画从 1.16 缩回 1.0，按最大时算最保守）。
                if "_kwpick" not in shot:
                    zone0 = shot["els"][0].get("zone", "C")
                    mask = build_clear_mask(subj_masks)
                    ct = shot.get("_card_top")
                    pick = None
                    if isinstance(kws, dict) and kws.get("pos") in ("LT", "RT"):
                        pick = (1.0, None)          # plan 强制位置，不信自动避让
                    else:
                        for sc in KW_SCALES:
                            ki = make_kw(kt, kstyle, scale=sc)
                            pos = kw_place(ki.width, ki.height, mask, shot["kind"],
                                           zone0, cur_i, ct, strict=True)
                            if pos:
                                pick = (sc, pos)
                                break
                    if pick is None:                # 全档都放不下 → 取重叠最小 + 记警告
                        ki = make_kw(kt, kstyle)
                        pick = (1.0, kw_place(ki.width, ki.height, mask, shot["kind"],
                                              zone0, cur_i, ct, strict=False))
                        shot["_kwfail"] = True
                    shot["_kwpick"] = pick
                    shot["_kbused"] = int(mask.sum())
                kscale, kpos = shot["_kwpick"]
                kimg = make_kw(kt, kstyle, scale=kscale)
                kp = min(1.0, (lt - kdel) / KW_PULL)
                ks = KW_SCALE_FROM - (KW_SCALE_FROM - 1.0) * ease_out_cubic(kp)
                left_t = shot["dur"] - lt
                ka = 1.0 if left_t > KW_OUT else max(0.0, left_t / KW_OUT)
                ka *= min(1.0, (lt - kdel) / 0.07)          # 头 2 帧快速淡入
                ww = max(8, int(round(kimg.width * ks)))
                hh = max(8, int(round(kimg.height * ks)))
                km = kimg if (ww, hh) == kimg.size else kimg.resize((ww, hh), Image.BILINEAR)
                if ka < 0.999:
                    km = km.copy()
                    km.putalpha(km.getchannel("A").point(lambda v: int(v * ka)))
                pos = kws.get("pos") if isinstance(kws, dict) else None
                if pos in ("LT", "RT"):
                    kcx = KW_MARGIN + ww // 2 if pos == "LT" else W - KW_MARGIN - ww // 2
                    kcy = (KW_Y_CARD if shot["kind"] in ("card", "vcard") else KW_Y_STICKER)
                    kw_side = pos
                else:
                    kcx, kcy, kw_side = kpos
                frame.alpha_composite(km, (kcx - ww // 2, kcy - hh // 2))

        proc.stdin.write(frame.convert("RGB").tobytes())
        if a.flush and fi % 150 == 0:
            print("  %d/%d  %s" % (fi, nf, shot["id"]), flush=True)

    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise SystemExit("ffmpeg 渲染失败")

    tlpath = os.path.splitext(a.out)[0] + ".timeline.json"
    json.dump({"bg": bg_id, "total": total, "fps": a.fps, "shots": tl},
              open(tlpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("→ %s\n→ %s" % (a.out, tlpath))


cards_cache = {}

if __name__ == "__main__":
    main()
