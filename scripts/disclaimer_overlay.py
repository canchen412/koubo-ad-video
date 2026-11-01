#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""免责小字（右上角）—— 贴片生成 + 是否该贴的判断

来源：2026-10-30 灿爹拍板
  「以后每一次只要有维生素相关的、肌酸相关的或者姜黄素相关的，都贴上这行小字，
    或者其他的品类如果我每次说加小字的话，你也把这行小字加上。」

  - 文案（固定，不要改写）：本产品为普通食品，个人感受仅供参考，不代表产品功效。本品不能代替药物。
  - 视觉（2026-10-30 第二次定稿，灿爹：「间距调小一点，字再靠右上角一点，透明度 50%」）：
      字号 30 @1080p（按分辨率等比缩放） / 距右 26 / 距顶 12 / 行距 1.26 倍
      白字 alpha 50%，2px 深描边（约 37%），无底条、无暗角
  - 触发：见 need_disclaimer()。品类关键词命中 → 自动贴；
          brand.json 写 "disclaimer": true → 强制贴（用户口头说「加小字」时就这么写）；
          "disclaimer": false → 强制不贴；写 dict 可覆盖 text / size / alpha 等。

被 build_ad_video.py 调用（出片时 ffmpeg overlay 叠一层，不额外重编码）；
卡片自动落位也用 overlay_box() 避开它，免得详情卡压在小字上。
单独生成贴片：python disclaimer_overlay.py --out /tmp/d.png
"""
import os
import sys

TEXT = "本产品为普通食品，个人感受仅供参考，不代表产品功效。本品不能代替药物。"
# 断成两行：右对齐后两行长度相近，块形方正，不会出现「短尾行」拖出突兀的空缺
LINES = ["本产品为普通食品，个人感受仅供参考，",
         "不代表产品功效。本品不能代替药物。"]

# 需要标注「普通食品」的品类关键词（营养补充/保健向）。
# 只放 2 字以上的词，避免「铁」「锌」这类单字在正常文案里误伤。
CAT_KWS = [
    "维生素", "维他命", "维C", "维E", "维B", "维D", "多维", "金维他",
    "肌酸", "一水肌酸", "姜黄素", "姜黄",
    "虾青素", "烟酰胺", "叶酸", "钙片", "补钙", "液体钙",
    "鱼油", "深海鱼油", "蛋白粉", "乳清蛋白", "乳清", "大豆肽",
    "氨基酸", "BCAA", "左旋肉碱", "辅酶Q10", "辅酶",
    "益生菌", "胶原蛋白", "胶原", "番茄红素", "花青素", "牛磺酸",
    "葡萄籽", "膳食纤维", "氮泵", "补铁", "铁剂", "葡萄糖酸锌",
    "氨糖", "软骨素", "褪黑素", "膳食补充", "营养补充",
]

# 字体候选（macOS 自带；ttc 需要用 index 取具体字重）
FONT_CANDIDATES = [
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 1),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),
    ("/Library/Fonts/Arial Unicode.ttf", 0),
]

DEFAULT_STYLE = dict(
    size=30,        # @1080p 高的字号
    right=26,       # 距右边
    top=12,         # 距顶部
    line_gap=1.26,  # 行距倍数
    alpha=128,      # 白字不透明度 0-255（128 ≈ 50%）
    stroke=2,       # 描边宽度
    stroke_alpha=95,
    shadow=True,
)


def _load_font(size):
    from PIL import ImageFont
    for path, idx in FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            continue
    raise RuntimeError("找不到可用的中文字体（Hiragino/STHeiti/Arial Unicode 均不可用）")


def _split(text):
    """外部自定义文案：尽量在中间逗号处断成两行。"""
    raw = (text or "").strip()
    if not raw or raw == TEXT:
        return LINES
    half = (len(raw) + 1) // 2
    cut = raw.rfind("，", 0, half + 1)
    if cut < 0:
        cut = raw.rfind(",", 0, half + 1)
    cut = cut + 1 if cut > 0 else half
    return [raw[:cut], raw[cut:]] if raw[cut:] else [raw]


def _layout(width, height, text=None, style=None):
    """算出版式（字号/行高/块的像素范围），供 make_overlay 与 overlay_box 共用。"""
    from PIL import Image, ImageDraw

    st = dict(DEFAULT_STYLE)
    if style:
        st.update({k: v for k, v in style.items() if v is not None})

    sx = width / 1920.0
    size = max(10, int(round(st["size"] * sx)))
    right = max(2, int(round(st["right"] * sx)))
    top = max(2, int(round(st["top"] * sx)))
    stroke = max(1, int(round(st["stroke"] * sx)))

    lines = _split(text)
    font = _load_font(size)
    line_h = int(size * float(st["line_gap"]))

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [probe.textlength(s, font=font) for s in lines]
    x_right = width - right
    block_w = int(max(widths))
    block_h = line_h * len(lines)

    return dict(st=st, size=size, font=font, lines=lines, widths=widths,
                line_h=line_h, stroke=stroke, x_right=x_right,
                x0=int(x_right - block_w), y0=top,
                x1=int(x_right), y1=int(top + block_h),
                block_w=block_w, block_h=block_h)


def overlay_box(width=1920, height=1080, text=None, style=None, pad=10):
    """返回小字实际占用的像素框 (x0, y0, x1, y1)，带 pad 余量。
    卡片自动落位用它把这块标成「已占用」，避免详情卡压在小字上。"""
    L = _layout(width, height, text, style)
    return (max(0, L["x0"] - pad), max(0, L["y0"] - pad),
            min(width, L["x1"] + pad), min(height, L["y1"] + pad))


def make_overlay(out_png, width=1920, height=1080, text=None, style=None):
    """生成一张整幅透明 PNG，只在右上角画免责小字。返回 out_png。"""
    from PIL import Image, ImageDraw, ImageFilter

    L = _layout(width, height, text, style)
    st, font, lines = L["st"], L["font"], L["lines"]

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    def _x(i):
        return L["x_right"] - L["widths"][i]

    if st.get("shadow", True):
        sh = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ds = ImageDraw.Draw(sh)
        for i, s in enumerate(lines):
            ds.text((_x(i), L["y0"] + i * L["line_h"]), s, font=font,
                    fill=(0, 0, 0, int(st["alpha"] * 0.55)))
        sh = sh.filter(ImageFilter.GaussianBlur(max(1, int(L["size"] * 0.16))))
        img.alpha_composite(sh)

    d = ImageDraw.Draw(img)
    for i, s in enumerate(lines):
        d.text((_x(i), L["y0"] + i * L["line_h"]), s, font=font,
               fill=(255, 255, 255, int(st["alpha"])),
               stroke_width=L["stroke"],
               stroke_fill=(0, 0, 0, int(st["stroke_alpha"])))

    os.makedirs(os.path.dirname(os.path.abspath(out_png)) or ".", exist_ok=True)
    img.save(out_png)
    return out_png


def _collect_text(cfg, workdir=None):
    """把所有可能含品类名的文本汇成一坨：品牌/产品/整份配置/文案文件。"""
    parts = []
    try:
        import json
        parts.append(json.dumps(cfg, ensure_ascii=False))
    except Exception:
        parts.append(str(cfg))
    for k in ("brand", "product", "category", "copy", "script", "vo_text", "title"):
        v = cfg.get(k) if isinstance(cfg, dict) else None
        if isinstance(v, str):
            parts.append(v)
    dirs = [workdir]
    if isinstance(cfg, dict):
        dirs.append(cfg.get("workspace"))
    for d in dirs:
        if not d:
            continue
        for fn in ("copy.txt", "文案.txt", "口播.txt"):
            p = os.path.join(d, fn)
            if os.path.exists(p):
                try:
                    parts.append(open(p, encoding="utf-8").read())
                except Exception:
                    pass
    return "\n".join(parts)


def need_disclaimer(cfg, workdir=None):
    """返回 (是否要贴, 原因说明)。显式开关优先于关键词。"""
    flag = cfg.get("disclaimer") if isinstance(cfg, dict) else None

    if flag is False:
        return False, "配置里 disclaimer=false，手动关闭"
    if isinstance(flag, dict) and flag.get("enabled") is False:
        return False, "配置里 disclaimer.enabled=false，手动关闭"
    if flag is True:
        return True, "配置里 disclaimer=true，手动开启"
    if isinstance(flag, dict) and flag.get("enabled") is True:
        return True, "配置里 disclaimer.enabled=true，手动开启"

    text = _collect_text(cfg, workdir)
    hits = [k for k in CAT_KWS if k in text]
    if hits:
        uniq = sorted(set(hits), key=len, reverse=True)[:4]
        return True, "命中品类关键词：" + "、".join(uniq)
    return False, "未命中品类关键词"


def main():
    import argparse
    ap = argparse.ArgumentParser(description="生成右上角免责小字透明贴片")
    ap.add_argument("--out", required=True)
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--text", default=None)
    ap.add_argument("--size", type=int, default=None)
    ap.add_argument("--right", type=int, default=None)
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--line-gap", type=float, default=None)
    ap.add_argument("--alpha", type=int, default=None)
    ap.add_argument("--stroke", type=int, default=None)
    ap.add_argument("--stroke-alpha", type=int, default=None)
    a = ap.parse_args()
    style = dict(size=a.size, right=a.right, top=a.top, line_gap=a.line_gap,
                 alpha=a.alpha, stroke=a.stroke, stroke_alpha=a.stroke_alpha)
    p = make_overlay(a.out, a.w, a.h, text=a.text, style=style)
    b = overlay_box(a.w, a.h, text=a.text, style=style)
    print("OK ->", p, "占用框", b)


if __name__ == "__main__":
    main()
