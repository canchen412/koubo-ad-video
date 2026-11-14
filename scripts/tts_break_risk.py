#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配音断句风险前置扫描（koubo-ad-video 技能）。

═══ 为什么要有这个（2026-11-11 老板实测）═══

成片交付后老板指出：「早上搭一杯咖啡，练完饿了撕两片，都不用开火动锅。」
被配音读成「……练完饿了撕，｜两片都不用开火动锅。」

这不是切句错、不是标点错、不是合成参数错 —— phrases.txt 一字不差。
是这句话本身**有真实语法歧义**：
  「撕两片，都不用开火动锅」里的「两片」
  既能当「撕」的宾语（撕两片面包），
  又能当「都不用开火动锅」的主语（这两片都不用开火）。
CosyVoice 选了后者，于是把停顿砸在「撕」后面。人靠上下文不会读错，
机器靠句法就会读错。**这种句子必须改文案，不能靠重跑**
（CosyVoice 是确定性的，同文本重跑逐样本一模一样）。

同批还查出第二处：「每一百克蛋白质给到15.4克，脂肪压到2.8克。」
被读成「给到15.4克脂肪｜压到2.8克」—— 因为「15.4克脂肪」是合法短语，
模型把「脂肪」当成了「给到」的宾语。产品核心数据听错，比断句难听严重得多。

═══ 本脚本干什么 ═══

配音之前扫 phrases.txt，按三条规则把「会被读错」的句子挑出来，
给出台词级修改建议。比事后听写回验（tts_hearback.py）便宜得多 ——
回验要先把整片重新合成一遍才能发现问题。

规则（改完再过 tts_hearback 复核，两道一前一后）：
  R1 分句以**单字动词**收尾 → 模型极易在动词后断
        「练完饿了撕，两片……」→ 「撕」后断
  R2 分句是「动词+数量词」，下一分句以**副词**开头（都/也/就/才/还/又/全/再）
        → 数量词会被下一分句抢去当主语
        「撕两片，都不用开火动锅」→ 两片 = 都不用开火动锅的主语
  R3〔提示级〕分句以「数字+单位」收尾，下分句开头是**名词**
        → 名词会被吸进前一分句当定语
        「给到15.4克，脂肪压到2.8克」→ 读成「15.4克脂肪」

退出码：0=干净；5=有 R1/R2（必须改）；6=只有 R3（提示）

用法：
    python3 tts_break_risk.py --phrases proj/phrases.txt
