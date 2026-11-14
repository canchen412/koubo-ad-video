#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简版分镜闸门 / 草稿生成
========================
两个用法：

  1) 闸门（出片前必跑，违规返回退出码 1）
     python3 minimal_plan_check.py --plan work/plan.json

  2) 草稿（文案 → 逐句贴纸方案，并列出「库里没有、需要现场抠」的句子）
     python3 minimal_plan_check.py --draft 文案.txt --cut "$CUT" --out work/plan.json

为什么要闸门：极简版靠「一帧最多两元素 + 相邻镜不撞 + 同贴纸最多两次」撑住节奏，
这三条靠人眼排一定会漏，必须机器判。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "sticker_semantic_map.json")

DEFAULT_CUT = "/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库"
Z = {"L": 0.27, "C": 0.50, "R": 0.73}

MAX_ELS = 2          # 一帧最多两个元素
MAX_REUSE = 1        # 同一素材一条片只能用一次（老板 2026-11-03：
                     # 「不管是小绿人还是中间的图片，在一个视频里它不能同时出现两次」）
                     # 以前是 2，s01/s08 都用「举铁_站姿推举」被当场抓到。
MAX_RUN = 2          # 同一种画面类型最多连着出现几次（老板 2026-11-03）
# 高度区间（老板 2026-11-03 二次加大：「抠完图的小绿人出现的时候可以再大一点」）
# 上限不是拍脑袋来的：脚底基线 BASE_Y=970，h=980 时头顶已在 y≈10，再高就出画。
H_MIN, H_MAX = 640, 980
H_TELL_MIN = 620     # 讲解位贴纸（图片旁边那个）高度下限
H_TELL_MAX = 800     # 讲解人得比主体小一档，但不能小到看不清表情
H_DEFAULT, H_TELL_DEFAULT = 940, 740   # 与 minimal_render.STICKER_H / TELLER_H 对齐
CONFIG_MIN_CARD_RATIO = 0.5   # 图片镜数 / 贴纸独镜数 上限（老板 2026-11-03：“图片不要超过小绿人”）

# ★ 独镜的宽高比下限（老板 2026-11-03 v13：「反应」组 13 张全是窄构图）
#   实测 `反应_垂头丧气` asp 0.518 给 940 高只有 487px 宽，成片里两侧各空 716px，
#   像「人退后了两步」，当场换掉。规则：<0.55 不许独镜；0.55–0.70 必须配重点字填空白。
ASP_SOLO_MIN = 0.55
ASP_SOLO_NEED_KW = 0.70


def die(msg):
    """只拼报告行。⚠️ 早期版本这里 return 1（照抄了别的脚本），所有调用处都是
    `lines.append(die(...))` → 一旦真违规，join 时 TypeError 崩掉，看不到任何报告。"""
    return "  ✗ " + msg


def shot_els(s):
    return s.get("els") or [s]


_ASP_CACHE = {}


def sticker_asp(path):
    """贴纸真实宽高比（按 alpha 外接框算，不是画布比例）。读不了就返回 None。"""
    if path in _ASP_CACHE:
        return _ASP_CACHE[path]
    asp = None
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        bb = im.getchannel("A").getbbox()
        if bb:
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            if h > 0:
                asp = w / float(h)
    except Exception:
        asp = None
    _ASP_CACHE[path] = asp
    return asp


# ---- 画面类型：闸门按这三种判「连续重复」（老板 2026-11-03 第三种类型定） ----
TYPE_NAME = {
    "T1": "贴纸独镜",
    "T2": "侧图+讲解人",
    "T3": "方图居中+左右拆字",
}


def shot_type(s):
    """T1 只有贴纸 / T2 侧图+讲解人 / T3 方图拆字。
    full 铺满算图片镜（T2 一类），免得兜底镜绕过连续检查。"""
    kinds = [e.get("kind", "sticker") for e in shot_els(s)]
    if "sqcard" in kinds:
        return "T3"
    if any(k in ("card", "vcard", "full") for k in kinds):
        return "T2"
    return "T1"


def seg_of(s, i):
    return s.get("seg") or ("sci" if i <= 11 else "product")


