#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bg_rotate.py — 动态背景轮换器（2026-11-03 老板定：以后背景随机用上，一批多片背景不许一样）

## 为什么要它

`assets/bg_library` 有 24 个预设，但一直默认写死 `W7`，等于库白建。
老板 2026-11-03 原话：「**我的很多动态背景都可以用，以后随机用上**，
如果我一次给你几条文案，你做出来的视频……**背景也不一样**」。

纯 `random` 不行：连抽三次可能两次撞，而且会和前几天的片撞墙。
所以改成**「最久未用优先 + 同批互斥 + 历史记录」**：
挑的是「这一批里没用过、而且离上次使用最久」的那几个，平局才随机。

## 用法

    PY=/Users/yourname/.workbuddy/binaries/python/envs/default/bin/python
    SK=~/.workbuddy/skills/koubo-ad-video

    # 单条片：挑 1 个（最久未用）
    $PY $SK/scripts/bg_rotate.py pick --n 1

    # 一批 3 条：挑 3 个互不相同的
    $PY $SK/scripts/bg_rotate.py pick --n 3 --note "肌酸批次派 3 条"

    # 只要某一组（深底漫画墙 / 深底纯动效 / 浅纸）
    $PY $SK/scripts/bg_rotate.py pick --n 2 --group comic_dark

    # 出完片记一笔（pick 带了 --note 会自动记，手动补记用这个）
    $PY $SK/scripts/bg_rotate.py commit --presets W4,DA --note "..."

    # 看最近用了什么
    $PY $SK/scripts/bg_rotate.py history -n 12

    # 给脚本消费（plan 里直接用）
    $PY $SK/scripts/bg_rotate.py pick --n 3 --json      # ["W4","DA","W2"]

## 选完的预设**直接写进 plan.json 的 "bg" 字段**，不要写 "random"

`"bg": "random"` 在渲染时抽，抽完没人知道用了哪个、历史也记不上，
下一批必然撞墙。写成显式 preset 才是可复现、可查账的。

## 分组（详见 assets/bg_library/README.md）

    comic_dark   W1–W7  深底漫画分格墙（绿人压得住，带货片默认这一组）
    comic_light  P1–P5  浅纸漫画墙（绿人压不住，慎用）
    fx_dark      D0–DE  深底纯动效（无分格，适合强信息/强动效段）
    fx_light     L0–LE  浅底纯动效
    all          全部 24 个
"""
import argparse
import datetime
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "assets", "bg_library")
HIST = os.path.join(LIB, "_bg_使用历史.json")
KEEP_HISTORY = 60          # 只留最近 60 条记录，文件不会无限长

# 分组定义（与 bg_lib 的 PRESETS 一致；这里显式写死，避免 import numpy 依赖）
GROUPS = {
    "comic_dark": ["W1", "W2", "W3", "W4", "W5", "W6", "W7"],
    "comic_light": ["P1", "P2", "P3", "P4", "P5"],
    "fx_dark": ["D0", "DA", "DB", "DC", "DD", "DE"],
    "fx_light": ["L0", "LA", "LB", "LC", "LD", "LE"],
}
ALL = [p for g in GROUPS.values() for p in g]

# 默认组：深底漫画墙（带货片唯一推荐组；浅纸组绿人压不住）
DEFAULT_GROUP = "comic_dark"

# 例外：W7 是「默认款」，如果库里只有它被用烂了，允许它优先被挑回来
FAVORED = {"W7"}


def _load():
    if not os.path.exists(HIST):
        return {"records": []}
    try:
        with open(HIST, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d.get("records"), list):
            d["records"] = []
        return d
    except Exception:
        return {"records": []}


def _save(d):
    d["records"] = d["records"][-KEEP_HISTORY:]
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    tmp = HIST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HIST)


def _last_used(d):
    """preset -> 最后一次使用的序号（越大越近）。没出现过的返回 -1。"""
    out = {}
    for i, r in enumerate(d["records"]):
        p = r.get("preset")
        if p:
            out[p] = i
    return out


def pick(n, group=DEFAULT_GROUP, exclude=(), note=None, seed=None, commit=True):
    presets = ALL if group == "all" else GROUPS.get(group)
    if not presets:
        sys.exit("未知分组 %r，可选：%s, all" % (group, ", ".join(GROUPS)))
    d = _load()
    last = _last_used(d)
    pool = [p for p in presets if p not in set(exclude)]
    if len(pool) < n:
        sys.exit("组 %s 只有 %d 个可选（已排除 %d 个），要 %d 个不够"
                 % (group, len(pool), len(exclude), n))

    rng = random.Random(seed)
    # 排序键：先「从未用过」（-1 最优先），再按久远程度；同档内随机破平局
    jitter = {p: rng.random() for p in pool}
    pool.sort(key=lambda p: (last.get(p, -1), jitter[p]))

    chosen = pool[:n]
    # W7 若长时间未用，给它一点权重：仅当它在最久未用的前 n+2 名里时才考虑替换第 n 个
    if n == 1 and chosen and chosen[0] not in FAVORED:
        pass  # 保持「最久未用优先」，不硬塞 W7

    if commit:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        for p in chosen:
            d["records"].append({"preset": p, "date": stamp,
                                 "note": note or "", "group": group})
        _save(d)
    return chosen


def main():
    ap = argparse.ArgumentParser(description="动态背景轮换器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("pick", help="挑背景预设")
    p1.add_argument("--n", type=int, default=1, help="要几条互不相同的背景")
    p1.add_argument("--group", default=DEFAULT_GROUP,
                    help="comic_dark / comic_light / fx_dark / fx_light / all")
    p1.add_argument("--exclude", default="", help="逗号分隔，已有片用过的不再给")
    p1.add_argument("--note", default=None, help="这批是什么片（写进历史）")
    p1.add_argument("--seed", type=int, default=None, help="固定随机种子（复现用）")
    p1.add_argument("--json", action="store_true", help="只输出 JSON 数组")
    p1.add_argument("--no-commit", action="store_true", help="只试算、不写历史")

    p2 = sub.add_parser("commit", help="手动补记使用历史")
    p2.add_argument("--presets", required=True, help="逗号分隔，如 W4,DA")
    p2.add_argument("--note", default="")

    p3 = sub.add_parser("history", help="看最近用过什么")
    p3.add_argument("-n", type=int, default=12)

    a = ap.parse_args()

    if a.cmd == "pick":
        ex = [s.strip() for s in a.exclude.split(",") if s.strip()]
        got = pick(a.n, a.group, ex, a.note, a.seed, commit=not a.no_commit)
        if a.json:
            print(json.dumps(got, ensure_ascii=False))
        else:
            print("背景：" + "  ".join(got))
            if a.n > 1:
                print("同批互不相同；按顺序分给 %d 条片，plan.json 的 \"bg\" 直接写各自的值。" % a.n)
            if a.no_commit:
                print("（--no-commit：只是试算，没记进历史）")
            else:
                print("（已记入 %s）" % os.path.relpath(HIST, os.path.dirname(HERE)))
    elif a.cmd == "commit":
        ps = [s.strip() for s in a.presets.split(",") if s.strip()]
        d = _load()
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        for p in ps:
            d["records"].append({"preset": p, "date": stamp, "note": a.note})
        _save(d)
        print("已记：%s" % ", ".join(ps))
    else:
        d = _load()
        recs = d["records"][-a.n:]
        if not recs:
            print("（还没有记录）")
            return
        for r in recs:
            print("%s  %-3s  %s" % (r.get("date", ""), r.get("preset", "?"), r.get("note", "")))


if __name__ == "__main__":
    main()
