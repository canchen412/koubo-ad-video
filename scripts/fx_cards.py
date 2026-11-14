#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品段动效层：黑底金「老虎机数字卡」+ 黑底金「详情卡」。

口径（koubo-ad-video `references/自建fx动效层_PIL逐帧.md`）：
  · 数字卡：近纯黑卡底 #0A0A0B alpha238 / 金 #DBAD57 零发光 / 单位同金色墨迹底对齐 /
    纯白副标题 / 金色胶囊下划线 / 卡宽按内容收口
  · 滚动必须「能数得出来」：滑入0.32s → 滚数0.62s（easeOutQuint，逐位老虎机）→
    回弹0.16s → 停留 → 淡出0.24s；落定值必须等于文案数字（抽帧硬验收）
  · 详情卡：金标题 + 金短线 + 「白标签/金数值」两栏账 + 一行灰脚注；
    只写口播说过的数与词，不复述数字卡副标题
  · 数字卡与详情卡不许落同一坐标区；一律避开绿色主体（小绿人身体与手）

用法（卡片内容由外部 json 给，脚本本身不含任何品牌文案）：
  python fx_cards.py --work <工程目录> [--spec fx_spec.json] [v1 v2 v3 ...]

fx_spec.json 结构：
{
  "v1": {
    "num":    [["<镜句关键词>", "300", "mg", "<副标题>"], ...],
    "detail": [["<镜句关键词>", "<标题>", [["<标签>","<数值>"], ...], "<脚注>"], ...]
  }
}
镜句关键词 = 该版 phrases.txt 里那一句的原话片段（唯一命中即可）。
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FF = "/Users/yourname/.local/bin/ffmpeg"
GOLD = (219, 173, 87)
GOLD_LINE = (201, 162, 78)
CARD_BG = (10, 10, 11)
WHITE = (255, 255, 255)
GREY = (168, 168, 168)
# 重点数字的手绘红圈（2026-11-10 老板：说到多少克必须圈出来）
RING_RED = (235, 45, 40)
F_NUM = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
F_CN = "/System/Library/Fonts/Hiragino Sans GB.ttc"
W, H = 1920, 1080
FPS = 30


def draw_hand_ring(base, box, progress, color=RING_RED, width=7, seed=7, ss=2):
    """在 base(RGBA) 上画手绘感红圈，圈住 box=(x0,y0,x1,y1)。

    为什么不用 `ImageDraw.arc`：arc 是**正圆弧 + 等宽**，一眼看出是软件画的。
    手绘圈有三个特征，缺一个就假：①起笔与收笔**重叠过一点**（绕 1.10 圈，不是 1.00）；
    ②半径**不规则抖动**（三组不同频率正弦叠加，比 random 更稳、帧间不跳）；
    ③笔迹**两头细中间粗**。

    progress 0..1 控制「画到哪」，用于逐帧描线动效；2 倍超采样后再缩回，保证边缘不锯齿。
    """
    if progress <= 0.001:
        return
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    rx, ry = max(1.0, (x1 - x0) / 2.0), max(1.0, (y1 - y0) / 2.0)

    a0 = math.radians(-104)              # 起笔在左上，符合右手书写习惯
    total = math.tau * 1.10 * min(1.0, progress)   # 绕 1.10 圈 ⇒ 首尾自然叠一点
    n = max(2, int(240 * min(1.0, progress)))

    rnd = random.Random(seed)
    ph = [rnd.uniform(0, math.tau) for _ in range(3)]
    tilt = math.radians(-4)              # 整圈略斜，手画不会端端正正（超过 6° 左端会翘到字上）

    layer = Image.new("RGBA", (base.width * ss, base.height * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ct, st = math.cos(tilt), math.sin(tilt)
    for i in range(n + 1):
        u = i / float(n) if n else 0.0
        a = a0 + total * u
        wob = (1.0 + 0.052 * math.sin(3 * a + ph[0])
               + 0.028 * math.sin(5 * a + ph[1])
               + 0.016 * math.sin(9 * a + ph[2]))
        ex, ey = rx * wob * math.cos(a), ry * wob * math.sin(a)
        x = (cx + ex * ct - ey * st) * ss
        y = (cy + ex * st + ey * ct) * ss
        # 两头细中间粗：0.55 → 1.0 → 0.55
        r = width * ss * (0.55 + 0.45 * math.sin(math.pi * min(1.0, u))) * 0.5
        d.ellipse([x - r, y - r, x + r, y + r], fill=color + (255,))
    base.alpha_composite(layer.resize(base.size, Image.LANCZOS))


def load_spec(path):
    """读卡片配置：{版本: {num: [...], detail: [...]}}。缺 key 直接报错，不静默降级。"""
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    for v, d in spec.items():
        if not isinstance(d, dict) or "num" not in d:
            raise SystemExit(f"✗ {path} 里 {v} 缺 num 段")
        d.setdefault("detail", [])
    return spec


def ink(font, txt, stroke=0):
    """真栅格化取墨迹 bbox → (宽, 高, dx, dy)。CJK 的 textbbox 不可信。"""
    sz = font.size
    pad = sz + stroke * 2
    cw = max(sz * (len(txt) + 2), sz * 3) + pad * 2
    ch = sz * 3 + pad * 2
    c = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(c).text((pad, pad), txt, font=font, fill=255,
                           stroke_width=stroke, stroke_fill=255)
    bb = c.getbbox()
    return bb[2] - bb[0], bb[3] - bb[1], bb[0] - pad, bb[1] - pad


def round_card(cw, ch, radius=26):
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=radius,
                                          fill=CARD_BG + (238,))
    # 暗背景上也能看出卡片轮廓：2px 细亮边 + 顶部淡暖高光
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=radius,
                        outline=(255, 255, 255, 42), width=2)
    glow = Image.new("RGBA", (cw, 64), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(64):
        a = int(16 * (1 - i / 64) ** 2)
        gd.rectangle([0, i, cw, i], fill=(255, 236, 198, a))
    mask = Image.new("L", (cw, 64), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, 63], radius=radius, fill=255)
    img.paste(Image.alpha_composite(img.crop((0, 0, cw, 64)), glow), (0, 0), mask)
    return img