def check(plan, cut):
    """返回 (错误数, 报告行)。规则见 references/极简版_贴纸模式.md「五条硬闸」。"""
    errs = 0
    lines = []
    shots = plan["shots"]
    used = {}
    all_src = {}          # 素材（贴纸 + 图片）全片出现次数，一条片只许 1 次
    src_kind = {}
    prev_srcs = set()
    n_card_shots = 0
    n_sticker_only = 0
    n_pure_img = 0
    run_type, run_len = None, 0

    for i, s in enumerate(shots, 1):
        sid = s.get("id", "s%02d" % i)
        els = shot_els(s)
        seg = seg_of(s, i)

        # ★ 画面类型不许连续超过 2 次（T1 贴纸 / T2 侧图+讲解人 / T3 方图拆字）
        t = shot_type(s)
        run_len = run_len + 1 if t == run_type else 1
        run_type = t
        if run_len > MAX_RUN:
            lines.append(die("%s 连续第 %d 句都是「%s」（%s）—— 最多连着 %d 次，第 %d 句必须换类型" % (
                sid, run_len, TYPE_NAME[t], t, MAX_RUN, MAX_RUN + 1)))
            errs += 1
        kinds = [e.get("kind", "sticker") for e in els]
        has_card = any(k in ("card", "vcard", "full", "sqcard") for k in kinds)
        has_sq = "sqcard" in kinds
        has_sticker = "sticker" in kinds

        if has_card:
            n_card_shots += 1
            # ★ 图片镜二选一：侧图必须带讲解人；方图居中必须自带左右拆字（老板 2026-11-03）
            if has_sq:
                n_pure_img += 1
                kw = s.get("kw")
                if not (isinstance(kw, dict) and (kw.get("l") or kw.get("r"))):
                    lines.append(die("%s 方图镜缺左右拆字：kw 要写 {\"l\":\"熬\",\"r\":\"夜\"}" % sid))
                    errs += 1
                elif isinstance(kw, dict):
                    # ★ 每侧最多 2 个汉字（≈4 个 ASCII 字符）。
                    #   2026-11-03 实测：3 汉字会顶到画边，距边 0px 直接被切，
                    #   缩字号也救不回 —— 排版算可用宽度时没含描边+投影（约 45px）。
                    for side, label in (("l", "左"), ("r", "右")):
                        txt = str(kw.get(side) or "")
                        units = sum(2 if ord(ch) > 127 else 1 for ch in txt)
                        if units > 4:
                            lines.append(die("%s 方图%s侧拆字「%s」超宽（%d 单位 > 4）："
                                             "每侧最多 2 个汉字，3 字会顶到画边被切" % (
                                                 sid, label, txt, units)))
                            errs += 1
                if len(els) > 1:
                    lines.append(die("%s 方图镜不要叠元素（左右大字已占满两侧）" % sid))
                    errs += 1
            elif not has_sticker:
                lines.append(die("%s 只有图片没有小绿人：侧图必须配讲解贴纸（els 里加一个 sticker）" % sid))
                errs += 1
        else:
            n_sticker_only += 1

        if len(els) > MAX_ELS:
            lines.append(die("%s 放了 %d 个元素，上限 %d" % (sid, len(els), MAX_ELS)))
            errs += 1

        cur_srcs = set()
        for el in els:
            kind = el.get("kind", "sticker")
            src = el.get("src", "")
            if not src:
                lines.append(die("%s 缺 src" % sid))
                errs += 1
                continue

            p = src if os.path.isabs(src) else os.path.join(cut, src)
            # 和 minimal_render.StickerLib.load 同一条规则：同目录有 xxx_净边.png 就用它。
            # 两边不一致会出现「闸门说不存在、渲染却能跑」的假违规（2026-11-03 踩过）。
            if "_净边" not in p:
                clean = os.path.splitext(p)[0] + "_净边.png"
                if os.path.exists(clean):
                    p = clean
            if not os.path.exists(p):
                lines.append(die("%s 素材不存在：%s" % (sid, p)))
                errs += 1

            # ★ 全片唯一：贴纸和小绿人旁边的图片都只许出现一次
            all_src[src] = all_src.get(src, 0) + 1
            src_kind.setdefault(src, kind)
            if all_src[src] > MAX_REUSE:
                where = "图片" if kind != "sticker" else "小绿人"
                lines.append(die("%s 的%s「%s」在本片第 %d 次出现 —— 一条片里每个素材只能用一次，换一个" % (
                    sid, where, os.path.basename(src), all_src[src])))
                errs += 1

            if kind == "sticker":
                zone = el.get("zone", "C")
                is_last = (i == len(shots))
                is_teller = el.get("role") == "teller"     # 图片旁的讲解人
                if seg == "sci" and zone != "C" and not is_teller:
                    lines.append(die("%s 科普段只能放 C 区，现在写的是 %s" % (sid, zone)))
                    errs += 1
                if seg != "sci" and not is_teller and zone not in ("L", "R") and not (is_last and zone == "C"):
                    lines.append(die("%s 产品段要分左右区（L/R，收尾镜可 C），现在写的是 %s" % (sid, zone)))
                    errs += 1
                h = int(el.get("h", H_TELL_DEFAULT if is_teller else H_DEFAULT))
                lo = H_TELL_MIN if is_teller else H_MIN
                hi = H_TELL_MAX if is_teller else H_MAX
                if not (lo <= h <= hi):
                    lines.append(die("%s 贴纸高度 %d 超出 %d–%d%s" % (
                        sid, h, lo, hi, "（讲解位）" if is_teller else "")))
                    errs += 1
                used[src] = used.get(src, 0) + 1
                cur_srcs.add(src)

                # ★ 独镜体量：窄姿态一个人扛不动 1920 画幅（见 ASP_SOLO_MIN 注释）
                #   但「物品/」豁免 —— 产品罐、胶囊、药瓶天生是瘦高的（罐子 asp 0.45
                #   是物理事实，不是姿态问题），拿宽高比卡它等于不许用产品。
                if not is_teller and not has_card and not src.startswith("物品/"):
                    asp = sticker_asp(p)
                    if asp is not None:
                        if asp < ASP_SOLO_MIN:
                            lines.append(die("%s 独镜用了窄姿态 %s（asp %.2f < %.2f）：940 高只有 %dpx 宽，"
                                             "画面会空 —— 换宽体块姿态，或改成讲解位/方图" % (
                                                 sid, os.path.basename(src), asp, ASP_SOLO_MIN,
                                                 int(940 * asp))))
                            errs += 1
                        elif asp < ASP_SOLO_NEED_KW and not s.get("kw"):
                            lines.append(die("%s 独镜姿态偏窄（asp %.2f < %.2f）却没写重点字："
                                             "两侧空白没东西填，必须加 kw" % (sid, asp, ASP_SOLO_NEED_KW)))
                            errs += 1

                # ★★ 纯贴纸独镜一律要有重点字（老板 2026-11-04）
                #   「只有小绿人一个人出来，其他左边全部是空白，不能出现这种场面……
                #    空空的地方一定要有一个重点字」。
                #   窄姿态那条（ASP_SOLO_NEED_KW）只拦 asp<0.70，可宽姿态照样会空一整侧
                #   —— v3 s03「今天我们讲肌酸」人站右侧、左边 900px 全空，当场被点名。
                #   物品/ 豁免：产品罐独镜是产品展示，罐子本身占中轴，不按人物算。
                if (not is_teller and not has_card and not s.get("kw")
                        and not src.startswith("物品/")):
                    lines.append(die("%s 只有一个小绿人、旁边整片留白（%s 区）却没写重点字："
                                     "空白侧必须压 2–4 字 kw，取自本句口播的重词" % (
                                         sid, el.get("zone", "C"))))
                    errs += 1
            elif kind in ("card", "vcard"):
                if (el.get("w") or 0) > 1180:
                    lines.append(die("%s 卡片宽 %s > 1180" % (sid, el.get("w"))))
                    errs += 1
            elif kind == "full":
                if len(els) > 1:
                    lines.append(die("%s full 铺满时不能再叠元素" % sid))
                    errs += 1

        card_zones = [e.get("zone", "C") for e in els
                      if e.get("kind", "sticker") in ("card", "vcard", "sqcard")]
        tell_zones = [e.get("zone", "C") for e in els if e.get("role") == "teller"]
        if card_zones and tell_zones and card_zones[0] == tell_zones[0]:
            lines.append(die("%s 讲解人和图片挤在同一侧（%s），必须一左一右" % (sid, card_zones[0])))
            errs += 1

        dup = cur_srcs & prev_srcs
        if dup:
            lines.append(die("%s 与上一镜用了同一个贴纸：%s" % (sid, ", ".join(sorted(dup)))))
            errs += 1
        prev_srcs = cur_srcs

    # （重复检查已上移到逐元素处，贴纸和图片同一套规则，这里不再重复报）

    n_stk = sum(used.values())

    # ★ 极简风是「小绿人说话」，图片只是偶尔拿来解释。
    # 口径（2026-11-03 v4 调整）：①画面里**没有小绿人**的纯图镜（T3 方图拆字）必须少于贴纸独镜；
    # ②图片镜总数不许超过小绿人出现次数（独镜 + 图片旁的讲解位）。
    # 产品段天然要露产品图，按这条口径仍然成立，不会把「产品段露产品」判成违规。
    if n_pure_img > n_sticker_only:
        lines.append(die("纯图镜（方图拆字，画面里没小绿人）%d 句 > 贴纸独镜 %d 句：无人的图必须少于小绿人" % (
            n_pure_img, n_sticker_only)))
        errs += 1
    if n_card_shots > n_stk:
        lines.append(die("图片镜 %d 句 > 小绿人出现 %d 次（独镜+讲解位）：图片不许压过小绿人（老板 2026-11-03）" % (
            n_card_shots, n_stk)))
        errs += 1

    lines.append("· 类型序列：" + " ".join(shot_type(s) for s in shots))
    lines.append("· %d 句 / 贴纸 %d 次（独镜 %d + 讲解 %d）/ 不同贴纸 %d 个 / 图片镜 %d 句 / 纯图镜 %d 句" % (
        len(shots), n_stk, n_sticker_only, n_stk - n_sticker_only, len(used), n_card_shots, n_pure_img))
    for src, n in sorted(used.items(), key=lambda kv: -kv[1]):
        lines.append("    %d× %s" % (n, os.path.basename(src)))
    return errs, lines


