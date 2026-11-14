#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch_plan_check.py — 一批极简版 plan 的跨片去重闸门（2026-11-03 老板定）

## 为什么需要它

老板 2026-11-03 原话：「如果我一次给你几条文案，你做出来的视频尽量在
**相同语义的图片不一样，背景也不一样**。」

`check_batch_dedup.py` 管的是 pipeline 版（brand_*.json：开头撞、素材跨片复用、
首句撞、文案相似），**读不了极简版的 plan.json**；而极简版恰恰是最容易「一批多片
全用同一个背景 + 同一张产品图」的通道——因为图片是按语义从图库现抓的，
同一句话必然抓到同一张。

本脚本补这一层：**只读 plan.json，不改文件、不渲染**。红了改 plan 再跑。

## 用法

    PY=/Users/yourname/.workbuddy/binaries/python/envs/default/bin/python
    SK=~/.workbuddy/skills/koubo-ad-video

    # 一次几条就给几个 --plan（顺序就是发布顺序）
    $PY $SK/scripts/batch_plan_check.py \
        --plan work/a/plan.json --plan work/b/plan.json --plan work/c/plan.json

    # 只要结论
    $PY $SK/scripts/batch_plan_check.py --plan ... --quiet

## 判定

- ❌ FAIL：同批背景撞 / 素材跨片复用 / 两片用了视觉近似的同一张图（dHash 距离 < 12）
- ⚠️  WARN：背景与历史最近 2 条撞（跨批不算违规，但建议换）/ 同批重点字全同
- ✅ PASS：exit 0；有任何 ❌ 则 exit 1（流水线里红了不许发）

## 与单条闸门的分工

