#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「镜内快推」可用性闸门：主体够小才推，大了推就是溢出屏幕。

老板 2026-11-02 定的规则（原话）：
  「当物品或者人物比较小的时候可以这样做，因为如果太大的话，它放大了之后它就溢出屏幕了。
    如果物体很小、瓶子很小，那么是近图的话，他这样做就把瓶子放大，就看起来更有动感一点。
    如果是只有小绿人的话，然后他做出比较惊恐惊讶的表情，突然一下放大到他的头部也行。
    只有这两种情况可以做这个快速运镜，其他的都还是做原来的效果。」

⇒ 只有两档被允许：
  push_product  人和产品同框、产品在画面里**小** → 猛推到产品
  push_face     只有小绿人且**惊讶/惊恐表情** → 猛推到头部（该档必须人工标记 expr="惊讶"，脚本不认表情）

判据（三条同时成立才放行）：
  1. 主体宽度占画面 <= W_MAX(0.26)。超了就是「太大」，推近必溢出。
  2. 推近后主体占画面 <= FILL_MAX(0.62)。既不顶满也不只剩瓶。
  3. 目标点居中不越界：z >= 1/(2*min(tx,1-tx,ty,1-ty))，否则 zoompan 会把框夹到边上（推歪）。
清晰度上限：源图宽 1536 → 2.20；1920~2047 → 2.60；>=2048 → 2.80。

用法：
  python3 push_subject_check.py --img a.png [--img b.png ...] [--json out.json]
  python3 push_subject_check.py --shot-map shot_map.json --workdir .
退出码：0 = 至少一镜可推且全部给出的配置合法；2 = 有配置被判不合格（会被拦）。
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

W_MAX = 0.26        # 主体宽占画面上限：再大就"太大"，推近必溢出（老板规则的核心否决项）
W_MIN = 0.10        # 主体宽占画面下限：比这更小，推到清晰度上限也只占 ~22%，推了没感觉
FILL_IDEAL = 0.45   # 推近后主体占画面的理想值（用来反推倍数）
FILL_MAX = 0.62     # 推近后主体占画面上限（不顶满）
H_MAX = 0.96        # 推近后主体占画面**高度**上限：留 4% 边距。实测 >1.0 就顶满并裁掉瓶盖
                    # （1.48× 实测裁掉半个瓶盖；1.34× 实测瓶盖贴到 y=0 看不见）
CLOSE_RE = ("近景", "特写", "大头", "脸部", "半身")   # 近景镜默认不推：源图有效细节不够
FILL_MIN = 0.30     # 推近后主体占画面下限（推了要看得出放大）
Z_MIN = 1.25        # 推近倍数下限，低于这个等于没推（1.25 = 主体放大约四分之一，2 秒镜里已能看出）


def _hard_max(w):
    """源图宽度决定的清晰度上限（超过就明显上采样发糊）。"""
    if w >= 2048:
        return 2.80
    if w >= 1920:
        return 2.60
    return 2.20


def _blocks(mask, axis, ratio=0.06, min_extent=30):
    """按行/列投影找连续段，返回 [(lo, hi), ...]。"""
    prof = mask.sum(axis=axis)
    th = max(prof.max() * ratio, 2) if prof.size else 0
    idx = np.where(prof > th)[0]
    if not len(idx):
        return []
    segs, s, p = [], idx[0], idx[0]
    for x in idx[1:]:
        if x - p > 12:
            segs.append((s, p))
            s = x
        p = x
    segs.append((s, p))
    return [(a, b) for a, b in segs if b - a >= min_extent]


def _find_bottle(rgb):
    """白瓶：高亮 + 中性（无彩度）。返回最大连通块的 bbox 或 None。"""
    a = rgb.astype(np.int16)
    mx, mn = a.max(2), a.min(2)
    m = (mn > 140) & ((mx - mn) < 40)
    # 去掉大面积过曝背景：逐列直方图取最宽的一段
    cols = _blocks(m, 0, ratio=0.10, min_extent=40)
    if not cols:
        return None
    # 面积最大的列段
    best = max(cols, key=lambda s: m[:, s[0]:s[1]].sum())
    sub = m[:, best[0]:best[1]]
    rows = _blocks(sub, 1, ratio=0.12, min_extent=60)
    if not rows:
        return None
    ry = max(rows, key=lambda s: sub[s[0]:s[1]].sum())
    return (int(best[0]), int(ry[0]), int(best[1]), int(ry[1]))


def _find_green(rgb):
    """小绿人：绿色掩膜。返回 bbox 或 None。"""
    a = rgb.astype(np.int16)
    g = (a[:, :, 1] > a[:, :, 0] + 16) & (a[:, :, 1] > a[:, :, 2] + 16) & (a[:, :, 1] > 66)
    if g.sum() < 800:
        return None
    ys, xs = np.where(g)
    # 用 2%/98% 分位砍掉零星噪点
    x0, x1 = np.percentile(xs, 2), np.percentile(xs, 98)
    y0, y1 = np.percentile(ys, 2), np.percentile(ys, 98)
    return (int(x0), int(y0), int(x1), int(y1))


def _head_box(green_bbox, H):
    """头部：绿人掩膜最上方一段（约占绿人身高 20%）。"""
    if not green_bbox:
        return None
    x0, y0, x1, y1 = green_bbox
    hh = max(int((y1 - y0) * 0.20), 24)
    return (x0, y0, x1, min(y0 + hh, y1))


