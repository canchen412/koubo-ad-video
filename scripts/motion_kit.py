#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
入场动效库 · 极简版专用
========================
老板 2026-11-03：「抠完图后它进入视频的动效太单一了，都是从小到大缩放进来放大进来的」
—— 原来只有 pop 一种（0.40 缩放 + 6% 过冲），16 句全一样，看上三句就腻。

这里给 8 套，统一接口：params(kind, p, dir) -> Motion
    p   0→1 入场进度
    dir +1 从右/上方来，-1 从左/下方来（左右区自动分派，让画面有来回感）

所有数值都在「最终尺寸 = 1.0」的归一化坐标上，调用方只管把结果贴上去。
"""
import math

# 动效时长（秒）。比原来的 PULL=0.36 略长，动作看得清但不拖
DUR = 0.62

KINDS = [
    ("pop",      "弹入",       "从 40% 放大弹到 106%，再收回原位"),
    ("slide_up", "上滑落定",   "从下方 170px 滑上来，落点上方 8px 回弹压住"),
    ("slide_in", "侧滑甩入",   "从侧边 300px 滑进来，同时 7° 斜角摆正"),
    ("wipe",     "揭幕擦出",   "从脚下往上长出来，边缘 10px 柔化"),
    ("squash",   "压扁回弹",   "横向 1.38 / 纵向 0.70 起，弹三下回正"),
    ("focus",    "对焦浮现",   "从 18px 模糊 + 透明里浮出来，1.16 收到 1.0"),
    ("swing",    "甩入挂正",   "从上方甩下来，绕重心 12° 摆正，过冲 10%"),
    ("iris",     "圆形展开",   "以中心为圆心，圆形遮罩扫到满幅"),
]


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def ease_out_cubic(p):
    p = _clamp01(p)
    return 1 - (1 - p) ** 3


def ease_out_sine(p):
    """前段就走得动、后段慢慢收 —— 0.6s 的入场用这个才不会像闪现"""
    p = _clamp01(p)
    return math.sin(math.pi * 0.5 * p)


def ease_out_quad(p):
    p = _clamp01(p)
    return 1 - (1 - p) ** 2


def ease_in_out(p):
    """两头慢中间快：擦出/展开用，避免前 3 帧就冲完"""
    p = _clamp01(p)
    return 0.5 - 0.5 * math.cos(math.pi * p)


def ease_out_quint(p):
    p = _clamp01(p)
    return 1 - (1 - p) ** 5


def ease_out_back(p, k=1.12):
    """过冲：p=0.7 附近冲过 1，再回落"""
    p = _clamp01(p)
    if p >= 1.0:
        return 1.0
    return 1 + (k + 1) * (p - 1) ** 3 + k * (p - 1) ** 2


def damped(p, freq=2.6, decay=5.2):
    """衰减振荡：p=0 时为 1，之后按 cos 摇摆并衰减到 0"""
    return math.exp(-decay * p) * math.cos(2 * math.pi * freq * p)


class Motion:
    """一帧的变换参数（全部相对最终尺寸）"""
    __slots__ = ("sx", "sy", "dx", "dy", "rot", "alpha", "blur", "wipe", "iris")

    def __init__(self, sx=1.0, sy=1.0, dx=0.0, dy=0.0, rot=0.0,
                 alpha=1.0, blur=0.0, wipe=None, iris=None):
        self.sx, self.sy = sx, sy
        self.dx, self.dy = dx, dy
        self.rot = rot
        self.alpha = alpha
        self.blur = blur
        self.wipe = wipe            # None 或 0→1：从底往上的揭示比例
        self.iris = iris            # None 或 0→1：圆形展开比例

    def __repr__(self):
        return ("M(sx=%.2f sy=%.2f dx=%.0f dy=%.0f rot=%.1f a=%.2f "
                "blur=%.1f wipe=%s)" % (self.sx, self.sy, self.dx, self.dy,
                                        self.rot, self.alpha, self.blur, self.wipe))


def params(kind, p, direction=1):
    """kind 见 KINDS；direction 只影响左右/上下来的方向，看起来更像在'摆放'而不是'弹出'"""
    p = _clamp01(p)
    d = 1 if direction >= 0 else -1

    if kind == "pop":
        s = max(0.40, ease_out_back(p, 1.06))
        return Motion(sx=s, sy=s)

    if kind == "slide_up":
        e = ease_out_sine(p)
        # 主位移铺满全程，最后 18% 再叠一个 9px 的落地回弹（压一下再起）
        bounce = -9.0 * math.sin(math.pi * min(1.0, max(0.0, (p - 0.72) / 0.28)))
        dy = 178.0 * (1.0 - e) + bounce
        s = 0.955 + 0.045 * ease_out_sine(p)
        return Motion(sx=s, sy=s, dy=dy, alpha=min(1.0, p / 0.14))

    if kind == "slide_in":
        e = ease_out_sine(p)
        dx = d * 320.0 * (1.0 - e)
        rot = -d * 8.0 * (1.0 - ease_out_sine(min(1.0, p / 0.9)))
        s = 0.94 + 0.06 * ease_out_sine(p)
        return Motion(sx=s, sy=s, dx=dx, rot=rot, alpha=min(1.0, p / 0.12))

    if kind == "wipe":
        r = ease_in_out(min(1.0, p / 0.96))
        return Motion(dy=26.0 * (1.0 - r), wipe=r, alpha=1.0)

    if kind == "squash":
        v = damped(p, freq=2.0, decay=2.3)
        sx = 1.0 + 0.30 * v
        sy = 1.0 - 0.24 * v
        dy = 12.0 * (1.0 - ease_out_cubic(p))   # 压扁时重心下沉一点
        return Motion(sx=max(0.55, sx), sy=max(0.55, sy), dy=dy,
                      alpha=min(1.0, p / 0.12))

    if kind == "focus":
        e = ease_out_quad(min(1.0, p / 0.95))
        s = 1.16 - 0.16 * e
        return Motion(sx=s, sy=s, blur=26.0 * (1.0 - e),
                      alpha=min(1.0, p / 0.5))

    if kind == "swing":
        e = ease_out_sine(p)
        dy = -120.0 * (1.0 - e)
        # 角度晚一点收，落定后再回摆 2°
        settle = ease_out_sine(min(1.0, p / 0.88))
        rot = -d * (12.0 * (1.0 - settle) + 2.0 * math.sin(math.pi * p) * (1 - p))
        s = 0.96 + 0.04 * e
        return Motion(sx=s, sy=s, dy=dy, rot=rot, alpha=min(1.0, p / 0.12))

    if kind == "iris":
        r = ease_in_out(min(1.0, p / 0.92))
        s = 1.10 - 0.10 * r
        return Motion(sx=s, sy=s, alpha=1.0, blur=6.0 * (1.0 - r), iris=r)

    raise ValueError("未知动效：%s（可选 %s）" % (kind, [k for k, _, _ in KINDS]))


def iris_radius(p, w, h):
    """圆形展开的半径（像素）：从中心扫到能盖住整个元素"""
    r = ease_out_quint(min(1.0, p / 0.84))
    return r * math.hypot(w, h) * 0.62


# ================================================================
# 落定后的常驻呼吸 / 摇晃（idle）
# ================================================================
# 老板 2026-11-03：「抠图的小绿人出现以后，画面就定在那里了 —— 可以做成轻微摇晃，
# 感觉视频在动，这样有动态效果会好一点点。」
#
# 入场动效跑完（MOTION_DUR）之后，贴纸不是彻底静止，而是挂着三层不同周期的微动：
#   ① 呼吸：纵向 ±1.3%、横向反向 -0.6%（体积守恒，像真人站着吸气）
#   ② 摇晃：绕重心 ±0.9°，周期 3.0s（腰为轴左右摆，底边锚定 → 脚不滑）
#   ③ 重心：左右 ±3px，与摇晃错相位（否则看着像整体平移，机械）
#
# ⚠️ 三条曲线的周期必须互不成整数倍 —— 一旦成整数倍，几秒后就会「同一帧无限重复」，
#    眼睛立刻看出是循环视频。这里 0.33Hz / 0.24Hz / 相位差 0.6rad 是刻意错开的。

IDLE_ROT = 2.00          # 摇晃摆幅（度），按贴纸高度归一化到 900px 基准
                         # ⚠️ 实测：1.15° 在 940px 的人身上头顶只横移 9px，手机上几乎看不见
                         #    （纵向呼吸 16px 反而更大，看着是「喘」不是「摇」）→ 加大角度、压低呼吸
IDLE_BREATH = 0.008      # 呼吸缩放幅度（辅助层，别压过摇晃）
IDLE_DX = 5.0            # 重心左右微移（px）
IDLE_SWAY_HZ = 0.33
IDLE_BREATH_HZ = 0.24
IDLE_RAMP = 0.40         # 落定后 0.4s 平滑拉满：短句（1.6s）也来得及看出呼吸


def idle(t, seed=0, h=900, ramp=None):
    """贴纸落定后的那部分变换（返回 Motion，直接乘/加到入场结果上）。
    t 是「落定之后过了多少秒」，seed 让每条片、每一镜的相位错开。"""
    ramp = IDLE_RAMP if ramp is None else ramp
    if t <= 0:
        return Motion()
    k = 1.0 if ramp <= 0 else min(1.0, t / ramp)
    k = k * k * (3.0 - 2.0 * k)                      # smoothstep：起手不抖
    ph = (seed * 0.83) % (2.0 * math.pi)
    a = 2.0 * math.pi * IDLE_SWAY_HZ * t + ph        # 摇晃相位
    b = 2.0 * math.pi * IDLE_BREATH_HZ * t + ph * 1.7  # 呼吸相位（错开，不同步）
    # 小贴纸（物品特写）按高度打折，否则一个 400px 的胶囊摇 1° 会像在飞
    rk = max(0.75, min(1.15, h / 900.0))
    rot = IDLE_ROT * rk * k * math.sin(a)
    dx = IDLE_DX * k * math.sin(a + 0.6)
    sy = 1.0 + IDLE_BREATH * k * math.sin(b)
    sx = 1.0 - IDLE_BREATH * 0.45 * k * math.sin(b)
    return Motion(sx=sx, sy=sy, dx=dx, rot=rot)


def idle_apply(prm, t, seed=0, h=900):
    """把 idle 叠到入场 Motion 上（原地改，返回同一个对象）"""
    if t <= 0:
        return prm
    i = idle(t, seed=seed, h=h)
    prm.sx *= i.sx
    prm.sy *= i.sy
    prm.dx += i.dx
    prm.rot += i.rot
    return prm
