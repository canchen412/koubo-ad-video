#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_sku_match.py —— 同品牌多代包装「款型」闸门（带退出码）
─────────────────────────────────────────────────────────────────────
用途：①出片前硬校验 —— 这条文案讲的是哪一款，shot_map 里用的就必须是哪一款的图。
      ②归档时硬校验 —— 归一化到哪一款的目录（`--archive-dir`），必须与文案判款一致。

背景（2026-11-01 灿爹纠正）：
  诺特兰德烟酰胺有**两款在售包装**（新款粉瓶 / 老款白瓶），图库也分两个目录。
  文案不提「虾青素 / 葡萄籽 / 新款」，它就是老款；却给配了新款粉瓶 ⇒ 货不对板。

背景（2026-11-02 灿爹再次纠正 · 归档分类）：
  选图判款改对了，**归档分类又错了**：那批 4 条片里前 3 条口播含「虾青素、葡萄籽」（新款），
  第 4 条不含（老款），我却按"同一天同一批"把 4 条全塞进 `烟酰胺/诺特新款/261101`。
  ⇒ 判款规则必须一路管到归档目录，不能只在选图那一环生效。

用法：
  # 选图校验
  python check_sku_match.py --phrases v1/phrases.txt --shot-map v1.shot_map.json
  python check_sku_match.py --text copy.txt --shot-map v1.shot_map.json
  # 归档分类校验（源工程已删也能跑，不需要 shot_map）
  python check_sku_match.py --text 本条口播.txt --archive-dir /…/烟酰胺/诺特老款/261101

  --phrases      一行一句，与 shot_map 一一对应（含镜1 专用位时按同序对齐）
  --text         整段口播；此时只做全片判定（全片产品图必须同为该款）
  --archive-dir  归档目标目录；与本条文案判款不符即失败

退出码：0 = 全部对齐；1 = 有 mismatch / 无法判定

判款规则（详见 references/素材款型台账.json）：
  ① 素材款型：看 src 路径命中哪个款型的「目录关键词」
  ② 期望款型：看该镜文案命中哪个款型的「触发词」；一个都不命中 ⇒ default_for（默认在售款）
  ③ 共用成分（维C/维E/烟酰胺/B族）永远不是触发词 —— 两款都有，用它判款必错
