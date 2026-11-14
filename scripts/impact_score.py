#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""impact_score.py — 冲击力构图的「辅助尺子」（不是闸门，退出码恒 0）

背景
----
2026-11-09 老板拿 5 张抖音对标 AI 图，说「效果没人家好，但我说不出来」。
拆完发现差距不在脑洞，在构图：机位太远、没有前景、只有一层、光平。
规则写进 `生图提示词模板.md` §一之四 之后，需要一把尺子看看出的图到底离对标图多远。

它量什么
--------
1. 冷色占比  HSV 色相 170–280°，饱和度 >0.22 的像素占比（青/蓝，对标图的背景光）
2. 暖色占比  HSV 色相 10–64°（橙/琥珀，对标图的前景光）
3. 暗角     四角 14% 区域平均亮度 ÷ 中心 30% 区域平均亮度（越小越暗角重）
4. 底中比   底部 28% 的粗粒度色彩能量 ÷ 中部 30–58% 的能量（越大说明底部越"满"）
5. 对比度   Y 通道 p95−p5，归一到 0–1

为什么退出码恒 0
----------------
标定集：正样本 = 5 张对标图，负样本 = 16 张历史张力图。
单项指标无法干净分开（暗角/冷暖/对比各自都有 3 张误判），
三项联立后在本标定集上做到 5/5 命中、0 误报 —— 但 n=21 太小，
不足以撑起一个会阻断流程的闸门。按 2026-11-02 `head_room_sheet` 的结论：
误报连连的闸门比没有闸门更坏。所以这里只出诊断，判定交给人眼。

用法
----
    python3 impact_score.py <图或目录> [...]
    python3 impact_score.py <目录> --json
"""
import sys
import os
import json
import glob
import argparse
import numpy as np
from PIL import Image

# 标定得到的判定线（正样本 5/5 通过，负样本 16/16 拒绝）
TH_VIG = 0.45      # 暗角：四角/中心亮度比 ≥ 此值 = 够暗
TH_CON = 0.75      # 对比度
TH_FILL = 0.85     # 底中比：底部得"满"
TH_TEMP = 3.0      # 冷暖两侧各至少占这么多（百分比）才算双色温

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def load(path, width=480):
    im = Image.open(path).convert("RGB")
    w = min(width, im.size[0])
    return im.resize((w, max(1, int(im.size[1] * w / im.size[0]))), Image.LANCZOS)


def metrics(im):
    W, H = im.size
    rgb = np.asarray(im).astype(float) / 255.0
    hsv = np.asarray(im.convert("HSV")).astype(float)
    hue = hsv[:, :, 0] * 360.0 / 255.0
    sat = hsv[:, :, 1] / 255.0
    colored = sat > 0.22
    cool = (colored & (hue >= 170) & (hue <= 280)).mean()
    warm = (colored & (hue >= 10) & (hue <= 64)).mean()

    y = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]) * 255
    cy, cx = H // 2, W // 2
    ch, cw = int(H * 0.30) // 2, int(W * 0.30) // 2
    center = y[cy - ch:cy + ch, cx - cw:cx + cw].mean()
    bh, bw = int(H * 0.14), int(W * 0.14)
    corners = [y[:bh, :bw], y[:bh, -bw:], y[-bh:, :bw], y[-bh:, -bw:]]
    vig = float(np.mean([c.mean() for c in corners])) / max(center, 1e-6)

    def coarse_std(reg):
        small = np.asarray(
            Image.fromarray(np.uint8(np.clip(reg, 0, 255))).resize((24, 8), Image.BOX)
        )
        return float(small.reshape(-1, 3).std(axis=0).mean())

    bot = coarse_std(rgb[int(H * 0.72):, :] * 255)
    mid = coarse_std(rgb[int(H * 0.30):int(H * 0.58), :] * 255)
    fill = bot / max(mid, 1e-6)

    p5, p95 = np.percentile(y, 5), np.percentile(y, 95)
    return {
        "cool": round(cool * 100, 1),
        "warm": round(warm * 100, 1),
        "vig": round(vig, 2),
        "fill": round(fill, 2),
        "con": round((p95 - p5) / 255.0, 2),
    }


def judge(m):
    """三条主判据联立，返回 (是否接近对标, 具体欠哪条)。"""
    miss = []
    if m["vig"] < TH_VIG:
        miss.append("暗角不够")
    if m["con"] < TH_CON:
        miss.append("对比不足")
    if m["fill"] < TH_FILL:
        miss.append("底部太空")
    ok = not miss
    if min(m["cool"], m["warm"]) < TH_TEMP:
        miss.append("单色温(冷暖没对撞)")
    return ok, miss


def expand(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for f in sorted(glob.glob(os.path.join(p, "*"))):
                if f.lower().endswith(EXTS):
                    out.append(f)
        elif p.lower().endswith(EXTS):
            out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    files = expand(args.paths)
    if not files:
        print("没有找到图片。")
        return 0

    rows = []
    for f in files:
        try:
            m = metrics(load(f))
        except Exception as e:  # 坏图不阻断
            rows.append({"file": f, "error": str(e)})
            continue
        ok, miss = judge(m)
        rows.append({"file": f, "ok": ok, "miss": miss, **m})

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"{'文件':34s} {'冷%':>5s} {'暖%':>5s} {'暗角':>5s} {'底/中':>6s} {'对比':>5s}  判定")
    print("-" * 92)
    for r in rows:
        nm = os.path.basename(r["file"])
        if "error" in r:
            print(f"{nm[:32]:34s} 读取失败: {r['error'][:40]}")
            continue
        mark = "接近对标" if r["ok"] else "偏平 ← " + "/".join(r["miss"])
        print(f"{nm[:32]:34s} {r['cool']:5.1f} {r['warm']:5.1f} {r['vig']:5.2f} "
              f"{r['fill']:6.2f} {r['con']:5.2f}  {mark}")

    good = sum(1 for r in rows if r.get("ok"))
    print("-" * 92)
    print(f"共 {len(rows)} 张，接近对标 {good} 张。")
    print(f"判定线：暗角≥{TH_VIG} 对比≥{TH_CON} 底/中≥{TH_FILL}（标定集 n=21，仅供参考，不是闸门）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