"""
import argparse
import re
import sys

# 会单独出现在分句末尾、容易把后文吸过来的单字动词
VERB1 = set("撕掰切压抹泡冲拆拧开咬喝拿放堆煎炸蒸煮炒塞掰灌倒抖拌剁刮削")
# 与「数量词」抢主语的副词
ADV_START = set("都也才就还又全再")
# 常见量词与单位（判断「动词+数量词」结尾 / 「数字+单位」结尾）
UNIT = set("克毫克千焦元块包天个片箱袋罐瓶粒勺碗根条张斤两升毫升")
UNIT_MULTI = ["毫克", "千焦", "毫升"]


def split_clauses(line):
    """按逗号句号切成 [(子句, 后面跟的标点)]"""
    out, buf = [], ""
    for ch in line:
        if ch in "，。、；,.;":
            out.append((buf, ch))
            buf = ""
        else:
            buf += ch
    if buf:
        out.append((buf, ""))
    return [(a, b) for a, b in out if a]


def tail_is_verb1(cl):
    """子句是否以单字动词收尾（排除双字动词：撕开/切开…）"""
    if len(cl) < 1:
        return False
    if cl[-1] not in VERB1:
        return False
    # 双字动词结尾（撕开、切开、压到）不算
    if len(cl) >= 2 and cl[-2] in VERB1:
        return False
    return True


def tail_is_verb_num(cl):
    """子句是否以「动词 + 数量词」收尾，返回数量词或 None"""
    m = re.search(r"(.+?)([一二两三四五六七八九十百千\d]+)([%s])$" % "".join(UNIT), cl)
    if not m:
        return None
    head = m.group(1)
    # 数量词前面得有个动词性成分，且不能是「这那」等指示词
    if not head or head[-1] in "的这那该每":
        return None
    return m.group(2) + m.group(3)


def tail_is_num_unit(cl):
    """子句是否以「数字 + 物质计量单位」收尾。

    ★ 只认物质计量单位（克/毫克/千焦/毫升/升/斤/两/卡），不认个体量词
      （天/个/包/箱/片）。因为只有「15.4克」+名词才组装得成「15.4克脂肪」，
      而「30天」+「袋子」不成立 —— 限定后 R3 从假报成群降到只报真问题。
    """
    return bool(re.search(r"(\d+(?:\.\d+)?|[一二两三四五六七八九十百千]+)"
                          r"(毫克|千焦|毫升|克|升|斤|两|卡)$", cl))


def starts_with_adv(cl):
    return bool(cl) and cl[0] in ADV_START


def starts_with_noun(cl):
    """粗略判断下分句开头是不是名词性成分（不是副词/动词/连词）"""
    if not cl:
        return False
    first = cl[0]
    # 虚词 / 连词 / 介词开头都不算名词：模型不会把数量词和它们组合
    if first in ADV_START or first in "是在有把被给让从对向往那这而但可却只连因即虽并或如": 
        return False
    if first in VERB1:
        return False
    return True


def scan_line(line):
    hits = []
    cl = split_clauses(line)
    for i, (cur, punct) in enumerate(cl):
        nxt = cl[i + 1][0] if i + 1 < len(cl) else ""
        if punct not in "，,":      # 只在句内逗号处判，句号是自然断句
            continue
        if tail_is_verb1(cur):
            hits.append(("R1", cur, nxt,
                         "分句以单字动词「%s」收尾，模型容易在动词后断" % cur[-1],
                         "把单字动词换成双字，或在动词前加修饰语（如「随手撕」）"))
            continue
        vnum = tail_is_verb_num(cur)
        if vnum and starts_with_adv(nxt):
            hits.append(("R2", cur, nxt,
                         "「%s」会被下一分句的「%s」抢去当主语（语法歧义）"
                         % (vnum, nxt[0]),
                         "让下一分句不再是「数量词+副词」结构，"
                         "如把「都不用开火」改成「连火都不用开」"))
            continue
        if tail_is_num_unit(cur) and starts_with_noun(nxt):
            _m = re.search(r"((?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千]+)"
                           r"(?:毫克|千焦|毫升|克|升|斤|两|卡))$", cur)
            _tail = _m.group(1) if _m else cur[-4:]
            hits.append(("R3", cur, nxt,
                         "「%s」后接名词「%s」，模型会读成「%s%s」"
                         % (_tail, nxt[:3], _tail, nxt[:3]),
                         "在逗号后加一个不能与数量词组合的虚词（如「而」），"
                         "或把两个数据拆成两句"))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrases", required=True)
    ap.add_argument("--strict", action="store_true", help="R3 也算不合格")
    a = ap.parse_args()

    lines = [ln.strip() for ln in open(a.phrases, encoding="utf-8") if ln.strip()]
    if not lines:
        print("✗ phrases 为空")
        return 2

    hard, soft = [], []
    for idx, ln in enumerate(lines, 1):
        for h in scan_line(ln):
            (hard if h[0] in ("R1", "R2") else soft).append((idx, ln) + h)

    print("═" * 68)
    print("配音断句风险前置扫描 · %d 句" % len(lines))
    print("═" * 68)

    if hard:
        print("\n【必须改 · 模型会把停顿放错位置】%d 处" % len(hard))
        for idx, ln, rule, cur, nxt, why, fix in hard:
            print("\n  第%d句  %s" % (idx, rule))
            print("    原句：%s" % ln)
            print("    位置：「%s，%s」" % (cur, nxt))
            print("    原因：%s" % why)
            print("    改法：%s" % fix)
    else:
        print("\n【必须改】无 —— 没有会被读错断点的句子")

    if soft:
        print("\n【提示 · 可能把后一个词吸进前半句】%d 处" % len(soft))
        for idx, ln, rule, cur, nxt, why, fix in soft:
            print("\n  第%d句  %s" % (idx, rule))
            print("    原句：%s" % ln)
            print("    原因：%s" % why)
            print("    改法：%s" % fix)

    print()
    if hard:
        print("✗ 不合格：%d 处必须改。改完再合成，合成后跑 tts_hearback.py 复核。" % len(hard))
        return 5
    if a.strict and soft:
        print("✗ 按 --strict 判定不合格：R3 %d 处。" % len(soft))
        return 5
    if soft:
        print("○ 通过（R3 %d 处，建议顺手改掉）" % len(soft))
        return 6
    print("✓ 通过：没有断句风险句")
    return 0


if __name__ == "__main__":
    sys.exit(main())
