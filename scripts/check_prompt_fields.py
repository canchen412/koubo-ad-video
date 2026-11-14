#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生图提示词 · 九字段闸门（2026-11-12 立，对应 references/生图提示词_七字段导演表.md）

为什么要有它：老板 2026-11-12「每次生成图片都差点意思、比较重复无序」。
根因＝「根据分镜写画面提示词」是**描述逻辑**，机位/光位/构图这些导演维度
不设成必填就会全被跳过；且全片没人分配过机位，所以逐镜合格、整片一模一样。
本脚本把两件事都变成退出码：
  ① 逐镜：F1–F9 九个字段必须齐，且 F4 必须写清机位（不许只写「特写」「中景」）；
  ② 全片：相邻镜不得撞「景别+方位」，≥6 镜时机位高度≥3 种、方位≥4 种。

输入格式（见参考文档 §四，标签不许改）：
    ## S01
    F1 主体+动作: ...
    F4 景别+机位: 中景，摄像机贴地 8cm、他正后方偏左 20°，朝门缝方向，24mm 广角
    ...

用法：
    python check_prompt_fields.py --prompts <工程>/prompts_生图.md
    python check_prompt_fields.py --prompts prompts.json      # [{"id":"S01","prompt":"..."}]
    python check_prompt_fields.py --prompts p.md --core7     # 只查外部给的七个字段
    python check_prompt_fields.py --prompts p.md --no-film   # 关掉全片编排检查

退出码：0 全过（或只有 WARN）；1 有 FAIL。
"""
import argparse
import json
import re
import sys

# ---------- 字段标签 ----------
FIELD_KEYS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"]
CORE7 = ["F1", "F2", "F3", "F4", "F5", "F6", "F7"]
FIELD_NAME = {
    "F1": "主体+动作", "F2": "角色参考", "F3": "场景", "F4": "景别+机位",
    "F5": "光线", "F6": "构图", "F7": "风格+情绪", "F8": "可动之物", "F9": "负向+画风锚",
}

SHOT_RE = re.compile(r"^\s{0,3}#{1,4}\s*(?:镜|shot|s)?\s*([0-9]{1,3})\s*$", re.I)
SHOT_RE2 = re.compile(r"^\s{0,3}#{1,4}\s*(?:镜|S|shot\s*)?\s*([0-9]{1,3})\b", re.I)
FIELD_RE = re.compile(r"^\s*[-*>\s]*\**\s*(F[1-9])\b\s*\**\s*(.*)$")

# ---------- 词表 ----------
JB = [("大远景", "EWS"), ("远景", "WS"), ("全景", "FS"), ("中近景", "MCU"),
      ("中景", "MS"), ("近景", "MCU"), ("大特写", "ECU"), ("特写", "CU"),
      ("过肩", "OTS"), ("OTS", "OTS"), ("ECU", "ECU"), ("MCU", "MCU"),
      ("CU", "CU"), ("WS", "WS"), ("MS", "MS")]
FOCAL = re.compile(r"\d{1,3}\s*(?:mm|毫米)", re.I)
HEIGHT = [("贴地", "ground"), ("地面", "ground"), ("离地", "ground"), ("地平面", "ground"),
          ("膝", "body"), ("腰", "body"), ("胸", "body"), ("肩高", "body"),
          ("眼高", "eye"), ("视平", "eye"), ("平视", "eye"),
          ("顶视", "top"), ("鸟瞰", "top"), ("俯拍", "top"), ("俯视", "top"), ("高角", "top"),
          ("仰拍", "low"), ("仰角", "low"), ("低角", "low"), ("仰视", "low")]
DIR = [("过肩", "ots"), ("侧后", "back"), ("背后", "back"), ("后方", "back"), ("正后", "back"),
       ("正前", "front"), ("正面", "front"),
       ("偏左", "left"), ("左侧", "left"), ("左前", "left"), ("左", "left"),
       ("偏右", "right"), ("右侧", "right"), ("右前", "right"), ("右", "right")]
FACING = re.compile(r"朝|对准|面向|看向|对着|指向|望向|冲着")
LIGHT_DIR = re.compile(r"左|右|上|下|顶|底|侧|逆|背|斜|正前|后方")
LIGHT_Q = re.compile(r"暖|冷|硬|柔|漫射|中性|高反|开尔文|\d{3,5}\s*K\b", re.I)
COMP_POS = re.compile(r"左|右|中|三分|角|边缘|居中|偏")
COMP_DEPTH = re.compile(r"前景|虚焦|景深|bokeh|遮挡|模糊|压缩|后景", re.I)
MOTION = re.compile(r"升|降|落|飘|飞|溅|涌|扫|滚|旋|扩散|流动|穿梭|翻涌|闪|炸|坠|横|卷|蒸|冒|漂|抖|晃")
TIME_W = re.compile(r"夜|日|晨|早|午|晚|黄昏|黎明|傍晚|白天|深夜|凌晨|时间|光时")
WEATHER = re.compile(r"晴|阴|雨|雪|雾|风|云|霾|室内|室外|晴空")
STYLE = re.compile(r"厚涂|动漫|2D|3D|写实|画风|anime|thick-paint|CG|赛璐璐", re.I)


def bucket(txt, table):
    """返回第一个命中的分桶标签（表按优先级排好）。"""
    for kw, tag in table:
        if kw in txt:
            return tag
    return None


def parse_md(path):
    """按 ## 镜头标题切块，返回 [(shot_id, {F1: text, ...})]"""
    shots, cur_id, cur = [], None, {}
    header_level = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = SHOT_RE.match(line) or SHOT_RE2.match(line)
            is_header = bool(m) and line.lstrip().startswith("#")
            if is_header:
                if cur_id is not None:
                    shots.append((cur_id, cur))
                cur_id, cur = normalize_id(m.group(1)), {}
                header_level = True
                continue
            fm = FIELD_RE.match(line)
            if fm and cur_id is not None:
                key, rest = fm.group(1), fm.group(2)
                # 去掉 "主体+动作: " 之类的前缀名，只留冒号后的内容
                if ":" in rest or "：" in rest:
                    rest = re.split(r"[:：]", rest, maxsplit=1)[1]
                elif rest.strip() and not rest.strip().startswith(("主体", "角色", "场景", "景别",
                                                                    "光线", "构图", "风格", "可动", "负向")):
                    pass
                cur[key] = (cur.get(key, "") + " " + rest.strip()).strip()
    if cur_id is not None:
        shots.append((cur_id, cur))
    return shots


