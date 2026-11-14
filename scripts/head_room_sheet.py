#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
头顶条带签署图（2026-11-02 立，老板「人物头被裁到画面外」事故后建）

为什么是「出图给人看」而不是「自动判定」
  试过三种自动判据：绿色 mask 连续段 / 左右边缘背景差分 / 中轴限定连续行。
  同一张贴顶的图，三种算法分别给 0% / 32% / 35%；而头顶完整的镜 15、镜 17
  又被误判成「顶行 96px 连续色块」—— 健身房绿光、走廊墙面色、镜面倒影
  都会污染判据。做一个误报连连的闸门，比没有闸门更坏（人会开始无视它）。

  → 改为：把每镜画面顶部裁出来拼成一张条带图，**必须人眼看一遍**。
    这条已写进 SKILL.md 出片流程，成为固定动作，不靠记忆。

★★ 必须查成片，不是查素材（2026-11-02 第二次事故后补）
  镜 15 素材留白没问题，但成片照样头顶切平：因为每镜还会过 zoompan
  （wide 每边裁 4.5%、mid 3.4%、close 2%）+ 手持微晃 1~2%，
  素材留 6% 到成片就只剩 1%。**素材留白 ≠ 成片留白。**
  → 默认入口改成从 render/final.mp4 按 shot_bounds 抽帧检查。

用法：
  python3 head_room_sheet.py --final render/final.mp4 --bounds audio/shot_bounds.json --out /tmp/hr.png
  python3 head_room_sheet.py --shots <分镜目录> --out /tmp/head_room.png     # 仅素材预检
  python3 head_room_sheet.py --shot-map <shot_map.json> --out /tmp/head_room.png
"""
import argparse
import json
import os
import subprocess

from PIL import Image, ImageDraw

BAND_PCT = 0.30      # 每镜取顶部 30%（18% 太窄，头顶贴边时容易看成天花板纹理）
OUT_W = 900          # 成片 1920 宽按 0.47x 显示，头顶边缘仍然看得清


def resolve(src, cfg_dir):
    if os.path.isabs(src):
        return src
    bases = [cfg_dir, os.path.dirname(cfg_dir), os.getcwd(), os.path.dirname(os.getcwd())]
    for b in bases:
        p = os.path.join(b, src)
        if os.path.exists(p):
            return p
    return os.path.join(cfg_dir, src)


def frames_from_final(final, bounds_path, tmpdir="/tmp/hr_frames"):
    """从成片按 shot_bounds 抽每镜代表帧（取 0.6 处，避开切点转场）。"""
    os.makedirs(tmpdir, exist_ok=True)
    bounds = json.load(open(bounds_path))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", final],
        capture_output=True, text=True)
    dur = float(probe.stdout.strip() or 0)
    out = []
    for k, (s, e) in enumerate(bounds):
        t = s + (e - s) * 0.6
        if dur:
            t = min(t, max(0.0, dur - 0.10))
        p = os.path.join(tmpdir, f"final_{k+1:02d}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", final,
                        "-frames:v", "1", "-y", p], check=True)
        out.append((f"镜{k+1:02d}  {t:.2f}s", p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots")
    ap.add_argument("--shot-map")
    ap.add_argument("--final", help="成片 mp4（推荐 —— 这才是观众真正看到的画面）")
    ap.add_argument("--bounds", help="配合 --final 用的 shot_bounds.json")
    ap.add_argument("--out", default="/tmp/head_room.png")
    args = ap.parse_args()

    if args.final:
        if not args.bounds:
            ap.error("--final 需要配 --bounds")
        pairs = frames_from_final(args.final, args.bounds)
        names = [n for n, _ in pairs]
        paths = [p for _, p in pairs]
    elif args.shot_map:
        cfg_dir = os.path.dirname(os.path.abspath(args.shot_map))
        items = json.load(open(args.shot_map))
        names = [os.path.basename(it["src"]) for it in items]
        paths = [resolve(it["src"], cfg_dir) for it in items]
    elif args.shots:
        names = sorted(f for f in os.listdir(args.shots)
                       if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
        paths = [os.path.join(args.shots, n) for n in names]
    else:
        ap.error("需要 --final / --shots / --shot-map 之一")

    rows = []
    skipped = 0
    for nm, p in zip(names, paths):
        if not os.path.exists(p):
            print(f"缺文件 {nm}")
            continue
        if not p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            skipped += 1          # 视频镜不参与（它自带运镜，头顶由素材本身决定）
            continue
        im = Image.open(p).convert("RGB")
        h = int(im.height * BAND_PCT)
        band = im.crop((0, 0, im.width, h)).resize((OUT_W, int(OUT_W * h / im.width)), Image.LANCZOS)
        rows.append((nm, band))

    if not rows:
        print("没有可用的图")
        return

    bh = rows[0][1].height
    sheet = Image.new("RGB", (OUT_W, (bh + 20) * len(rows)), "#0a0a0a")
    d = ImageDraw.Draw(sheet)
    for i, (nm, band) in enumerate(rows):
        y = i * (bh + 20)
        sheet.paste(band, (0, y + 20))
        d.text((4, y + 4), nm, fill="#ffd479")
        # 红线 = 画面第一条像素；头顶触到红线即被切
        d.line([(0, y + 20), (OUT_W, y + 20)], fill=(255, 60, 60), width=2)
    sheet.save(args.out)
    print(f"已出 {args.out}（{len(rows)} 张图 × 顶部 {int(BAND_PCT*100)}%"
          + (f"，跳过 {skipped} 个视频镜" if skipped else "") + "）")
    print("看什么：任何一格里，人物头顶若与红线（画面第一行）重合或被其截断 → 该镜必须重做。")


if __name__ == "__main__":
    main()