def draft(texts_path, cut, out_path, start_index=1):
    """按语义表给每句配贴纸；配不上/撞满的标 need_new，等现场抠图"""
    rules = json.load(open(MAP, encoding="utf-8"))["rules"]
    texts = [ln.strip() for ln in open(texts_path, encoding="utf-8") if ln.strip()]

    plan = {"bg": "random", "bg_group": "comic_dark", "shots": []}
    used = {}
    prev = set()
    todo = []

    for i, text in enumerate(texts, start_index):
        sid = "s%02d" % i
        seg = "sci" if i <= start_index + 9 else "product"

        scored = []
        for r in rules:
            hit = sum(1 for k in r["keys"] if k in text)
            if hit:
                scored.append((hit, r))
        scored.sort(key=lambda x: -x[0])

        pick = None
        for hit, r in scored:
            src = r["src"]
            if src in prev:                       # 相邻镜不撞
                continue
            if used.get(src, 0) >= MAX_REUSE:      # 一片最多两次
                continue
            pick = r
            break

        zone = "C" if seg == "sci" else ("L" if i % 2 else "R")
        if pick is None:
            # 不硬凑：语义没命中就是「库里没有合适的」，标出来等现场抠图
            plan["shots"].append({"id": sid, "seg": seg, "kind": "card",
                                  "src": "", "ar": "16x9", "zone": zone,
                                  "need_new": True, "why": text})
            todo.append((sid, text, "语义无匹配，建议现场抠一张"))
            prev = set()
            continue

        plan["shots"].append({"id": sid, "seg": seg, "kind": "sticker",
                              "src": pick["src"], "zone": zone,
                              "h": H_DEFAULT, "off": 0.02})
        used[pick["src"]] = used.get(pick["src"], 0) + 1
        prev = {pick["src"]}

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump(plan, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("→ %s（%d 句，待补 %d 句）" % (out_path, len(texts), len(todo)))
    for sid, text, why in todo:
        print("    %s %s  ← %s" % (sid, text, why))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan")
    ap.add_argument("--draft")
    ap.add_argument("--cut", default=DEFAULT_CUT)
    ap.add_argument("--out", default="plan.json")
    ap.add_argument("--start-index", type=int, default=1)
    a = ap.parse_args()

    if a.draft:
        sys.exit(draft(a.draft, a.cut, a.out, a.start_index))
    if not a.plan:
        ap.error("要么 --plan，要么 --draft")

    plan = json.load(open(a.plan, encoding="utf-8"))
    errs, lines = check(plan, a.cut)
    print("\n".join(lines))

    # 背景必须是显式预设（2026-11-03）：写 "random" 等于渲染时才抽，历史记不上、下批必撞
    bg = plan.get("bg")
    if bg in (None, "random"):
        print("\n⚠️  bg=%r：本片背景没定死。先跑 scripts/bg_rotate.py pick --n 1 取一个预设写进 plan，"
              "否则下一批无法保证「背景不一样」" % bg)

    if errs:
        print("\n❌ %d 处违规，不许出片" % errs)
        sys.exit(1)
    print("\n✅ 闸门全绿")


if __name__ == "__main__":
    main()