def evaluate(img_path, target="product", z_plan=None):
    """评估一张图能否做快推。target: product | face；z_plan: 实际打算用的倍数（None=用清晰度上限）"""
    im = Image.open(img_path).convert("RGB")
    W, H = im.size
    rgb = np.asarray(im)
    bottle = _find_bottle(rgb)
    green = _find_green(rgb)
    head = _head_box(green, H)

    box = bottle if target == "product" else head
    if box is None:
        return {"img": os.path.basename(img_path), "size": [W, H], "target": target,
                "ok": False, "reason": f"没测到{'产品瓶' if target == 'product' else '头部'}",
                "bottle": bottle, "green": green, "head": head}

    bx0, by0, bx1, by1 = box
    w_norm = (bx1 - bx0) / W
    h_norm = (by1 - by0) / H
    tx = (bx0 + bx1) / 2 / W
    ty = (by0 + by1) / 2 / H

    z_hard = _hard_max(W)
    z_edge = 1.0 / (2 * min(tx, 1 - tx, ty, 1 - ty))     # 目标点居中不越界的最小倍数
    z_low = max(Z_MIN, z_edge)
    # 想让主体推到「看着够大」的理想倍数；源图上限夹一下，但不能夹到低于下限
    z_ideal = FILL_IDEAL / w_norm if w_norm > 0 else z_hard
    # 高度是**硬约束**：瓶盖和净含量不能被裁穿 ⇒ 上限 H_MAX/h_norm（产品图多为竖长瓶，这条常是真正的瓶颈）
    z_h = H_MAX / h_norm if h_norm > 0 else z_hard
    z_rec = max(z_low, min(z_ideal, z_hard, z_h))
    z_use = float(z_plan) if z_plan else z_rec       # 实际评估用的倍数
    z_use = max(z_use, z_low)

    probs = []
    if w_norm > W_MAX:
        probs.append(f"主体太大（占画宽 {100*w_norm:.1f}% > {100*W_MAX:.0f}%），推近会溢出屏幕")
    if w_norm < W_MIN:
        probs.append(f"主体太小（占画宽 {100*w_norm:.1f}% < {100*W_MIN:.0f}%），推到上限也只占 "
                     f"{100*w_norm*z_use:.0f}%，推了没感觉")
    if target == "product" and any(k in os.path.basename(img_path) for k in CLOSE_RE):
        probs.append("近景镜（源图有效细节不够，再推会糊）—— 该用原来的缓推/拉远")
    if z_low > z_hard + 1e-6:
        probs.append(f"目标点太靠边，需 {z_low:.2f}× 才能居中，源图只支持 {z_hard:.2f}×")
    fill = w_norm * z_use
    if fill > FILL_MAX:
        probs.append(f"推到 {z_use:.2f}× 时主体占画宽 {100*fill:.0f}% > {100*FILL_MAX:.0f}%，顶满")
    fill_h = h_norm * z_use
    if fill_h > H_MAX:
        probs.append(f"推到 {z_use:.2f}× 时主体占画面高度 {100*fill_h:.0f}% > {100*H_MAX:.0f}%，"
                     f"上下会被裁穿（溢出）")

    return {"img": os.path.basename(img_path), "size": [W, H], "target": target,
            "bottle": bottle, "green": green, "head": head,
            "subject_w_pct": round(100 * w_norm, 1),
            "subject_h_pct": round(100 * h_norm, 1),
            "to": [round(tx, 4), round(ty, 4)],
            "z_hard": round(z_hard, 2), "z_edge": round(z_edge, 2),
            "z_rec": round(z_rec, 2), "z_use": round(z_use, 2),
            "fill_pct": round(100 * fill, 1), "fill_h_pct": round(100 * fill_h, 1),
            "ok": not probs, "reason": "；".join(probs) if probs else "可推"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", action="append", default=[])
    ap.add_argument("--shot-map")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--target", default="product", choices=["product", "face"])
    ap.add_argument("--z", type=float, default=None,
                    help="实际打算用的推近倍数（如 1.75）。不给就用清晰度上限评估最坏情况")
    ap.add_argument("--json")
    a = ap.parse_args()

    imgs = list(a.img)
    if a.shot_map:
        sm = json.load(open(a.shot_map, encoding="utf-8"))
        for it in sm:
            s = it.get("src", "")
            if s.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                p = s if os.path.isabs(s) else os.path.join(a.workdir, s)
                if os.path.exists(p) and p not in imgs:
                    imgs.append(p)
    if not imgs:
        print("没有输入图")
        return 1

    res = [evaluate(p, a.target, a.z) for p in imgs]
    print(f"{'图':52s} {'主体宽%':>7s} {'倍数':>6s} {'推后宽%':>7s} {'推后高%':>7s}  结论")
    for r in res:
        if "subject_w_pct" not in r:
            print(f"{r['img'][:50]:52s} {'-':>7s} {'-':>6s} {'-':>7s} {'-':>7s}  ❌ {r['reason']}")
            continue
        print(f"{r['img'][:50]:52s} {r['subject_w_pct']:6.1f}% {r['z_use']:6.2f} "
              f"{r['fill_pct']:6.1f}% {r['fill_h_pct']:6.1f}%  "
              f"{'✅ 可推' if r['ok'] else '❌ ' + r['reason']}")
    if a.json:
        json.dump(res, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n已写 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
