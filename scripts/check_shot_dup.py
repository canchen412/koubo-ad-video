#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""片内重复镜自检（2026-11-13 老板抓出 v1 油条摊连放两遍后新增）

跨片去重脚本 check_batch_dedup.py 只管「这一批不同片之间」，查不出**同一片里**
把同一个源片段的两个时长/裁切版连在一起用（2.8s 版 + 3.1s 版），观感就是一个镜头放两遍。

本脚本按「去掉时长/裁切后缀后的基名」聚类，同一簇在一片里出现 ≥2 次即 FAIL。

用法：
  python check_shot_dup.py v1.shot_map.json v2.shot_map.json ...
  python check_shot_dup.py "v1:v1.shot_map.json" "v2:v2.shot_map.json"
退出码：0 全过；1 有片内重复。
"""
import json
import os
import re
import sys

# 时长/裁切/速度类后缀：_冲镜定格2.8s / _匀速推2.7s / _4s / __1.5s / _带推近
SUFFIX = re.compile(
    r"(?:_?(?:冲镜定格|匀速推|冲镜|定格|带推近|慢推|快推)?"
    r"(?:_|__)?\d+(?:\.\d+)?s(?:版)?)"
    r"|(?:_?第?[一二三四五1-5]版)|(?:_?[AB]版)$"
)


def base_stem(path):
    name = os.path.splitext(os.path.basename(str(path)))[0]
    prev = None
    while prev != name:
        prev = name
        name = SUFFIX.sub("", name).rstrip("_ ")
    return name


def as_job(arg):
    if ":" in arg and not arg.endswith(".json"):
        name, path = arg.split(":", 1)
        return name, path
    if ":" in arg and arg.count(":") == 1:
        head, tail = arg.split(":", 1)
        if tail.endswith(".json"):
            return head, tail
    return os.path.splitext(os.path.basename(arg))[0], arg


def check(name, path):
    shots = json.load(open(path, encoding="utf-8"))
    groups = {}
    for i, s in enumerate(shots, 1):
        src = s.get("src", "")
        groups.setdefault(base_stem(src), []).append((i, os.path.basename(src)))
    bad = {k: v for k, v in groups.items() if len(v) >= 2}
    print(f"\n【{name}】共 {len(shots)} 镜")
    if bad:
        for k, v in bad.items():
            idx = "、".join(f"镜{i}({f})" for i, f in v)
            print(f"  ❌ 同一源片段用了 {len(v)} 次：{k} → {idx}")
    else:
        print("  ✅ 无片内同源重复")
    return not bad


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    ok = True
    for a in args:
        name, path = as_job(a)
        if not os.path.exists(path):
            print(f"  ⚠️  找不到 {path}")
            ok = False
            continue
        ok = check(name, path) and ok
    print("\n" + "=" * 60)
    print("结论：✅ PASS —— 片内无同源重复" if ok else "结论：❌ FAIL —— 有片内同源重复，换镜后再渲")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
