#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_publish_copy.py — 校验「发布文案.txt」首屏的发布用区块格式

老板 2026-11-11 定的格式（原话给的就是这一行）：
    1，练薄肌早饭还拿煎饼垫着？这吐司一百克蛋白15.4克，三箱四十出头#蛋白吐司 #练薄肌 #健身早餐

硬规则（少一条就 exit 1，不许静默通过）：
  R1 文件头就有「发布用」区块：序号起头，一行一条，多条往下排 1，2，3，
  R2 序号后面是中文逗号「，」（不是「.」「、」「)」）
  R3 一行内 = 标题 + 话题，**标题与第一个 # 之间不许有空格**，直接贴住
  R4 话题之间用一个空格分隔，话题数固定 3 个（铁律：只要最相关的 3 个）
  R5 前区块里不许出现【标题】【话题】这类分段小标题（老写法，看不清、不好复制）
  R6 标题字符数 8–60（太短没信息量、太长平台折叠）

用法：
  python3 check_publish_copy.py --file "/Volumes/素材库/广告视频/蛋白吐司/剑盾/261111/发布文案.txt"
  python3 check_publish_copy.py --text "1，标题#话题 #话题 #话题"      # 单行干跑
  exit 0 = 合规；exit 1 = 有违规（逐条打印行号 + 原因）
"""
import argparse
import re
import sys

# 发布用区块的结束标记：遇到「====」分隔线或【xx】小节标题就停
STOP = re.compile(r'^\s*(=|-{4,}|【)')
ITEM = re.compile(r'^(\d+)([，,、.)）])\s*(.+)$')
TAGS = re.compile(r'(#\S+(?:\s+#\S+)*)\s*$')
BANNED = ("【标题】", "【话题】", "【话题标签】", "标题：", "话题：")
TAG_N = 3
TITLE_MIN, TITLE_MAX = 8, 60


def check_block(lines):
    """lines: [(行号, 原文)]，返回 (条目数, errors)"""
    errors = []
    n = 0
    for no, raw in lines:
        s = raw.strip()
        if not s:
            continue
        if any(b in s for b in BANNED):
            errors.append(f"  L{no} 前区块出现老写法分段「{s[:16]}…」——"
                          f"要一行一条整串，不要【标题】【话题】")
            continue
        m = ITEM.match(s)
        if not m:
            errors.append(f"  L{no} 不是「序号＋中文逗号」起头：{s[:20]}…")
            continue
        n += 1
        idx, sep, body = m.group(1), m.group(2), m.group(3)
        if sep != "，":
            errors.append(f"  L{no} 第 {idx} 条：序号后是「{sep}」，要用中文逗号「，」")
        tm = TAGS.search(body)
        if not tm:
            errors.append(f"  L{no} 第 {idx} 条：行尾没找到 #话题，标题后必须紧跟话题串")
            continue
        tags = [t for t in tm.group(1).split() if t.startswith("#")]
        title = body[: tm.start()].rstrip()
        if body[tm.start() - 1 : tm.start()] == " ":
            errors.append(f"  L{no} 第 {idx} 条：标题与第一个 # 之间有空格，要直接贴住")
        if not title:
            errors.append(f"  L{no} 第 {idx} 条：话题前没有标题")
        elif not (TITLE_MIN <= len(title) <= TITLE_MAX):
            errors.append(f"  L{no} 第 {idx} 条：标题 {len(title)} 字，"
                          f"要求 {TITLE_MIN}–{TITLE_MAX} 字")
        if len(tags) != TAG_N:
            errors.append(f"  L{no} 第 {idx} 条：{len(tags)} 个话题，要求正好 {TAG_N} 个"
                          f"（{' '.join(tags)}）")
        if "  " in body:
            errors.append(f"  L{no} 第 {idx} 条：出现连续空格")
    return n, errors


def read_block(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if i > 1 and STOP.match(line) and not ITEM.match(line.strip()):
                break
            out.append((i, line.rstrip("\n")))
            if i > 12:                      # 前区块最多 12 行，再多就是没分段
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--text")
    a = ap.parse_args()

    if a.text:
        lines = [(1, a.text)]
        src = "(--text)"
    elif a.file:
        try:
            lines = read_block(a.file)
        except FileNotFoundError:
            print(f"✗ 找不到文件：{a.file}")
            return 1
        src = a.file
    else:
        ap.error("要么 --file，要么 --text")

    n, errors = check_block(lines)
    print(f"发布文案格式检查：{src}")
    if n == 0 and not errors:
        print("✗ 文件头没有「序号＋中文逗号」起头的发布用条目")
        print("  期望首行形如：1，<标题>#话题1 #话题2 #话题3")
        return 1
    for e in errors:
        print(e)
    if errors:
        print(f"✗ {n} 条里 {len(errors)} 处不合格")
        return 1
    print(f"✓ {n} 条全部合格（序号中文逗号 / 标题贴 # / 话题 {TAG_N} 个）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
