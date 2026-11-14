#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸门 · 卷播主图（hero）不许用产品图。

老板 2026-11-02 原话：「卷播的主图打开后，今天我们讲烟酰胺……这个主图不要用
小绿人抱着产品的图片，要用小绿人其他的图片就行。」

背景：卷播定格那一刻配音正说「今天我们讲，X」，主图举着产品＝语义打架。
本闸门在渲 banner 之前跑，拦住「hero 挑到产品图」这一类错误。

【工程侧要求】工作区根目录放 hero_src.json：
  {"A": "<hero 源素材绝对路径>", "B": "…"}
（make_hero2.py 生成 hero 时同时写这个文件，别手写死）

【判据】basename 命中产品词即 FAIL：
  产品_ / 瓶 / 罐 / 盒 / 装 / 囤货_ / 抱一摞 / 双手捧 / 举瓶 / 指瓶 / 单指指向
纯小绿人姿态、场景、科普、情绪、张力类均放行。

【用法】
  python check_hero_no_product.py --manifest /path/to/hero_src.json
  python check_hero_no_product.py --src a.png --src b.png
退出码：0 全部过关 / 1 有命中 / 2 参数或文件问题
"""
import argparse, json, os, sys

BAD_TOKENS = ["产品_", "瓶", "罐", "盒", "装", "囤货_", "抱一摞", "捧", "举瓶", "指瓶", "单指指向"]


def judge(path):
    base = os.path.basename(path)
    hit = [t for t in BAD_TOKENS if t in base]
    return base, hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", help="hero_src.json 路径（键=条目标记，值=源素材路径）")
    ap.add_argument("--src", action="append", default=[], help="直接给源素材路径，可重复")
    a = ap.parse_args()

    items = []
    if a.manifest:
        if not os.path.exists(a.manifest):
            print(f"❌ 找不到 manifest：{a.manifest}")
            return 2
        items += [(k, v) for k, v in json.load(open(a.manifest, encoding="utf-8")).items()]
    items += [(f"src{i+1}", p) for i, p in enumerate(a.src)]

    if not items:
        print("❌ 没给任何 hero 源素材（--manifest 或 --src）")
        return 2

    print("=== check_hero_no_product · 卷播主图禁产品图 ===")
    bad = []
    for tag, path in items:
        base, hit = judge(path)
        if not os.path.exists(path):
            print(f"  ⚠️  {tag}: 文件不存在 {path}")
            bad.append((tag, base, ["文件不存在"]))
            continue
        if hit:
            print(f"  ❌ {tag}: {base}  ← 命中 {hit}")
            bad.append((tag, base, hit))
        else:
            print(f"  ✅ {tag}: {base}")

    print()
    if bad:
        print(f"=== 结论: ❌ FAIL — {len(bad)} 条主图是产品图，必须换小绿人本体系画面 ===")
        for tag, base, hit in bad:
            print(f"   · {tag} → {base}（{','.join(hit)}）")
        print("   换图注意：bg / fg 必须同变换（只缩 fg 会留 _bg_soft 的虚影鬼影）；")
        print("   3:2 转 16:9 补边从人物右侧无人区取样，别用整图镜像（会把人物边缘复制到两侧）。")
        return 1
    print("=== 结论: ✅ PASS — 主图全是小绿人本体系，无产品 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