class NumCard:
    """黑底金数字卡，逐位老虎机滚动。ring=True 时落定后手绘红圈圈住数字。"""
    NUM_SZ, UNIT_SZ, SUB_SZ, PAD = 118, 56, 44, 46

    def __init__(self, big, unit, sub, ring=True):
        self.big, self.unit, self.sub, self.ring = big, unit, sub, ring
        self.f_num = ImageFont.truetype(F_NUM, self.NUM_SZ)
        self.f_unit = ImageFont.truetype(F_CN, self.UNIT_SZ)
        self.f_sub = ImageFont.truetype(F_CN, self.SUB_SZ)
        # 数字条：逐位竖排 0-9
        self.row_h = self.NUM_SZ + 12
        self.digit_w, self.digit_h, _, _ = ink(self.f_num, "0", stroke=2)
        self.strip = self._digit_strip()
        # 目标值各位置
        # ★2026-11-10：必须支持小数（15.4 / 38.8 / 2.8）。旧版 frame() 对每个字符
        #   做 int(ch)，遇到 '.' 直接 ValueError；且按 digit_w 等宽推进会把小数点
        #   撑成一个数字的宽度。这里改成**逐字符预排位置**，小数点按自身墨迹宽 + 窄间距。
        self.glyphs = []
        _x, _prev = self.PAD, None
        for _ch in big:
            _gap = 3 if (_ch == "." or _prev == ".") else 8
            _gw, _, _, _ = ink(self.f_num, _ch, stroke=2)
            self.glyphs.append((_ch, _x, _gw))
            _x += _gw + _gap
            _prev = _ch
        _last = self.glyphs[-1]
        nun = _last[1] + _last[2] - self.PAD
        uun = ink(self.f_num, big, stroke=2)[1]
        uw, uh, _, _ = ink(self.f_unit, unit)
        sw, sh, _, _ = ink(self.f_sub, sub)
        self.num_w, self.num_h = nun, uun
        self.unit_w, self.unit_h = uw, uh
        self.sub_w, self.sub_h = sw, sh
        self.block_w = max(nun + 18 + uw, sw)
        self.cw = self.block_w + self.PAD * 2
        # 顶部多留 20px：红圈要在数字上方 13px 起笔，按原 PAD=46 会把圈顶挤进圆角里
        self.num_top = self.PAD + 20
        self.sub_top = self.num_top + self.num_h + 54
        self.ch = self.sub_top + self.sub_h + 30 + 9 + self.PAD
        # 红圈范围（2026-11-10 按实测金色墨迹标定，不是估的）：
        #   「15.4 g」实测墨迹 x59–271 / y66–172（g 的降部比数字低 17px）；
        #   墨迹顶边 == num_top，数字底部 == num_top+num_h。
        #   ⇒ 左右各放 16/34、上下各放 18/31，圈比数字块大 2 成，才像「圈出来」不是「框住」。
        #   sub_top 同步下移，否则圈底会压到副标题第一行。
        _rb_x1 = self.PAD + self.num_w + 18 + self.unit_w + 34
        # ★圈右端必须离卡边 ≥30px：贴边看着像被卡片裁掉了半张圈。卡宽按此反推。
        self.cw = max(self.cw, int(_rb_x1) + 30)
        self.ring_box = (self.PAD - 16, self.num_top - 18,
                         _rb_x1, self.num_top + self.num_h + 31)

    def _digit_strip(self):
        """0-9 竖排，末尾再补一个 0 做进窗缓冲（否则滚到 9.x 会露透明底）。"""
        w = self.digit_w + 8
        h = self.row_h * 11
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for n in range(11):
            ch = str(n % 10)
            _, dh, _, dy = ink(self.f_num, ch, stroke=2)
            # 墨迹底对齐到本行底
            y = n * self.row_h + (self.row_h - dh) // 2 - dy
            d.text((4, y), ch, font=self.f_num, fill=GOLD + (255,),
                   stroke_width=2, stroke_fill=GOLD + (255,))
        return img

    def frame(self, val, alpha=255, ring=0.0):
        """val: 浮点数值（0..目标）。返回整卡 RGBA。ring: 红圈描线进度 0..1。"""
        img = round_card(self.cw, self.ch)
        d = ImageDraw.Draw(img)
        # 每位数字：目标值的第 i 位，滚动时从 0 转上去
        digits = self.big
        n = len(digits)
        _tgtval = float(digits.replace(",", ""))
        for i, (ch, gx, _gw) in enumerate(self.glyphs):
            if not ch.isdigit():
                # 小数点/千分位：不滚动，按墨迹垂直居中直接落金
                _, dh, _, dy = ink(self.f_num, ch, stroke=2)
                d.text((gx, self.num_top + (self.num_h - dh) // 2 - dy), ch,
                       font=self.f_num, fill=GOLD + (255,),
                       stroke_width=2, stroke_fill=GOLD + (255,))
                continue
            tgt = int(ch)
            # 滚动进度：整卡统一用 val/目标 的进度；每位错开一点做进位感
            frac = 0.0 if _tgtval == 0 else min(1.0, val / _tgtval)
            frac = min(1.0, frac * (1 + 0.08 * (n - 1 - i)))
            if frac >= 1.0:
                pos = float(tgt)
            elif tgt == 0:
                # 目标位是 0 的位也要转：从 9 转一圈落回 0，才像老虎机
                pos = (1.0 - frac) * 10.0 % 10.0
            else:
                pos = (frac * tgt) % 10
            y_off = int(pos * self.row_h) % (10 * self.row_h)
            crop = self.strip.crop((0, y_off, self.strip.width, y_off + self.row_h))
            img.paste(crop, (gx, self.num_top - (self.row_h - self.num_h) // 2), crop)
        # 单位：墨迹底对齐数字墨迹底
        uy = self.num_top + self.num_h - self.unit_h
        d.text((self.PAD + self.num_w + 18, uy), self.unit, font=self.f_unit,
               fill=GOLD + (255,))
        # 副标题
        d.text((self.PAD, self.sub_top), self.sub, font=self.f_sub, fill=WHITE + (255,))
        # 金色胶囊下划线
        cy = self.sub_top + self.sub_h + 30
        d.rounded_rectangle([self.PAD, cy, self.PAD + self.num_w + 18 + self.unit_w, cy + 9],
                            radius=5, fill=GOLD_LINE + (255,))
        if self.ring and ring > 0:
            draw_hand_ring(img, self.ring_box, ring, seed=len(self.big) * 13 + 7)
        if alpha < 255:
            a = img.split()[3].point(lambda v: v * alpha // 255)
            img.putalpha(a)
        return img

    def frames(self, dur, fade=0.24):
        """整段逐帧：滑入 0.32 + 滚数 0.62 + 回弹 0.16 + 停留 + 淡出 fade。"""
        nf = max(1, int(round(dur * FPS)))
        slide, roll, bounce = 0.32, 0.62, 0.16
        # 红圈：滚数落定、回弹收住之后才起笔（早画就成了圈空气），0.34s 描完一圈。
        # 卡太短就压不出来 —— 宁可明确跳过并留痕，也不要画半个圈。
        r0 = slide + roll + bounce + 0.02
        rdur = min(0.34, dur - r0 - fade - 0.02)
        do_ring = self.ring and rdur >= 0.12
        if self.ring and not do_ring:
            print(f"  ⚠️ 数字卡 {self.big}{self.unit} 只有 {dur:.2f}s，红圈来不及画，已跳过")
        out = []
        for i in range(nf):
            t = i / FPS
            if t < slide:
                u = t / slide
                e = 1 - (1 - u) ** 3              # 缓出
                dx = int((1 - e) * 90)
                dy = int((1 - e) * 46)
                al = int(255 * min(1.0, u / 0.55))
                val = 0.0
            elif t < slide + roll:
                u = (t - slide) / roll
                e = 1 - (1 - u) ** 5              # easeOutQuint
                dx = dy = 0
                al = 255
                val = e * float(self.big)
            elif t < slide + roll + bounce:
                dx = dy = 0
                al = 255
                val = float(self.big)
            elif t > dur - fade:
                u = (t - (dur - fade)) / fade
                dx = dy = 0
                al = int(255 * (1 - u))
                val = float(self.big)
            else:
                dx = dy = 0
                al = 255
                val = float(self.big)
            # 回弹：落定瞬间整卡放大再回落
            tt = t - slide - roll
            sc = 1.0
            if 0 <= tt < bounce:
                u = tt / bounce
                sc = 1.0 + 0.065 * (1 - u) ** 2
            f = self.frame(val, al,
                           min(1.0, (t - r0) / rdur) if (do_ring and t >= r0) else 0.0)
            if sc != 1.0:
                nw, nh = int(f.width * sc), int(f.height * sc)
                f = f.resize((nw, nh), Image.LANCZOS)
            out.append((f, dx, dy))
        return out


class DetailCard:
    """黑底金详情卡：金标题 + 金短线 + 白标签/金数值两栏账 + 灰脚注。

    ring_rows：要手绘红圈的**行号列表**（0 基）。老板 2026-11-10：
    「说到多少多少克的时候，一定要用卡片上面有个红圈圈一下」。
    """
    TITLE_SZ, LABEL_SZ, VALUE_SZ, FOOT_SZ, PAD = 37, 31, 35, 26, 40
    VALUE_FONT_NUM = F_NUM

    def __init__(self, title, rows, foot, ring_rows=()):
        self.title, self.rows, self.foot = title, rows, foot
        self.ring_rows = [int(x) for x in (ring_rows or [])]
        self.f_t = ImageFont.truetype(F_CN, self.TITLE_SZ)
        self.f_l = ImageFont.truetype(F_CN, self.LABEL_SZ)
        # ★数值字体按内容选：纯数字/单位用 DIN，含中文必须用中文字体
        #   （DIN 没有 CJK 字形，中文会渲成豆腐块 □□）
        self.f_v = ImageFont.truetype(self.VALUE_FONT_NUM, self.VALUE_SZ)
        self.f_v_cn = ImageFont.truetype(F_CN, self.VALUE_SZ)
        self.f_f = ImageFont.truetype(F_CN, self.FOOT_SZ)

        def vfont(txt):
            return self.f_v if all(ord(c) < 128 for c in txt) else self.f_v_cn

        tw, th, _, _ = ink(self.f_t, title)
        lw = max(ink(self.f_l, l)[0] for l, _ in rows)
        vw = max(ink(vfont(v), v)[0] for _, v in rows)
        fw, fh, _, _ = ink(self.f_f, foot)
        self.row_gap = 20
        rh = max(ink(self.f_l, "测")[1], ink(self.f_v, "0")[1],
                 ink(self.f_v_cn, "测")[1])
        content = max(tw, lw + 40 + vw, fw)
        self.cw = content + self.PAD * 2
        self.title_top = self.PAD
        self.line_y = self.title_top + th + 16
        self.rows_top = self.line_y + 9 + 30
        self.ch = self.rows_top + len(rows) * rh + (len(rows) - 1) * self.row_gap \
            + 26 + fh + self.PAD
        self.rh, self.tw, self.th = rh, tw, th
        self.lw, self.vw, self.fh = lw, vw, fh
        self.rows_top_ = self.rows_top
        # 每行红圈范围：圈住「数值 + 单位」那一列；数值太窄时按最小 110px 撑开，
        # 免得圈小到像句号。
        self.ring_boxes = {}
        for i in self.ring_rows:
            if not 0 <= i < len(rows):
                raise SystemExit(f"✗ 详情卡「{title}」ring_rows 给了 {i}，但只有 {len(rows)} 行")
            y = self.rows_top_ + i * (rh + self.row_gap)
            vx = self.PAD + self.lw + 40
            self.ring_boxes[i] = (vx - 12, y - 5,
                                  vx + max(self.vw, 110) + 12, y + rh + 5)

    def frame(self, reveal=1.0, alpha=255, rings=None):
        img = round_card(self.cw, self.ch)
        d = ImageDraw.Draw(img)
        d.text((self.PAD, self.title_top), self.title, font=self.f_t, fill=GOLD + (255,))
        # 金短线
        ln = int(self.tw * min(1.0, reveal * 2))
        d.rounded_rectangle([self.PAD, self.line_y, self.PAD + ln, self.line_y + 5],
                            radius=3, fill=GOLD_LINE + (255,))
        # 两栏账：逐行淡入
        y = self.rows_top_
        for i, (lab, val) in enumerate(self.rows):
            rv = max(0.0, min(1.0, (reveal - 0.35 - i * 0.13) / 0.25))
            if rv > 0:
                a = int(255 * rv)
                _, lh, _, _ = ink(self.f_l, lab)
                _, vh, _, _ = ink(self.f_v, val)
                d.text((self.PAD, y + (self.rh - lh) // 2), lab, font=self.f_l,
                       fill=WHITE + (a,))
                d.text((self.PAD + self.lw + 40, y + (self.rh - vh) // 2), val,
                       font=(self.f_v if all(ord(c) < 128 for c in val) else self.f_v_cn),
                       fill=GOLD + (a,))
            y += self.rh + self.row_gap
        # 脚注
        fy = self.rows_top_ + len(self.rows) * self.rh + (len(self.rows) - 1) * self.row_gap + 26
        fv = max(0.0, min(1.0, (reveal - 0.7) / 0.3))
        if fv > 0:
            d.text((self.PAD, fy), self.foot, font=self.f_f, fill=GREY + (int(255 * fv),))
        for i, pr in (rings or {}).items():
            if pr and i in self.ring_boxes:
                draw_hand_ring(img, self.ring_boxes[i], pr, width=6, seed=i * 31 + 11)
        if alpha < 255:
            a = img.split()[3].point(lambda v: v * alpha // 255)
            img.putalpha(a)
        return img

    def frames(self, dur, fade=0.24):
        nf = max(1, int(round(dur * FPS)))
        slide, rev = 0.30, 0.90
        # 红圈：逐行错开 0.20s 起笔，每圈 0.34s。各行都在淡出前收笔。
        r_start = {i: slide + rev + 0.02 + k * 0.20
                   for k, i in enumerate(sorted(self.ring_boxes))}
        rdur = 0.34
        if r_start:
            _room = dur - fade - 0.02 - max(r_start.values())
            rdur = min(0.34, max(0.12, _room))
        out = []
        for i in range(nf):
            t = i / FPS
            if t < slide:
                u = t / slide
                e = 1 - (1 - u) ** 3
                dx, dy = int((1 - e) * 70), int((1 - e) * 40)
                al, rv = int(255 * min(1.0, u / 0.55)), 0.0
            elif t < slide + rev:
                dx = dy = 0
                al = 255
                rv = (t - slide) / rev
            elif t > dur - fade:
                u = (t - (dur - fade)) / fade
                dx = dy = 0
                al = int(255 * (1 - u))
                rv = 1.0
            else:
                dx = dy = 0
                al, rv = 255, 1.0
            rings = {i: min(1.0, max(0.0, (t - s0) / rdur)) for i, s0 in r_start.items()
                     if t >= s0}
            out.append((self.frame(rv, al, rings), dx, dy))
        return out


def green_mask(p):
    im = Image.open(p).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (g > 70) & (g > r + 22) & (g > b + 22)


def occupy(mask, x, y, cw, ch):
    m = mask.copy()
    y0, y1 = max(0, y - 24), min(H, y + ch + 24)
    x0, x1 = max(0, x - 24), min(W, x + cw + 24)
    m[y0:y1, x0:x1] = True
    return m


def pick_pos(mask, cw, ch, margin=56, step=60):
    """滑窗扫描全画面找「绿色主体占比最低」的位置。

    不能用稀疏格点：格点一少，避不开人物时只能选「最不差」的那个，
    实测会落到 0.22~0.28 绿占比（＝两成面积压在胸肌上）。60px 步长够快也够密。
    字幕带（底部 128px）不落卡；已占位区在 mask 里已被置 True，自动避开。
    """
    best, bestscore = (margin, 132), 1e9
    ys = list(range(96, max(97, H - 128 - ch), step))
    xs = list(range(24, max(25, W - cw - 24), step))
    for y in ys:
        for x in xs:
            s = mask[y:y + ch, x:x + cw].mean()
            # 轻微偏好靠边：同分时左上/右上优先，观感更稳
            edge = 0.0 if (x < W * 0.28 or x + cw > W * 0.72) else 0.006
            if s + edge < bestscore:
                bestscore, best = s + edge, (x, y)
    return best, bestscore


def write_clip(frames, path, w, h):
    """逐帧 RGBA → qtrle/argb mov。

    ★画布必须比卡大一圈：滑入位移 dx/dy 在卡自身尺寸的画布上会被直接裁掉
    （表现为卡片顶部/右侧缺一块、数字只剩半截）。留 MARGIN 后卡片最终落在 (0,0)，
    overlay 时把 mov 左上角对准落位点即可，滑入就是「从右下角飘进来」。
    """
    MX, MY = 120, 80
    tmp = tempfile.mkdtemp(prefix="fxcard_")   # 每次新建，避免旧帧残留污染帧数
    for i, (f, dx, dy) in enumerate(frames):
        canvas = Image.new("RGBA", (w + MX, h + MY), (0, 0, 0, 0))
        canvas.paste(f, (dx, dy), f)
        canvas.save(f"{tmp}/{i:04d}.png")
    subprocess.run([FF, "-y", "-v", "error", "-framerate", str(FPS),
                    "-i", f"{tmp}/%04d.png", "-c:v", "qtrle", "-pix_fmt", "argb",
                    path], check=True)
    shutil.rmtree(tmp, ignore_errors=True)


def build(v, W_dir, spec):
    S = f"{W_dir}/{v}"
    phrases = [x.strip() for x in open(f"{S}/phrases.txt", encoding="utf-8").read().splitlines() if x.strip()]
    bounds = json.load(open(f"{S}/audio/shot_bounds.json", encoding="utf-8"))
    # ★2026-11-03 修缺：拆镜片（2026-10-28 起）phrases.txt 是「语音句」（如 11 行），
    #   shot_bounds 是「画面镜」（18 条）——两者行号语义不同，直接按 idx 索引会
    #   整片错位（卡落到别的镜、甚至算到负时长）。有 phrases_shots.txt 且行数与
    #   bounds 相等时一律以它为准；对不上就报错，不静默用错的。
    _ps = f"{S}/phrases_shots.txt"
    if os.path.exists(_ps):
        _sp = [x.strip() for x in open(_ps, encoding="utf-8").read().splitlines() if x.strip()]
        if len(_sp) == len(bounds):
            phrases = _sp
        else:
            raise SystemExit(
                f"✗ {v} phrases_shots.txt {len(_sp)} 行 ≠ shot_bounds {len(bounds)} 条，"
                f"索引会错位；先对齐再叠卡")
    elif len(phrases) != len(bounds):
        raise SystemExit(
            f"✗ {v} phrases.txt {len(phrases)} 行 ≠ shot_bounds {len(bounds)} 条，"
            f"索引会错位；先对齐再叠卡")
    cfg = json.load(open(f"{W_dir}/cfg_{v}.json", encoding="utf-8"))
    shift = float(cfg.get("cover_dur", 0.9))
    # ★2026-11-03：卷播片在 6.7/7 会再叠一层漂浮粒子 → final_dust.mp4 才是交付版。
    #   旧代码写死 final.mp4，卡就叠在「粒子层之前」的中间片上，交出去的那个文件
    #   里根本没有卡。有 final_dust 就叠它。
    # ★2026-11-10 修（本次实测踩到，封面整条丢干净了）：pipeline 6.5 贴完封面产的是
    #   `final_cov.mp4`，再 `os.replace` 成 `final.mp4` —— 一旦 replace 被文件锁/权限拦下
    #   （日志只有一行 ⚠️），`final.mp4` 还是**没封面**的底片，而这里只认 final.mp4，
    #   叠完卡交出去的成片第 0 帧就是黑的。候选顺序必须把 final_cov 排上。
    src = None
    _cands = [p for p in (f"{S}/render/final_dust.mp4",
                          f"{S}/render/final_cov.mp4",
                          f"{S}/render/final.mp4") if os.path.exists(p)]
    if not _cands:
        raise SystemExit(f"✗ {v} 找不到 final_dust.mp4 / final_cov.mp4 / final.mp4，先跑完合成")
    if _cands[0].endswith("final_dust.mp4"):
        src = _cands[0]                      # 粒子层是最后一道，永远优先
    else:
        # 只剩 final_cov / final 时按 mtime 取新的：重跑过 pipeline 却没清旧 cov 的话，
        # 直接按固定顺序会叠在上一次的旧片子上（封面/画面全是上一版的）。
        src = max(_cands, key=os.path.getmtime)
    if src.endswith("final_cov.mp4"):
        print(f"  ⚠️ {v} 用的是 final_cov.mp4（final.mp4 未含封面，rename 被拦过）")
    print(f"  {v} 叠卡源：{os.path.basename(src)}")
    outdir = f"{S}/render/num"
    os.makedirs(outdir, exist_ok=True)

    jobs = []
    mask = None
    # ── 先排数字卡（它们占住最好的两个角）──
    for raw in spec[v]["num"]:
        kw, big, unit, sub = raw[0], raw[1], raw[2], raw[3]
        # 第 5 项可选：[x, y] 强制坐标。仅在自动落位压到字幕/主体时手填。
        force = raw[4] if len(raw) > 4 and raw[4] else None
        # 第 6 项可选：时长秒数。缺省按句长自动取 1.9~2.4s；
        # 下一镜画面很满时（卡片会跨镜压主体）手填缩短，让它在切镜前收掉。
        dur_fix = float(raw[5]) if len(raw) > 5 and isinstance(raw[5], (int, float)) else None
        # 第 7 项可选：红圈开关（缺省 **开** —— 数字卡的存在意义就是把那个数指出来）
        do_ring = bool(raw[6]) if len(raw) > 6 else True
        idx = next((i for i, p in enumerate(phrases) if kw in p), None)
        if idx is None:
            sys.exit(f"✗ {v} 找不到镜句：{kw}")
        b0, b1 = bounds[idx]
        dur = dur_fix if dur_fix else min(2.4, max(1.9, (b1 - b0) + shift))
        start = round(b0 + shift + 0.15, 3)
        probe = f"{outdir}/probe_{big}.png"
        subprocess.run([FF, "-y", "-v", "error", "-ss", f"{b0 + shift + 0.55:.2f}",
                        "-i", src, "-frames:v", "1", probe], check=True)
        if mask is None:
            mask = green_mask(probe)
        card = NumCard(big, unit, sub, ring=do_ring)
        if force:
            (x, y), sc = (int(force[0]), int(force[1])), -1.0
        else:
            (x, y), sc = pick_pos(mask, card.cw, card.ch)
        mask = occupy(mask, x, y, card.cw, card.ch)
        clip = f"{outdir}/card_{big}.mov"
        write_clip(card.frames(dur), clip, card.cw, card.ch)
        jobs.append(dict(tag=f"{big}{unit}", start=start, end=round(start + dur, 3),
                         x=x, y=y, clip=clip, score=sc, w=card.cw, h=card.ch))
        print(f"  {v} 数字卡 {big}{unit}  {start:.2f}-{start + dur:.2f}s "
              f"落位({x},{y}) 绿占比{max(sc,0.0):.3f}{' (手填)' if sc < 0 else ''} 卡{card.cw}x{card.ch}")

    # ── 再排详情卡（避开数字卡已占位）──
    for raw in spec[v]["detail"]:
        kw, title, rows, foot = raw[0], raw[1], raw[2], raw[3]
        # 第 5 项可选：[x, y] 强制坐标（同上）；第 6 项可选：要红圈的行号列表
        force = raw[4] if len(raw) > 4 and raw[4] else None
        rrows = raw[5] if len(raw) > 5 and raw[5] else []
        idx = next((i for i, p in enumerate(phrases) if kw in p), None)
        if idx is None:
            sys.exit(f"✗ {v} 找不到详情卡镜句：{kw}")
        b0, b1 = bounds[idx]
        # 数字卡已占该句前段 → 详情卡往后错开，落在同一镜的尾段
        dur = 2.3
        start = round(b0 + shift + 0.95, 3)
        card = DetailCard(title, rows, foot, ring_rows=rrows)
        if force:
            (x, y), sc = (int(force[0]), int(force[1])), -1.0
        else:
            (x, y), sc = pick_pos(mask, card.cw, card.ch)
        mask = occupy(mask, x, y, card.cw, card.ch)
        clip = f"{outdir}/detail_{title}.mov"
        write_clip(card.frames(dur), clip, card.cw, card.ch)
        jobs.append(dict(tag=f"详情·{title}", start=start, end=round(start + dur, 3),
                         x=x, y=y, clip=clip, score=sc, w=card.cw, h=card.ch))
        print(f"  {v} 详情卡「{title}」 {start:.2f}-{start + dur:.2f}s "
              f"落位({x},{y}) 绿占比{max(sc,0.0):.3f}{' (手填)' if sc < 0 else ''} 卡{card.cw}x{card.ch}")

    inputs = ["-i", src]
    for j in jobs:
        inputs += ["-i", j["clip"]]
    fc, cur = [], "0:v"
    for i, j in enumerate(jobs, start=1):
        nxt = f"v{i}"
        # ★两个必须：①setpts 把卡的第一帧对齐到 start（否则主视频跑到 20 多秒时，
        #   2 秒长的卡早已 EOF，eof_action 默认 repeat 会停在最后一帧＝淡出后的全透明，
        #   表现为「一张卡都看不见」）；②eof_action=pass 让卡播完后透传主画面。
        fc.append(f"[{i}:v]setpts=PTS-STARTPTS+{j['start']}/TB,format=rgba[fx{i}]")
        fc.append(f"[{cur}][fx{i}]overlay=x={j['x']}:y={j['y']}:format=auto:shortest=0:"
                  f"eof_action=pass:enable='between(t,{j['start']},{j['end']})'[{nxt}]")
        cur = nxt
    subprocess.run([FF, "-y", "-v", "error"] + inputs + [
        "-filter_complex", ";".join(fc), "-map", f"[{cur}]", "-map", "0:a",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
        f"{S}/render/final_num.mp4"], check=True)
    print(f"  ✓ {v} → {S}/render/final_num.mp4  （{len(jobs)} 个动效卡）")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="产品段动效层：黑底金数字卡 + 详情卡")
    ap.add_argument("versions", nargs="*", default=["v1"], help="片名（工程下的子目录名），如 v1 v2 v3")
    ap.add_argument("--work", required=True, help="工程目录（其下有 <版本>/phrases.txt、<版本>/audio/shot_bounds.json）")
    ap.add_argument("--spec", default=None, help="卡片配置 json，默认 <work>/fx_spec.json")
    a = ap.parse_args()
    sp = a.spec or f"{a.work}/fx_spec.json"
    if not os.path.exists(sp):
        raise SystemExit(f"✗ 找不到卡片配置：{sp}（结构见本文件 docstring）")
    spec_all = load_spec(sp)
    for v in a.versions:
        if v not in spec_all:
            raise SystemExit(f"✗ {sp} 里没有 {v} 段")
        build(v, a.work, spec_all)
