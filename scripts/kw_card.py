#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「燕麦」大字层（卷播定格卡内叠加用）

从 Q_燕麦大字_动效小样 的定稿移植，只把「写死的 1920 坐标」
换成「跟随卡片内圈 cw×ch 的比例」，这样舞台卡放大/抖动时字不会脱层。

层序（严格）：
  卡底 → 字（远处）→ 人物接触阴影 → 人物 → 圆点（最上面）
⇒ 字被人物压住 = 前后景深；圆点浮在人物之上 = 起手看得见。

比例来自小样实测（卡内圈 1131×624）：
  字心距内沿 248/1131 = 0.2193
  字身高     424/624  = 0.6795
  「麦」字面窄，字号 ×1.06 才与「燕」视觉等重
"""
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SCRIPT = "/Users/yourname/.workbuddy/skills/koubo-ad-video/scripts"
if SCRIPT not in sys.path:
    sys.path.insert(0, SCRIPT)
import minimal_render as MR      # noqa: E402

# ---- 动效时间（相对 T0 = 大字起手，秒）----
T_DOT = 0.00          # 圆点出现
HOLD = 0.10           # 圆点停留
BURST = 0.10          # 爆裂（横向撕开淡出）
GAP = 0.05            # 裂开后再出字，避免点与半截字同帧
GROW = 0.40           # 字长出到位
FLY = 0.20            # 位移到位
FADE = 0.04           # 起手淡入（两字字面宽窄不同，硬出会左右不对称）

FILL = (255, 248, 232)
EDGE = (14, 11, 7)

R_SIDE = 0.2193
R_SIZE = 0.6795
R_MAI = 1.06


def _ease_out_back(u, c1=1.22):
    uu = u - 1.0
    return 1.0 + (c1 + 1.0) * uu ** 3 + c1 * uu ** 2


def big_char(ch, size, fill=FILL, edge=EDGE, sw_k=0.012):
    """米白字面 + 极细深边。深炭底上不需要粗描边，粗了会把宋体笔画糊成黑块。"""
    size = max(12, int(size))
    sw = max(3, int(round(size * sw_k)))
    f = ImageFont.truetype(MR.FONT_KW, size)
    pad = sw * 2 + 40
    tw = int(ImageDraw.Draw(Image.new("RGBA", (10, 10))).textlength(ch, font=f))
    w, h = tw + pad * 2, int(size * 1.4) + pad * 2
    core = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(core).text((w // 2, h // 2), ch, font=f, fill=fill + (255,),
                              anchor="mm", stroke_width=sw, stroke_fill=edge + (255,))
    return core.crop(core.getbbox())


def tint_soft(layer, thick):
    """远处感：微失焦 + 同形深色层向下偏 thick px（立体的边）"""
    core = layer.filter(ImageFilter.GaussianBlur(max(0.4, thick * 0.11)))
    a = core.split()[-1]
    th = Image.new("RGBA", core.size, (0, 0, 0, 0))
    th.paste(Image.new("RGBA", core.size, (26, 20, 14, 235)), (0, 0), a)
    base = Image.new("RGBA", (core.width, core.height + thick), (0, 0, 0, 0))
    base.alpha_composite(th, (0, thick))
    base.alpha_composite(core, (0, 0))
    dim = Image.new("RGBA", base.size, (0, 0, 0, 0))
    dim.paste(Image.new("RGBA", base.size, (16, 12, 8, 6)), (0, 0), base.split()[-1])
    return Image.alpha_composite(base, dim)


def dot_overlay(alpha, rx, ry=None):
    """一个点；rx/ry 分开 ⇒ 爆裂时横向撕成左右两半"""
    if alpha <= 0 or rx < 1:
        return None
    ry = rx if ry is None else ry
    R = int(max(rx, ry)) + 22
    ov = Image.new("RGBA", (R * 2 + 8, R * 2 + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    c = R + 4
    for i, k in enumerate(range(int(max(rx, ry)) + 16, int(max(rx, ry)), -2)):
        sx = rx + (k - max(rx, ry)) * 0.4
        sy = ry + (k - max(rx, ry)) * 0.4
        d.ellipse([c - sx, c - sy, c + sx, c + sy], fill=FILL + (int(alpha * (16 + i * 5)),))
    d.ellipse([c - rx, c - ry, c + rx, c + ry], fill=FILL + (alpha,),
              outline=EDGE + (alpha,), width=max(2, int(min(rx, ry) * 0.22)))
    return ov


class KwLayer:
    """alpha_im：1920×1080 人物遮罩（gen_banner_cards → hero_alpha.png）

    chars：大字内容，**2 字或 4 字**。
      · 2 字（默认/旧片）：左右各一字分立两侧，中间整条留给人物 —— 原版式。
      · 4 字（★2026-11-09 补）：老板原话「形象优先是四个字，但这里跳出来是两个字，
        你改成四个字」。四字横排铺满卡宽、字心均分，**中间两字压在人物身后**（景深不变），
        字号按卡宽自适应（min(ch·R_SIZE, cw·0.94/n)），四字必定全部入画、不出卡框。
      · 2 字路径一字未改（slots／字号／R_MAI 全同旧值），旧片重渲零差异。
    """

    def __init__(self, alpha_im, chars=("燕", "麦"), size_k=1.0):
        self.alpha_src = alpha_im.convert("L")
        chars = tuple(chars)
        if len(chars) not in (2, 4):
            raise ValueError("KwLayer 只支持 2 字或 4 字，收到 %r" % (chars,))
        self.chars = chars
        self.n = len(chars)
        self.size_k = float(size_k)     # 字号倍率：人物太宽时字会顶出卡框，0.8 收进来
        self.ref_h = None
        self._cur = None

    def _prepare(self, cw, ch):
        """按第一次出现时的卡尺寸做一次基准渲染，之后逐帧等比缩放"""
        if self.ref_h is not None:
            return
        self.ref_h = float(ch)
        if self.n == 2:
            # 原版式：左右分立，两字同尺寸
            size = ch * R_SIZE * self.size_k
            self.slots = (R_SIDE, 1.0 - R_SIDE)
        else:
            # 四字：横排铺满卡宽，字心均分；字号取「高度允许」与「宽度允许」的较小值
            size = min(ch * R_SIZE, cw * 0.90 / self.n) * self.size_k
            self.slots = tuple((i + 0.5) / self.n for i in range(self.n))
        self.thick = max(3, int(round(size * 0.0165)))         # 小样 424→7px
        # 「麦」字面窄，×1.06 才与「燕」视觉等重；自定义字（如肌/酸）字形相当，不放大
        r2 = R_MAI if self.chars == ("燕", "麦") else 1.0
        self.layers = []
        for i, c in enumerate(self.chars):
            s = size * (r2 if (self.n == 2 and i == 1) else 1.0)
            self.layers.append(tint_soft(big_char(c, s), self.thick))
        self.cx0 = cw / 2.0
        # 人物接触阴影：剪影外扩模糊、只留外环（实心区由人物本身覆盖）
        pa = self.alpha_src.resize((cw, ch), Image.LANCZOS)
        self.person_a = pa
        rad = max(4, int(round(ch * 0.030)))                   # 小样 624→14px
        grown = pa.filter(ImageFilter.GaussianBlur(rad)).point(lambda v: int(v * 0.46))
        ring = Image.new("L", (cw, ch), 0)
        ring.paste(grown, (int(round(ch * 0.011)), int(round(ch * 0.014))))   # 小样 (7,9)
        self.shadow = ImageChops.subtract(ring, pa)
        self._cur = None

    def _sized(self, cw, ch):
        """抖动时卡尺寸每帧都在变（±1%），阴影/遮罩必须跟着 resize，
        否则 paste 尺寸不匹配、或被压成错位的一圈。"""
        if self._cur == (cw, ch):
            return self.person_a_s, self.shadow_s
        self.person_a_s = self.person_a.resize((cw, ch), Image.BILINEAR)
        self.shadow_s = self.shadow.resize((cw, ch), Image.BILINEAR)
        self._cur = (cw, ch)
        return self.person_a_s, self.shadow_s

    def frame(self, t, cw, ch):
        """t = 距起手秒数。返回 (字层, 阴影层)；t<0 返回 None"""
        if t < T_DOT:
            return None
        self._prepare(cw, ch)
        # ★2026-11-08 修：中心坐标原来只在 _prepare 里按「首帧卡宽」算死，
        #   而段3 是「小卡 → 放大到满卡」：后续帧 cw 变大、字被 k 放大，字心却钉在旧坐标
        #   ⇒ 字越放越往卡框外飘（肌酸 v1 实测「肌」左半被卡框切掉）。
        #   正解：每帧按当前 cw 重算字心，字心永远跟着卡走。
        self.cx0 = cw / 2.0
        k = ch / self.ref_h
        lay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        cy = ch / 2.0

        def draw_char(layer, cx_target):
            el = t - (T_DOT + HOLD + GAP)
            if el < 0:
                return
            u = min(1.0, el / GROW)
            s = max(0.03, _ease_out_back(u ** 1.15))
            p = min(1.0, el / FLY)
            f = 1.0 - 2.0 ** (-10.0 * p) if p < 1.0 else 1.0
            cx = self.cx0 + (cx_target - self.cx0) * f
            if u >= 1.0:
                s = 1.0 + 0.006 * math.sin(2 * math.pi * 1.1 * (el - GROW))
            s *= k
            nw = max(2, int(layer.width * s))
            nh = max(2, int(layer.height * s))
            small = layer.resize((nw, nh), Image.LANCZOS if s > 0.45 else Image.BILINEAR)
            if el < FADE:
                a = small.split()[-1].point(lambda v: int(v * el / FADE))
                small.putalpha(a)
            lay.alpha_composite(small, (int(cx - nw / 2), int(cy - nh / 2)))

        for lyr, slot in zip(self.layers, self.slots):
            draw_char(lyr, cw * slot)
        # 字被人物压住：人物实心区清零（阴影在外环，不受影响）
        pa, shd = self._sized(cw, ch)
        inv = pa.point(lambda v: 255 - v)
        lay.putalpha(ImageChops.multiply(lay.split()[-1], inv))
        return lay, shd

    def dot(self, t, cw, ch):
        """圆点必须画在人物之上，否则被躯干完全挡住、看不到起手"""
        if t < T_DOT:
            return None, None
        self._prepare(cw, ch)
        # ★2026-11-08 修：中心坐标原来只在 _prepare 里按「首帧卡宽」算死，
        #   而段3 是「小卡 → 放大到满卡」：后续帧 cw 变大、字被 k 放大，字心却钉在旧坐标
        #   ⇒ 字越放越往卡框外飘（肌酸 v1 实测「肌」左半被卡框切掉）。
        #   正解：每帧按当前 cw 重算字心，字心永远跟着卡走。
        self.cx0 = cw / 2.0
        k = ch / self.ref_h
        e = t - T_DOT
        r = 16 * k
        if e < 0.04:
            ov = dot_overlay(int(235 * e / 0.04), r)
        elif e < HOLD:
            ov = dot_overlay(235, r)
        elif e < HOLD + BURST:
            kk = (e - HOLD) / BURST
            ov = dot_overlay(int(235 * (1.0 - kk) ** 1.7), r + 58 * k * kk, r - 6 * k * kk)
        else:
            ov = None
        if not ov:
            return None, None
        return ov, (int(self.cx0 - ov.width / 2), int(ch / 2.0 - ov.height / 2))