"""
import argparse
import json
import os
import re
import sys

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "references", "素材款型台账.json")

C_OK = "\033[32m"
C_BAD = "\033[31m"
C_WARN = "\033[33m"
C_OFF = "\033[0m"


def load_ledger(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_sentences(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            out.append(s)
    return out


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return "".join(f.read().split("\n"))


def src_of(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("src") or ""
    return ""


def pick_variant_by_path(path, brand):
    """素材路径 → 款型名（None=不是该品牌的款型目录）"""
    base = os.path.basename(path)
    # ① 单图款型表优先（根目录混放的老图文件名不带款型字样，只能靠台账点名）
    for fn, vn in (brand.get("单图款型") or {}).items():
        if base == fn:
            return vn
    # ② 再按目录关键词
    for name, spec in brand["款型"].items():
        for kw in spec.get("目录关键词", []):
            if kw and kw in path:
                return name
    return None


def pick_variant_by_text(text, brand):
    """文案 → 期望款型名 + 命中的触发词"""
    best, best_hits = None, []
    for name, spec in brand["款型"].items():
        hits = [kw for kw in spec.get("触发词", []) if kw and kw in text]
        if len(hits) > len(best_hits):
            best, best_hits = name, hits
    if best is None:
        best = brand.get("default_for")
    return best, best_hits


def pick_variant_by_archive(path, brand):
    """归档目录路径 → 款型名（按「归档目录关键词」，与图库的「目录关键词」分开）"""
    norm = (path or "").rstrip("/")
    for name, spec in brand["款型"].items():
        for kw in spec.get("归档目录关键词", []):
            if kw and kw in norm:
                return name
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrases")
    ap.add_argument("--text")
    ap.add_argument("--shot-map")
    ap.add_argument("--archive-dir",
                    help="归档目标目录（如 …/烟酰胺/诺特老款/261101）；"
                         "给出后额外校验「归到哪一款的目录」与文案判款一致")
    ap.add_argument("--ledger", default=LEDGER)
    a = ap.parse_args()

    if not a.phrases and not a.text:
        sys.exit("需要 --phrases 或 --text")
    if not a.shot_map and not a.archive_dir:
        sys.exit("需要 --shot-map（校验选图）或 --archive-dir（校验归档分类），至少给一个")

    ledger = load_ledger(a.ledger)
    srcs = []
    if a.shot_map:
        shot_map = json.load(open(a.shot_map, encoding="utf-8"))
        srcs = [src_of(x) for x in shot_map]

    sentences = read_sentences(a.phrases) if a.phrases else None
    full_text = read_text(a.text) if a.text else "".join(sentences or [])

    fails, warns = [], []

    # ---- 镜号对齐 ----
    # pipeline 语义：shot_map 项数 == 镜数-1 时不含「镜1 专用位」，mapping[0] 对应镜2
    # （镜1 归开头卷播）；项数 == 镜数时含专用位，mapping[0] 就是镜1。
    # phrases 的行数就是镜数，据此推偏移，别再把镜号报歪。
    off = 0
    if sentences:
        d = len(sentences) - len(srcs)
        if d in (0, 1):
            off = d
        else:
            print(f"{C_WARN}⚠️ phrases {len(sentences)} 行 vs shot_map {len(srcs)} 项，"
                  f"差值 {d} 不是 0/1，无法推断镜号偏移，按 0 处理{C_OFF}")
    else:
        print(f"{C_WARN}⚠️ 只给了整段文案，镜号按 shot_map 顺序报（不含镜1 偏移推断）{C_OFF}")

    print("=" * 74)
    print(f"款型闸门 check_sku_match  （shot_map {len(srcs)} 项 / 镜号偏移 +{off}）")
    if a.archive_dir:
        print(f"另校验归档分类：{a.archive_dir}")
    print("=" * 74)

    arch_matched = False
    for bname, brand in ledger["brands"].items():
        rooted = [s for s in srcs if s and pick_variant_by_path(s, brand)]
        arch = pick_variant_by_archive(a.archive_dir, brand) if a.archive_dir else None
        if arch is not None:
            arch_matched = True
        if not rooted and arch is None:
            continue

        # ---- 全片期望款型（整段文案口径）----
        global_want, global_hits = pick_variant_by_text(full_text, brand)
        print(f"\n【{bname}】全片判定：{C_WARN}{global_want}{C_OFF}"
              f"（触发词：{'/'.join(global_hits) if global_hits else '无 → 走默认款'}）")

        # ---- 归档分类校对（2026-11-02 加的：归错款型目录的闸门）----
        if arch is not None:
            if arch == global_want:
                print(f"  归档分类 {C_OK}PASS{C_OFF}：文案判 {global_want}，"
                      f"归进「{arch}」目录 —— 一致")
            else:
                print(f"  归档分类 {C_BAD}FAIL{C_OFF}：文案判 {global_want}，"
                      f"却归进「{arch}」目录")
                fails.append(
                    f"归档目录错了：这条文案判 {global_want}（触发词 "
                    f"{'/'.join(global_hits) if global_hits else '无'} ），"
                    f"却归进「{arch}」→ {a.archive_dir}"
                )

        if not rooted:
            continue

        # ---- 逐镜比对 ----
        print(f"{'镜':<4}{'素材款型':<10}{'该句期望':<10}{'触发词':<22}结论")
        for i, s in enumerate(srcs):
            got = pick_variant_by_path(s, brand)
            if got is None:
                continue
            si = i + off
            sn = i + 1 + off
            sent = sentences[si] if (sentences and si < len(sentences)) else full_text
            want, hits = pick_variant_by_text(sent, brand)
            ok = (got == want)
            mark = f"{C_OK}PASS{C_OFF}" if ok else f"{C_BAD}FAIL{C_OFF}"
            hit_s = "/".join(hits) if hits else "-"
            print(f"{sn:<4}{got:<10}{want:<10}{hit_s:<22}{mark}")
            if not ok:
                fails.append(
                    f"镜{sn}：文案「{sent[:26]}…」判定为 {want}，"
                    f"实际用的 {got} 图 → {os.path.basename(s)}"
                )
            # 与全片口径不一致也报（"某句漏判"的兜底）
            if got != global_want:
                warns.append(f"镜{sn} 用 {got}，但全片口径是 {global_want}")

        # ---- 素材侧反向检查：不该出现的款型一张都不许进 shot_map ----
        bad_dirs = [k for vn, spec in brand["款型"].items() if vn != global_want
                    for k in spec.get("目录关键词", [])]
        bad_files = [fn for fn, vn in (brand.get("单图款型") or {}).items()
                     if vn != global_want]
        for i, s in enumerate(srcs):
            if not s:
                continue
            if any(k in s for k in bad_dirs) or os.path.basename(s) in bad_files:
                if not any(f"镜{i + 1 + off}" in f for f in fails):
                    fails.append(
                        f"镜{i + 1 + off}：用了非 {global_want} 的图 → {os.path.basename(s)}")

    if a.archive_dir and not arch_matched:
        fails.append(
            f"归档目录「{a.archive_dir}」没命中台账里任何款型的「归档目录关键词」，"
            f"判不出款型 —— 核对目录名，或在 references/素材款型台账.json 里补上该关键词"
        )

    print("\n" + "=" * 74)
    if fails:
        print(f"{C_BAD}❌ {len(fails)} 处货不对板：{C_OFF}")
        for f in fails:
            print("   · " + f)
        print("\n修法：按台账 references/素材款型台账.json 里该款型的「瓶身特征」换图；"
              "归档目录错了就把整个日期文件夹移到对应款型目录，别只改里面文件名。")
        sys.exit(1)
    if warns:
        print(f"{C_WARN}⚠️ 非阻断提示：{C_OFF}")
        for w in warns:
            print("   · " + w)
    print(f"{C_OK}✅ 款型全部对齐{C_OFF}")
    sys.exit(0)


if __name__ == "__main__":
    main()