def normalize_id(raw):
    digits = re.sub(r"\D", "", raw) or "0"
    return "S%02d" % int(digits)


def parse_json(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("shots") or data.get("prompts") or list(data.items())
    out = []
    for i, item in enumerate(data, 1):
        if isinstance(item, dict):
            sid = normalize_id(str(item.get("id") or item.get("shot") or i))
            prompt = item.get("prompt") or item.get("text") or ""
        else:
            sid, prompt = normalize_id(str(i)), str(item)
        fields = {}
        for line in str(prompt).splitlines() or [str(prompt)]:
            fm = FIELD_RE.match(line)
            if fm:
                key, rest = fm.group(1), fm.group(2)
                if ":" in rest or "：" in rest:
                    rest = re.split(r"[:：]", rest, maxsplit=1)[1]
                fields[key] = (fields.get(key, "") + " " + rest.strip()).strip()
        out.append((sid, fields))
    return out


def check_shot(sid, f, required):
    fails, warns = [], []
    for k in required:
        if not f.get(k, "").strip():
            fails.append("缺 %s %s" % (k, FIELD_NAME[k]))
    g = lambda k: f.get(k, "")

    if g("F1") and len(g("F1")) < 8:
        warns.append("F1 过短（<8字），像占位符")

    if g("F2") and not re.search(r"image\s*\d|\.png|\.jpg", g("F2"), re.I):
        fails.append("F2 没挂锚定图（要有 image1=…png 这种）")

    if g("F3"):
        if not TIME_W.search(g("F3")):
            warns.append("F3 没写时间（夜/黄昏/清晨…）")
        if not WEATHER.search(g("F3")):
            warns.append("F3 没写天气/室内外")

    # ---- F4：本表核心 ----
    f4 = g("F4")
    if f4:
        jb = bucket(f4, JB)
        hb = bucket(f4, HEIGHT)
        db = bucket(f4, DIR)
        if not jb:
            fails.append("F4 没写景别（远景/全景/中景/近景/特写/大特写/过肩）")
        if not FOCAL.search(f4) and not hb:
            fails.append("F4 只写了景别，没写机位（要高度如「贴地/胸高/眼高」或焦段如「35mm」）")
        if not db:
            fails.append("F4 没写摄像机方位（正前/左侧30°/侧后/过肩/偏右…）")
        if not FACING.search(f4):
            warns.append("F4 没写机位朝向（朝/对准/面向…）")

    if g("F5"):
        if not LIGHT_DIR.search(g("F5")):
            fails.append("F5 没写光的**方向**（左/右/顶/底/逆/侧）")
        if not LIGHT_Q.search(g("F5")):
            fails.append("F5 没写**质感或色温**（硬/柔/暖/冷/3200K）")

    if g("F6"):
        if not COMP_POS.search(g("F6")):
            fails.append("F6 没写主体位置（左三分之一/右三分/居中偏上…）")
        if not COMP_DEPTH.search(g("F6")):
            warns.append("F6 没写景深或前景（前景虚焦/浅景深/遮挡）")

    if g("F7") and not STYLE.search(g("F7")):
        warns.append("F7 没写画风锚（2D 日系厚涂/赛璐璐…）")

    if g("F8") and not MOTION.search(g("F8")):
        fails.append("F8 没有运动元素（要写蒸汽升腾/液面上升/落叶横飞这种带方向的）")

    if g("F9") and not re.search(r"\bNO\b", g("F9")):
        fails.append("F9 没有负向词（要有 NO text, NO face … 全大写 NO）")

    return fails, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", required=True, help="prompts_生图.md 或 .json")
    ap.add_argument("--core7", action="store_true", help="只要求 F1–F7（外部七字段版）")
    ap.add_argument("--no-film", action="store_true", help="关掉全片机动分配检查")
    ap.add_argument("--min-shots", type=int, default=6, help="少于这个镜数不查全片多样性")
    ap.add_argument("--max-words", type=int, default=200, help="单镜英文词数上限（超出仅 WARN）")
    a = ap.parse_args()

    shots = parse_json(a.prompts) if a.prompts.lower().endswith(".json") else parse_md(a.prompts)
    if not shots:
        print("[FAIL] 一个镜头块都没解析到。确认标题行写成 `## S01` / `## 镜01`。", file=sys.stderr)
        return 1

    required = CORE7 if a.core7 else FIELD_KEYS
    total_fail = total_warn = 0
    meta = {}

    print("=" * 66)
    print("生图提示词 · 九字段闸门 ｜ %d 镜 ｜ 要求字段：%s" % (len(shots), " ".join(required)))
    print("=" * 66)

    for sid, f in shots:
        fails, warns = check_shot(sid, f, required)
        f4 = f.get("F4", "")
        meta[sid] = {"jb": bucket(f4, JB), "dir": bucket(f4, DIR), "h": bucket(f4, HEIGHT),
                     "words": len(re.findall(r"[A-Za-z][A-Za-z'-]*", " ".join(f.values())))}
        if len(required) == 9:
            if meta[sid]["words"] > a.max_words:
                warns.append("英文 %d 词 > %d，建议压到 120–180（堆太多模型会挑保险的那半句）"
                             % (meta[sid]["words"], a.max_words))

        if not fails and not warns:
            print("  ✅ %s  九字段齐，机位=%s/%s" % (sid, meta[sid]["jb"], meta[sid]["dir"]))
        else:
            print("  %s %s" % ("❌" if fails else "⚠️ ", sid))
            for x in fails:
                print("       ✗ %s" % x)
            for x in warns:
                print("       · %s" % x)
        total_fail += len(fails)
        total_warn += len(warns)

    film_fails = []
    film_skipped = a.no_film or len(shots) < a.min_shots
    if not film_skipped:
        ids = [s for s, _ in shots]
        for prev, nxt in zip(ids, ids[1:]):
            p, q = meta[prev], meta[nxt]
            if p["jb"] and p["jb"] == q["jb"] and p["dir"] and p["dir"] == q["dir"]:
                film_fails.append("%s 与 %s 撞「景别+方位」（都 %s/%s）→ 改方位或改景别"
                                  % (prev, nxt, p["jb"], p["dir"]))
        heights = {m["h"] for m in meta.values() if m["h"]}
        dirs = {m["dir"] for m in meta.values() if m["dir"]}
        if len(heights) < 3:
            film_fails.append("全片机位高度只有 %d 种（%s），要求 ≥3 种 → 至少补一镜贴地或顶视"
                              % (len(heights), "、".join(sorted(heights)) or "无"))
        if len(dirs) < 4:
            film_fails.append("全片机位方位只有 %d 种（%s），要求 ≥4 种 → 补侧后/过肩/偏左偏右"
                              % (len(dirs), "、".join(sorted(dirs)) or "无"))

    print("-" * 66)
    if film_fails:
        print("全片调度编排：")
        for x in film_fails:
            print("   ✗ %s" % x)
    elif not film_skipped:
        print("全片调度编排：✅ 相邻镜无撞位，机位种类达标")
    else:
        print("全片调度编排：⏭ 跳过（%s）" % ("--no-film" if a.no_film else
                                              "镜数 %d < %d" % (len(shots), a.min_shots)))

    print("-" * 66)
    print("结果：FAIL %d ／ WARN %d ／ 影片级 FAIL %d" % (total_fail, total_warn, len(film_fails)))
    if total_fail or film_fails:
        print("⇒ 不通过。先按上面逐条补齐（内容去哪取见 references/生图提示词_七字段导演表.md §五），再调生图。")
        return 1
    print("⇒ 通过。可以调生图接口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
