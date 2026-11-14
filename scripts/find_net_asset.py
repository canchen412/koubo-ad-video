#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络素材库 检索 / 命名校验 / 裁方图
库位置：分镜图库/小绿人/_抠图库/网络素材/
配套规则：该目录下 _README_命名规则与用图对照.md

用法
  python3 find_net_asset.py list                        # 列出全部，带画面说明
  python3 find_net_asset.py search 果干                  # 关键词检索（任意段命中）
  python3 find_net_asset.py search 反面 糖                 # 多关键词 AND
  python3 find_net_asset.py check                        # 校验命名是否合规（退出码 1=有违规）
  python3 find_net_asset.py square 果干 --out /tmp/sq --size 900
  python3 find_net_asset.py square 反面_granola_加果干坚果铺木板_俯拍_pexels-5505468.jpg \
                              --out /tmp/sq --size 900 --bias 0.15

退出码
  0 正常 / 校验通过
  1 check 发现命名违规，或未找到指定素材
"""
import argparse
import os
import re
import sys

NET_DIR = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库/网络素材"

SEMANTIC = ("反面", "中性", "正面")
# ②主体档：只收燕麦本体。麦圈/巧克力圈/玉米片/米粒不属于燕麦，一律不许入库
SUBJECT = ("燕麦片", "燕麦粥", "granola", "麦片碗")
SHOT = ("满画面", "特写", "近景", "中景", "俯拍", "全景")
SRC_RE = re.compile(r"^(pexels|unsplash|pixabay)-\d+$")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")

# 文件名 → 画面说明（加了新素材记得补一行，方便 list 时看清内容）
# 准入铁律（老板 2026-11-08）：主体必须是燕麦本体。
#   麦圈 / 巧克力圈 / 玉米片 / 米粒 一律不收 —— 画面里只有糖片，跟「燕麦掺了东西」是两回事。
DESC = {
    # ── 散燕麦片 + 加东西 ──────────────────────────────
    "反面_燕麦片_加葡萄干蔓越莓_近景_pexels-13557588": "★最正的一张：白碗燕麦片里混红黑果干。掺了水果的燕麦",
    "反面_燕麦片_糖浆烤加坚果果干铺满_满画面_pexels-33742591": "★燕麦片被糖浆烤成金黄，混坚果碎+果干，铺满整格无碗无盘。糖浆最直观",
    "反面_燕麦片_加蓝莓香蕉片_俯拍_pexels-7655884": "白盘燕麦片+蓝莓+香蕉片+木勺，干净俯拍。加了水果",
    "反面_燕麦片_巧克力味加覆盆子泡牛奶_俯拍_pexels-30563706": "深色燕麦片泡牛奶+覆盆子莓果，俯拍近满格。加了巧克力+水果",
    "反面_燕麦片_加巧克力块坚果_俯拍_pexels-14665853": "玻璃罐倒出，燕麦片+大块巧克力+榛子杏仁南瓜籽。加了巧克力",
    # ── 燕麦粥 + 淋糖 ──────────────────────────────────
    "反面_燕麦粥_淋蜂蜜加蓝莓香蕉_近景_pexels-7167846": "★蜂蜜正从勺上淋进燕麦粥碗+蓝莓香蕉。『加糖』拍得最明白的一张",
    # ── granola（糖浆烤成团的燕麦） ────────────────────
    "反面_granola_加果干坚果铺木板_俯拍_pexels-5505468": "蓝木板一摊 granola+木勺+小碗，糖浆粘成块，果干坚果满眼",
    "反面_granola碗_倒牛奶_近景_pexels-3872437": "碗里 granola 正倒牛奶，表面发亮。糖浆裹的",
    "反面_granola碗_配饼干牛奶_中景_pexels-6823306": "黑碗 granola+饼干+牛奶，当零食吃的那种",
    "反面_麦片碗_加切块水果_近景_pexels-19318453": "白碗 granola+猕猴桃/芒果/石榴切块，又加水果又加糖",
}


def iter_files():
    if not os.path.isdir(NET_DIR):
        sys.exit(f"! 素材库不存在：{NET_DIR}")
    for fn in sorted(os.listdir(NET_DIR)):
        if fn.startswith("._") or fn.startswith("_"):
            continue
        if os.path.splitext(fn)[1].lower() in IMG_EXT:
            yield fn


def stem(fn):
    return os.path.splitext(fn)[0]


def cmd_list(_a):
    files = list(iter_files())
    print(f"网络素材库 共 {len(files)} 张  {NET_DIR}\n")
    for i, fn in enumerate(files, 1):
        print(f"{i:>2}. {stem(fn)}")
        d = DESC.get(stem(fn))
        print(f"    {d if d else '⚠ 未登记画面说明，请补进脚本 DESC 与 README 索引表'}")
    return 0


def cmd_search(a):
    kws = a.keywords
    hits = [fn for fn in iter_files() if all(k in stem(fn) for k in kws)]
    if not hits:
        print(f"✗ 没有匹配 {' + '.join(kws)} 的素材")
        print(f"  提示：库里现有主体＝{'/'.join(SUBJECT)}（只收燕麦本体）")
        print("        现有特征＝加果干/加巧克力/加蓝莓香蕉/淋蜂蜜/糖浆烤/泡牛奶/倒牛奶")
        return 1
    print(f"匹配 {len(hits)} 张（关键词：{' + '.join(kws)}）\n")
    for fn in hits:
        print(f"  {fn}")
        d = DESC.get(stem(fn))
        if d:
            print(f"    → {d}")
    print(f"\n取图：python3 {os.path.basename(__file__)} square \"{kws[0]}\" --out <目录> --size 900")
    return 0


def cmd_check(a):
    bad = 0
    files = list(iter_files())
    for fn in files:
        s = stem(fn)
        errs = []
        parts = s.split("_")
        if len(parts) != 5:
            errs.append(f"段数 {len(parts)}≠5")
        else:
            if parts[0] not in SEMANTIC:
                errs.append(f"①语义档 '{parts[0]}' 不在 {'/'.join(SEMANTIC)}")
            if not any(parts[1].startswith(s) for s in SUBJECT):
                errs.append(f"②主体 '{parts[1]}' 不是燕麦本体（应以 {'/'.join(SUBJECT)} 开头；"
                            f"麦圈/巧克力圈/玉米片不收）")
            if parts[3] not in SHOT:
                errs.append(f"④景别 '{parts[3]}' 不在 {'/'.join(SHOT)}")
            if not SRC_RE.match(parts[4]):
                errs.append(f"⑤来源 '{parts[4]}' 应为 pexels-<数字>")
        if re.search(r"[()（）\s\-]{1,}", s) and not SRC_RE.search(s):
            pass
        if any(c in s for c in " ()（）"):
            errs.append("含空格或括号")
        if re.search(r"_[abc]$|_v\d+$", s):
            errs.append("不得用 a/b/c 或 v2 版本后缀")
        if any(b in s for b in ("家乐氏", "Kellogg", "欧扎克", "Ocak")):
            errs.append("文件名出现品牌名（品牌本身就不该入库）")
        if stem(fn) not in DESC:
            errs.append("未登记画面说明（DESC）")
        if errs:
            bad += 1
            print(f"✗ {fn}")
            for e in errs:
                print(f"    · {e}")
    if bad:
        print(f"\n{bad}/{len(files)} 张命名或登记不合规 —— 按 _README_命名规则与用图对照.md 第一节改")
        return 1
    print(f"✓ {len(files)} 张全部合规（261108 规则：5 段 / 语义档 / 景别 / 来源-编号 / 已登记说明）")
    return 0


def cmd_square(a):
    from PIL import Image

    kws = a.keywords
    hits = [fn for fn in iter_files() if all(k in stem(fn) for k in kws)]
    if not hits:
        print(f"✗ 没有匹配 {' + '.join(kws)} 的素材")
        return 1
    if len(hits) > 1 and not a.all:
        print(f"! 匹配到 {len(hits)} 张，只处理第一张（要全部加 --all）：")
        for h in hits:
            print(f"    {h}")
    os.makedirs(a.out, exist_ok=True)
    for fn in (hits if a.all else hits[:1]):
        src = os.path.join(NET_DIR, fn)
        im = Image.open(src).convert("RGB")
        w, h = im.size
        s = min(w, h)
        # bias: -1 取上边, 0 居中, +1 取下边
        y = (h - s) // 2 + int(a.bias * (h - s) / 2)
        x = (w - s) // 2
        x = max(0, min(w - s, x))
        y = max(0, min(h - s, y))
        out = os.path.join(a.out, f"{stem(fn)}_sq{a.size}.jpg")
        im.crop((x, y, x + s, y + s)).resize((a.size, a.size), Image.LANCZOS).save(out, quality=93)
        print(f"✓ {os.path.basename(out)}  ← 裁 ({x},{y},{s}) 源 {w}x{h}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="网络素材库 检索/校验/裁图")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出全部素材").set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="关键词检索")
    p.add_argument("keywords", nargs="+")
    p.set_defaults(func=cmd_search)

    sub.add_parser("check", help="校验命名合规").set_defaults(func=cmd_check)

    p = sub.add_parser("square", help="裁 1:1 方图")
    p.add_argument("keywords", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, default=900)
    p.add_argument("--bias", type=float, default=0.0, help="-1上 0中 +1下")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_square)

    a = ap.parse_args()
    sys.exit(a.func(a))


if __name__ == "__main__":
    main()
