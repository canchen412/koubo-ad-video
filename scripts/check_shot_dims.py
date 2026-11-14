#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸门 · 分镜图必须是 16:9（1536×864），不许 3:2 进片。

为什么要有这道闸：
  SKILL.md §🧭 生图第 6 条早就写了「尺寸直接生 16:9（1536×864）」，
  但 2026-11-02 仁和烟酰胺那支片还是照 1536×1024 生了一批，
  结果进成片要 cover 裁掉 160px 高度 —— 那 160px 是从主体身上割的：
  切头顶、切瓶底、切手指，一晚上返工三次（镜11/13/18 各一次）。
  规则写在文档里不等于会被执行，所以配这道带退出码的闸。

判据（任一不满足即 FAIL）：
  ① 宽高比 |w/h - 16/9| > 0.01
  ② 宽度 < 1536（底片按 1536 宽出图再上采到 1920×1080，比这更小会糊）
视频镜（.mp4）不看宽高比，但要求 ≥ 1280 宽。

【用法】
  python check_shot_dims.py --shots 烟酰胺_仁和/assets/shots
  python check_shot_dims.py --shot-map 烟酰胺_仁和/config/shot_map.json
  python check_shot_dims.py --shots <dir> --fix-hint     # 附重生成建议
退出码：0 全部过关 / 1 有不合规 / 2 参数或文件问题
"""
import argparse
import json
import os
import subprocess
import sys

TARGET_AR = 16 / 9
AR_TOL = 0.01
MIN_WIDTH = 1536


def probe(path):
    """返回 (w, h)；视频返回 None 表示只看宽度。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        w, h = out.stdout.strip().split("x")[:2]
        return int(w), int(h)
    except Exception:
        return None


def collect(args):
    paths = []
    if args.shots:
        if not os.path.isdir(args.shots):
            print(f"❌ 目录不存在：{args.shots}")
            sys.exit(2)
        for fn in sorted(os.listdir(args.shots)):
            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".mp4")):
                paths.append(os.path.join(args.shots, fn))
    if args.shot_map:
        if not os.path.isfile(args.shot_map):
            print(f"❌ shot_map 不存在：{args.shot_map}")
            sys.exit(2)
        base = os.path.dirname(os.path.dirname(os.path.abspath(args.shot_map)))
        root = os.path.dirname(base)
        data = json.load(open(args.shot_map, encoding="utf-8"))
        for item in data:
            src = item.get("src") or ""
            if not src:
                continue
            if not os.path.isabs(src):
                src = os.path.join(root, src)
            paths.append(src)
    if not paths:
        print("❌ 没有找到任何素材（--shots 或 --shot-map 至少给一个）")
        sys.exit(2)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", help="分镜素材目录")
    ap.add_argument("--shot-map", help="shot_map.json（只查被引用到的素材）")
    ap.add_argument("--fix-hint", action="store_true", help="附重生成建议")
    args = ap.parse_args()

    paths = collect(args)
    bad = []
    for p in paths:
        if not os.path.isfile(p):
            bad.append((p, "文件缺失", ""))
            continue
        size = probe(p)
        if not size:
            bad.append((p, "读不出尺寸", ""))
            continue
        w, h = size
        name = os.path.basename(p)
        if p.lower().endswith(".mp4"):
            if w < 1280:
                bad.append((p, f"视频宽度 {w} < 1280", name))
            continue
        ar = w / h
        if abs(ar - TARGET_AR) > AR_TOL:
            bad.append((p, f"{w}×{h}（比例 {ar:.3f}，要 1.778）", name))
            continue
        if w < MIN_WIDTH:
            bad.append((p, f"{w}×{h} 偏小（宽度 < {MIN_WIDTH}）", name))

    total = len(paths)
    if not bad:
        print(f"✅ PASS ｜ {total} 个素材全部 16:9 且尺寸达标")
        return 0

    print(f"❌ FAIL ｜ {total} 个素材里 {len(bad)} 个不合规\n")
    for p, why, _ in bad:
        print(f"  {os.path.basename(p)}\n    → {why}")
    if args.fix_hint:
        print("\n【修法】重新生成时 size 写 \"1536x864\"（当前通道直出 16:9），")
        print("        不要 \"1536x1024\" 回头裁 —— 裁掉的 160px 是从头顶/瓶底/手指上割的。")
        print("        构图同时要求「底部 25% 留净空」，否则底部字幕会压住产品标签。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