`minimal_plan_check.py` 管单条（镜数/时长/kw 避让/贴纸宽高比），
**本脚本只管片与片之间**。两个都要跑：先单条过闸，再跑本脚本。
"""
import argparse
import json
import os
import re
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 pillow")

NEAR_DUP_HAMMING = 12        # dHash 汉明距离 < 12 视为「视觉上是同一张图」
HISTORY_KEEP = 2             # 与历史最近 K 条的背景撞 → WARN

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(os.path.dirname(HERE), "assets", "bg_library", "_bg_使用历史.json")

FAIL, WARN, OK = "❌", "⚠️ ", "✅"


def dhash(path, size=16):
    """16×16 差分哈希 = 256 bit，返回 int。图读不了返回 None。"""
    try:
        im = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    except Exception:
        return None
    px = list(im.tobytes())
    bits = 0
    for y in range(size):
        row = y * (size + 1)
        for x in range(size):
            bits = (bits << 1) | (1 if px[row + x] > px[row + x + 1] else 0)
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def kw_text(s):
    """重点字文本。缺省 plan 里 kw 既可能是字符串（"蛋白吐司"），也可能是
    字典（{"t":..} / {"l":..,"r":..}），两种都要认，否则整条批检直接崩。"""
    kw = s.get("kw")
    if not kw:
        return ""
    if isinstance(kw, str):
        return kw
    return (kw.get("t") or "") + (kw.get("l") or "") + (kw.get("r") or "")


def load_plan(p):
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    shots = d.get("shots", [])
    items = []          # (镜号, 素材路径, 重点字文本)
    for s in shots:
        kwt = kw_text(s)
        if s.get("els"):
            for e in s["els"]:
                if e.get("src"):
                    items.append((s.get("id", "?"), e["src"], kwt))
        elif s.get("src"):
            items.append((s.get("id", "?"), s["src"], kwt))
    return d, shots, items


def main():
    ap = argparse.ArgumentParser(description="一批 plan 的跨片去重闸门")
    ap.add_argument("--plan", action="append", required=True, help="plan.json（可多个）")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if len(a.plan) < 2:
        print("%s 只给了 1 条 plan，跨片检查无意义（单条请跑 minimal_plan_check.py）" % WARN)
        return 0

    plans = []
    for p in a.plan:
        d, shots, items = load_plan(p)
        ap_ = os.path.abspath(p)
        plans.append({"path": p, "name": os.path.basename(os.path.dirname(ap_)),
                      "stem": os.path.splitext(os.path.basename(ap_))[0],
                      "plan": d, "shots": shots, "items": items})
    # 多条 plan 挤在同一目录时（试算/对比场景），目录名会重名 → 改用文件名区分
    dirs = [P["name"] for P in plans]
    if len(set(dirs)) < len(dirs):
        for P in plans:
            P["name"] = P["stem"]

    fails, warns = [], []

    def say(level, msg):
        print("%s %s" % (level, msg))
        if level == FAIL:
            fails.append(msg)
        elif level == WARN:
            warns.append(msg)

    print("=" * 68)
    print("跨片去重 · %d 条" % len(plans))
    print("=" * 68)

    # ---------- 1. 背景：同批必须互不相同 ----------
    bgs = [(P["name"], P["plan"].get("bg")) for P in plans]
    print("\n【背景】")
    for n, b in bgs:
        print("   %-16s bg=%s" % (n, b))
    seen = {}
    for n, b in bgs:
        if not b or b == "random":
            say(FAIL, "「%s」的 bg 写的是 %r —— 必须是显式预设（先跑 bg_rotate.py pick），"
                      "写 random 等于这一批没人知道用了哪张墙、下一批必撞" % (n, b))
            continue
        if b in seen:
            say(FAIL, "背景撞：%s 与 %s 都是 %s → 换其中一个（bg_rotate.py pick --exclude %s）"
                % (n, seen[b], b, b))
        else:
            seen[b] = n
    if len(seen) == len(bgs) and all(b and b != "random" for _, b in bgs):
        say(OK, "同批 %d 条背景互不相同" % len(bgs))

    # ---------- 2. 背景：与历史最近 K 条别撞（跨批建议级）----------
    if os.path.exists(HIST):
        try:
            hist = json.load(open(HIST, encoding="utf-8")).get("records", [])
        except Exception:
            hist = []
        recent = [r.get("preset") for r in hist[-HISTORY_KEEP:]]
        for n, b in bgs:
            if b and b in recent:
                say(WARN, "「%s」的背景 %s 与最近 %d 条历史撞了（建议换一个，跨批不强制）"
                    % (n, b, HISTORY_KEEP))

    # ---------- 3. 素材：不许跨片复用 ----------
    print("\n【素材】")
    owner = {}
    for P in plans:
        for sid, src, _ in P["items"]:
            key = os.path.abspath(src) if not src.startswith("角色/") else src
            owner.setdefault(key, []).append((P["name"], sid))
    reused = {k: v for k, v in owner.items() if len({x[0] for x in v}) > 1}
    if reused:
        for k, v in reused.items():
            who = "、".join("%s(%s)" % (n, s) for n, s in v)
            say(FAIL, "素材跨片复用：%s ← %s" % (os.path.basename(k), who))
    else:
        say(OK, "无跨片复用（%d 个素材，全片各用一次）" % len(owner))

    # ---------- 4. 视觉近似：不同路径但其实是同一张图 ----------
    hashes = {}
    for k in owner:
        if k.startswith("角色/"):
            continue
        if not os.path.exists(k):
            continue
        h = dhash(k)
        if h is not None:
            hashes[k] = h
    dup = []
    keys = list(hashes)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            d = hamming(hashes[keys[i]], hashes[keys[j]])
            if d < NEAR_DUP_HAMMING:
                dup.append((keys[i], keys[j], d))
    if dup:
        for x, y, d in dup[:10]:
            say(FAIL, "视觉近似同图（dHash 距离 %d）：%s ↔ %s → 换一张"
                % (d, os.path.basename(x), os.path.basename(y)))
    else:
        say(OK, "无视觉近似同图（两两 dHash ≥ %d）" % NEAR_DUP_HAMMING)

    # ---------- 5. 重点字：同批别整片雷同 ----------
    print("\n【重点字】")
    kwsets = [(P["name"], {kw_text(s) for s in P["shots"] if s.get("kw")}) for P in plans]
    for i in range(len(kwsets)):
        for j in range(i + 1, len(kwsets)):
            A, B = kwsets[i][1] - {""}, kwsets[j][1] - {""}
            if A and B and A == B:
                say(WARN, "%s 与 %s 的重点字完全相同 → 建议至少换 2 个" % (kwsets[i][0], kwsets[j][0]))
    if not any(True for _ in []):
        say(OK, "重点字无整片雷同")

    # ---------- 结论 ----------
    print("\n" + "=" * 68)
    if fails:
        print("%s FAIL %d 项 / %s %d 项 → 这批不能发，先整改" % (FAIL, len(fails), WARN.strip(), len(warns)))
        return 1
    print("%s PASS（%s %d 项建议）" % (OK, WARN.strip(), len(warns)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
