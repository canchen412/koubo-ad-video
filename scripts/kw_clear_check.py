#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重点字避让闸门 · 字不许压到小绿人主体、不许压到图片卡
================================================================
为什么需要：`kw_place` 只有「左上 / 右上」两个候选 + 三档高度，
贴纸一宽（举铁 977px、深蹲 1443px）两个角全撞，代码兜底 `return W//2, 6+h//2`
→ 字直接糊在人物头顶/脸上。老板 2026-11-03：「重点字挡住人物的脸了」。

判据用**贴纸真实 alpha 轮廓**算，不用外接矩形 —— 矩形会把大量透明区算成遮挡，
逼得字无处可放；真实轮廓才是人眼看到的"人"。

用法：
    python3 kw_clear_check.py --plan plan.json            # 出片前必跑，违规退出码 1
    python3 kw_clear_check.py --plan plan.json --verbose  # 每镜明细
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import minimal_render as R   # noqa: E402

# 允许的遮挡上限（像素）。字是压在最上层的，只要有重叠就是"挡脸"
TOL_PX = 0          # 严格：一个不透明像素都不许压
HEAD_FRAC = 0.32    # 人物 bbox 上部这么多算「头部优先区」


def sticker_box(el, card_box):
    """复现渲染器里贴纸的落位，返回 (left, top, w, h, alpha_mask, im)"""
    zone = el.get("zone", "C")
    is_teller = el.get("role") == "teller"
    h = int(el.get("h") or (R.TELLER_H if is_teller else R.STICKER_H))
    p = el["src"] if os.path.isabs(el["src"]) else os.path.join(R.CUT, el["src"])
    if "_净边" not in p:
        c = os.path.splitext(p)[0] + "_净边.png"
        if os.path.exists(c):
            p = c
    im = Image.open(p).convert("RGBA")
    asp = im.width / float(im.height)
    cx = int(R.W * R.Z[zone])
    max_w = 2 * min(cx - 40, R.W - 40 - cx)
    h = min(h, int(max_w / asp))
    ww = int(round(im.width * h / float(im.height)))
    s = im.resize((ww, h), Image.BILINEAR)

    if card_box is not None:
        c_left, c_right = card_box[0], card_box[2]
        ov = min(R.OVERLAP, int((c_right - c_left) * 0.16))
        if (c_left + c_right) // 2 >= R.W // 2:
            cx = c_left + ov - s.width // 2
        else:
            cx = c_right - ov + s.width // 2
        cx = max(s.width // 2 + 16, min(R.W - 16 - s.width // 2, cx))
    pad = int(round(R.BOTTOM_PAD * h / 1000.0))
    sx = cx - s.width // 2
    sy = R.BASE_Y - s.height + pad
    return sx, sy, s.width, s.height, s


def card_box_of(el):
    if el.get("kind", "sticker") == "sqcard":
        size = int(el.get("s") or R.SQ_SIZE)
        cy = int(el.get("cy", R.SQ_CY))
        cxx = int(el.get("cx", R.W // 2))
        half = size // 2 + 24
        return (cxx - half, cy - half, cxx + half, cy + half)
    zone = el.get("zone", "C")
    two = False
    ar = el.get("ar", "16x9")
    aw, ah = R._ar(ar)
    bw = int(el.get("w") or (R.CARD_MIN_W if two else R.CARD_MAX_W))
    bp = int(el.get("h") or (R.CARD_MIN_H if two else R.CARD_MAX_H))
    bw = min(bw, int(bp * aw / ah))
    cx = int(R.W * R.Z[zone])
    if zone != "C":
        bw = min(bw, 2 * min(cx - 40, R.W - 40 - cx))
    bh = int(round(bw * ah / aw))
    cy = int(el.get("cy", R.CARD_CY))
    return (cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2)


def overlap_px(kw_mask, box_w, box_h, kx, ky, subj_rgba, sx, sy):
    """字的不透明像素与「贴纸 alpha」的重叠像素数"""
    x0 = max(kx, sx); x1 = min(kx + box_w, sx + subj_rgba.width)
    y0 = max(ky, sy); y1 = min(ky + box_h, sy + subj_rgba.height)
    if x1 <= x0 or y1 <= y0:
        return 0
    km = kw_mask.crop((x0 - kx, y0 - ky, x1 - kx, y1 - ky))
    sa = subj_rgba.getchannel("A").crop((x0 - sx, y0 - sy, x1 - sx, y1 - sy))
    a = np.asarray(sa).astype(np.float32) / 255.0
    k = np.asarray(km).astype(np.float32) / 255.0
    return int((a * k > 0.35).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--min-alpha", type=float, default=0.35)
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    shots = plan["shots"]
    # 动效不影响落位，但 zone/side 需要
    bad = 0
    print("%-5s %-6s %-24s %-10s %s" % ("镜", "类型", "重点字", "位置", "遮挡 / 结论"))
    for i, s in enumerate(shots):
        kws = s.get("kw")
        if not kws or s.get("kind") == "sqcard":
            continue
        kt = kws if isinstance(kws, str) else (kws.get("t") or kws.get("text") or "")
        if not kt:
            continue
        els = s.get("els") or [s]
        # 先卡片后贴纸，跟渲染顺序一致
        ordered = sorted(els, key=lambda e: 1 if e.get("kind", "sticker") == "sticker" else 0)
        cb = None
        masks = []
        subs = []
        for el in ordered:
            if el.get("kind", "sticker") != "sticker":
                cb = card_box_of(el)
                masks.append(("rect", cb))
                subs.append(("card", cb, None, None))
            else:
                sx, sy, sw, sh, s_im = sticker_box(el, cb)
                masks.append(("sticker", sx, sy,
                              np.asarray(s_im.getchannel("A"), np.float32) / 255.0))
                subs.append(("sticker", (sx, sy, sx + sw, sy + sh), s_im, (sx, sy)))
        allk = any(e.get("kind", "sticker") != "sticker" for e in els)
        kind = "card" if allk else s.get("kind", "sticker")
        zone0 = els[0].get("zone", "C")
        ct = cb[1] if cb else None

        mask = R.build_clear_mask(masks)
        pick = None
        for sc in R.KW_SCALES:
            ki = R.make_kw(kt, R.kw_style(kws, i, kt), scale=sc)
            pos = R.kw_place(ki.width, ki.height, mask, kind, zone0, i, ct, strict=True)
            if pos:
                pick = (sc, ki, pos)
                break
        if pick is None:
            ki = R.make_kw(kt, R.kw_style(kws, i, kt))
            pos = R.kw_place(ki.width, ki.height, mask, kind, zone0, i, ct, strict=False)
            pick = (1.0, ki, pos)
        sc_used, simg, (kcx, kcy, side) = pick
        kx, ky = kcx - simg.width // 2, kcy - simg.height // 2

        hits = []
        for tag, box, s_im, pos in subs:
            if tag == "sticker":
                n = overlap_px(simg.getchannel("A"), simg.width, simg.height,
                               kx, ky, s_im, pos[0], pos[1])
                if n > TOL_PX:
                    head = (box[3] - box[1]) * HEAD_FRAC + box[1]
                    where = "脸部/头部" if ky < head and ky + simg.height > box[1] else "身体"
                    hits.append("%s %d px（%s）" % (tag, n, where))
            else:
                x0 = max(kx, box[0]); x1 = min(kx + simg.width, box[2])
                y0 = max(ky, box[1]); y1 = min(ky + simg.height, box[3])
                if x1 > x0 and y1 > y0:
                    hits.append("%s %d px（压图）" % (tag, (x1 - x0) * (y1 - y0)))
        note = "" if sc_used >= 0.999 else " 字号×%.2f" % sc_used
        flag = ("✓" + note) if not hits else "✗ " + "；".join(hits) + note
        if hits:
            bad += 1
        if a.verbose or hits:
            print("%-5s %-6s %-24s %-10s %s" % (s["id"], kind, kt[:22], side, flag))
    print("\n%d 镜有重点字，%d 镜遮挡主体" % (
        sum(1 for s in shots if s.get("kw") and s.get("kind") != "sqcard"), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
