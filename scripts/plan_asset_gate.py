#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出片前素材闸门：查「别家产品混进画面」与「产品卡被镜像」。

2026-11-11 老板反馈的两条事故，都是肉眼没看出来的：
  ① 科普段方图抽中了场景图库里 `产品_*` 的别家品牌图（诺特兰德 B 族瓶 / 蓝盒 / 烟酰胺罐）；
  ② 产品卡为了拉开 dHash 被水平镜像，瓶身中文和营养成份表整张反字。

退出码：
  0  通过
  1  发现被禁素材（src 命中 --ban 关键词）
  2  发现被镜像的产品卡（_flip_flags.json 里有 true）
  3  参数/文件问题
  4  贴纸抠图质量不合格（绿占比过低 / 白底残留过多）
  5  plan 里的 ar 与卡片实际比例不符（渲染器会二次裁切，把产品切掉）

用法：
  python3 plan_asset_gate.py --plan v06/plan.json --plan v07/plan.json \
      --ban 产品_ 物品_ 诺特 烟酰胺 虾青素 红罐 蓝盒 \
      --flipflags cards/_flip_flags.json --stickers
"""
import argparse
import json
import os
import sys

try:
    from PIL import Image
except ImportError:
    Image = None


def sticker_quality(path):
    """返回 (绿占比, 白底残留占比)，都基于 _净边 版（那才是真正会用到的图）。"""
    q = path
    if "_净边" not in q:
        c = os.path.splitext(q)[0] + "_净边.png"
        if os.path.exists(c):
            q = c
    im = Image.open(q).convert("RGBA").resize((120, 120), Image.LANCZOS)
    px = im.load()
    tot = green = pale = 0
    for y in range(120):
        for x in range(120):
            r, g, b, a = px[x, y]
            if a > 128:
                tot += 1
                if g > r + 12 and g > b + 12:
                    green += 1
                mx, mn = max(r, g, b), min(r, g, b)
                if mx > 205 and (mx - mn) < 30:
                    pale += 1
    if not tot:
        return 1.0, 0.0
    return green / float(tot), pale / float(tot)


def ar_mismatch(src, ar, tol=0.02):
    """plan 写的 ar 和卡片实际比例对不对得上。

    渲染器对 kind=card 会调 `fit_crop(src, bw, bh, ar)` —— **它真的会裁**。
    plan 里的 ar 一旦和卡片实际比例不一致，卡上刚做好的「整图完整」就被
    渲染器再裁一次，产品照样被切，而且不会有任何报错。这里先把它挡住。
    """
    try:
        a, b = [float(x) for x in ar.split("x")]
    except Exception:
        return None
    want = a / b
    try:
        im = Image.open(src)
    except Exception:
        return None
    got = im.width / float(im.height)
    if abs(got - want) / want <= tol:
        return None
    return (got, want)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="append", required=True)
    ap.add_argument("--ban", nargs="*", default=["产品_", "物品_"])
    ap.add_argument("--flipflags", default=None)
    ap.add_argument("--stickers", action="store_true",
                    help="检查贴纸抠图质量（绿占比 <0.32 或白底残留 >0.08 判不合格）")
    ap.add_argument("--no-archeck", action="store_true",
                    help="跳过 ar 与卡片比例校验（只在你确实想让它二次裁切时用）")
    a = ap.parse_args()

    bad, flipped, dirty, armis = [], [], [], []
    for pf in a.plan:
        if not os.path.exists(pf):
            print("✗ 找不到 plan：%s" % pf)
            return 3
        plan = json.load(open(pf, encoding="utf-8"))
        for sh in plan.get("shots", []):
            for el in (sh.get("els") or [sh]):
                src = el.get("src") or ""
                base = os.path.basename(src)
                hit = [t for t in a.ban if t and (t in base or t in src)]
                if hit:
                    bad.append((pf, sh.get("id", "?"), base, hit))
                if (a.stickers and src.endswith(".png")
                        and "_抠图库" in src and os.path.exists(src)):
                    gr, pr = sticker_quality(src)
                    if gr < 0.32 or pr > 0.08:
                        dirty.append((os.path.basename(pf), sh.get("id", "?"),
                                      base, gr, pr))
                if (not a.no_archeck and el.get("ar") and src.endswith((".jpg", ".png"))
                        and os.path.exists(src)):
                    r = ar_mismatch(src, el["ar"])
                    if r:
                        armis.append((os.path.basename(pf), sh.get("id", "?"),
                                      base, el["ar"], r[0]))

    if a.flipflags and os.path.exists(a.flipflags):
        flags = json.load(open(a.flipflags, encoding="utf-8"))
        flipped = [k for k, v in flags.items() if v]

    if bad:
        print("❌ 画面里混进了非本产品素材（别家品牌图等于白做）：")
        for pf, sid, base, hit in bad:
            print("   %s %s → %s（命中 %s）" % (os.path.basename(pf), sid, base, "/".join(hit)))
    if flipped:
        print("❌ 这些产品卡被水平镜像了，文字会反：%s" % ", ".join(flipped))
    if dirty:
        print("❌ 这些贴纸抠图不合格（人物不成形 / 带背景残片），放大成独镜就是一团脏：")
        for pf, sid, base, gr, pr in dirty:
            print("   %s %s → %s（绿 %.1f%%，白底残留 %.1f%%）"
                  % (pf, sid, base, gr * 100, pr * 100))
    if armis:
        print("❌ plan 的 ar 与卡片实际比例不符 —— 渲染器会二次裁切，产品会被切掉：")
        for pf, sid, base, ar, got in armis:
            print("   %s %s → %s（plan 写 %s，实际 %.2f:1）"
                  % (pf, sid, base, ar, got))
        print("   改法：plan 的 ar 抄 cards/_cards_manifest.json 里的值，不要手填")
    if bad:
        return 1
    if flipped:
        return 2
    if dirty:
        return 4
    if armis:
        return 5

    print("✅ 素材闸门通过：无别家产品、无镜像产品卡%s%s"
          % ("、贴纸抠图干净" if a.stickers else "",
             "、ar 与卡片比例一致" if not a.no_archeck else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
