#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配音听写回验（koubo-ad-video 技能）。

═══ 为什么要有这道闸门（2026-11-11 老板实测）═══

成片里一句「早上搭一杯咖啡，练完饿了撕两片，都不用开火动锅。」
被 CosyVoice 读成「……练完饿了撕，｜两片都不用开火动锅。」
老板的原话：「配音说成了……以后不要犯类似的错」。

根因不是切句、不是标点、不是合成参数 —— phrases.txt 一字不差，
逐句合成也是每句一次请求。**是这句话本身有真实语法歧义**：
「撕两片，都不用开火动锅」里的「两片」既是「撕」的宾语，
又能当「都不用开火动锅」的主语 —— 模型按主语句读了，于是把停顿
砸在「撕」后面。人靠上下文不会读错，机器靠句法就会读错。

CosyVoice 是**确定性**的（同文本同 seed 逐样本一致），重跑等于白跑；
唯一出路是**改这句文案**。所以要有一道闸门，在渲染前把「读错的位置」
自动抓出来，而不是等人耳朵发现。

═══ 判据 ═══

拿 whisper 对 vo.wav 做**独立听写**（不用我们的文本，避免自证），
把 whisper 的 segment 边界映射回原文下标，然后分两级：

  A 级（硬错，exit 5）：边界落在「距最近标点 1～3 字」的位置。
       = 短句被从中间切断，听感就是「撕｜两片」。必须改文案重配。
       （2026-09-24 前科「想要薄｜肌，肌酸怎么选」也是这一级）

  B 级（软错，只报告）：
       · 漏停 —— 原文标点处 whisper 没有边界（一口气读过去），
         如「…全麦粉，占比38.8%以上」整段无气口
       · 长距误停 —— 边界距最近标点 ≥4 字，多为主谓之间的自然韵律，
         如「每一百克蛋白质｜给到15.4克」，通常可接受

退出码：0=通过；5=有 A 级；6=只有 B 级；2=环境不可用

用法：
    python3 tts_hearback.py --wav proj/audio/vo.wav --phrases proj/phrases.txt
    python3 tts_hearback.py --wav ... --phrases ... --json report.json
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile

PUNCT = "，。、；：？！,.;:?!…—-～~　 "
WHISPER_BIN = "~/.workbuddy/models/whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = "~/.workbuddy/models/whisper.cpp/models/ggml-base.bin"

CN = "零一二三四五六七八九"
UNIT = ["", "十", "百", "千", "万"]


def _int2cn(n):
    """0-99999 的整数读法（口语式：15=十五，20=二十，105=一百零五）"""
    if n == 0:
        return "零"
    s, digits = "", []
    x = n
    while x > 0:
        digits.append(x % 10)
        x //= 10
    digits = digits[::-1]
    zero = False
    for i, d in enumerate(digits):
        pos = len(digits) - i - 1
        if d == 0:
            zero = True
            continue
        if zero and s:
            s += "零"
        zero = False
        s += CN[d] + UNIT[pos]
    # 十五 而不是 一十五
    if s.startswith("一十"):
        s = s[1:]
    return s


def num2cn(s):
    """把阿拉伯数字串（含小数点）转成中文读法，让原文和 ASR 两边长度可比。
    15.4→十五点四  2.8→二点八  0→零  30→三十  38.8→三十八点八"""
    def rep(m):
        t = m.group(0)
        if "." in t:
            a, b = t.split(".", 1)
            ai = int(a) if a else 0
            out = (_int2cn(ai) if ai else "零") + "点"
            out += "".join(CN[int(c)] if c.isdigit() else c for c in b)
            return out
        n = int(t)
        return _int2cn(n)
    return re.sub(r"\d+(?:\.\d+)?", rep, s)


def strip_all(s):
    """去标点 + 数字转中文，两边都过这一道才能逐字对齐"""
    return num2cn("".join(ch for ch in s if ch not in PUNCT))


def load_phrases(path):
    """返回 [(原句, 去标点正文, 标点边界下标集合)]

    ★ 下标必须建在「数字转中文之后」的坐标系上 —— 原文 `15.4` 是 4 个字符、
      转成「十五点四」是 5 个字，若标点位置按原字符数、正文按转换后数，
      两套坐标混用会错位 1 位，逗号处的正确边界会被误判成「距标点 2 字」。
    """
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            core, marks, i = "", [], 0
            while i < len(ln):
                ch = ln[i]
                m = re.match(r"\d+(?:\.\d+)?", ln[i:])
                if ch in PUNCT:
                    marks.append(len(core))
                    i += 1
                elif m:
                    piece = num2cn(m.group(0))
                    core += piece
                    i += len(m.group(0))
                else:
                    core += ch
                    i += 1
            bounds = {b for b in marks if 0 < b < len(core)}
            out.append((ln, core, bounds))
    return out


def run_whisper(wav, bin_path, model, lang="zh"):
    bin_path = os.path.expanduser(bin_path)
    model = os.path.expanduser(model)
    if not os.path.exists(bin_path):
        return None, "whisper 二进制不存在：%s" % bin_path
    if not os.path.exists(model):
        return None, "whisper 模型不存在：%s" % model
    tmpd = tempfile.mkdtemp(prefix="hearback_")
    of = os.path.join(tmpd, "asr")
    cmd = [bin_path, "-m", model, "-f", wav, "-l", lang, "-oj", "-of", of, "-np"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    jp = of + ".json"
    if r.returncode != 0 or not os.path.exists(jp):
        return None, "whisper 运行失败 rc=%s %s" % (r.returncode, (r.stderr or "")[-300:])
    d = json.load(open(jp, encoding="utf-8"))
    segs = []
    for t in d.get("transcription", []):
        txt = (t.get("text") or "").strip()
        if not txt:
            continue
        segs.append({
            "text": txt,
            "from": t.get("offsets", {}).get("from", 0) / 1000.0,
            "to": t.get("offsets", {}).get("to", 0) / 1000.0,
        })
    return segs, None


def map_asr_to_ref(asr_core, ref_core):
    """把 asr 串的下标映射到 ref 下标：返回 list，长度 = len(asr_core)+1。
    mapped[i] = asr 第 i 个字之后、对应 ref 的哪个下标（尽力而为）。"""
    sm = difflib.SequenceMatcher(a=ref_core, b=asr_core, autojunk=False)
    mapped = [None] * (len(asr_core) + 1)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        span = j2 - j1
        for k in range(span + 1):
            pos = j1 + k
            if span == 0:
                mapped[pos] = i1
            else:
                mapped[pos] = i1 + round(k * (i2 - i1) / span)
    # 补空值
    for i in range(len(mapped)):
        if mapped[i] is None:
            mapped[i] = mapped[i - 1] if i > 0 else 0
    return mapped


def nearest_bound(dist_to_punct):
    return min(dist_to_punct) if dist_to_punct else 999


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--phrases", required=True)
    ap.add_argument("--whisper", default=WHISPER_BIN)
    ap.add_argument("--model", default=WHISPER_MODEL)
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--json", default="")
    ap.add_argument("--soft", action="store_true", help="B 级也当失败（exit 6 变 5）")
    a = ap.parse_args()

    if not os.path.exists(a.wav):
        print("✗ 找不到音频：%s" % a.wav)
        return 2
    sents = load_phrases(a.phrases)
    if not sents:
        print("✗ phrases 为空：%s" % a.phrases)
        return 2

    segs, err = run_whisper(a.wav, a.whisper, a.model, a.lang)
    if err:
        print("✗ %s" % err)
        print("  → 没有 whisper 时本闸门不可用，改为人工听一遍全片再交付")
        return 2

    ref_core = "".join(c for _, c, _ in sents)
    asr_core = strip_all("".join(s["text"] for s in segs))
    mapped = map_asr_to_ref(asr_core, ref_core)

    # 每句在整串里的起点
    starts, k = [], 0
    for _, core, _ in sents:
        starts.append(k)
        k += len(core)
    all_bounds = set()
    for idx, (_, core, bs) in enumerate(sents):
        for b in bs:
            all_bounds.add(starts[idx] + b)
        # 行末也是句子分界（phrases 一行一句），必须当标点边界算，
        # 否则每两句之间都会被误判成「距标点 N 字的误停」
        if idx < len(sents) - 1:
            all_bounds.add(starts[idx] + len(core))

    def which_sent(pos):
        for i in range(len(sents) - 1, -1, -1):
            if pos >= starts[i]:
                return i
        return 0

    # whisper 分段边界（不在整串末尾的）
    seg_bounds, acc = [], 0
    for s_i, s in enumerate(segs[:-1]):
        acc += len(strip_all(s["text"]))
        if 0 < acc < len(asr_core):
            seg_bounds.append((acc, s))

    hard, soft = [], []
    hit_punct = set()
    for acc, s in seg_bounds:
        refpos = mapped[acc]
        if refpos in all_bounds:
            hit_punct.add(refpos)
            continue
        dist = min(abs(refpos - b) for b in all_bounds) if all_bounds else 999
        si = which_sent(refpos)
        rec = {
            "sent": si + 1,
            "ref_pos": refpos,
            "dist": dist,
            "at": s["from"],
            "before": ref_core[max(0, refpos - 4):refpos],
            "after": ref_core[refpos:refpos + 4],
            "line": sents[si][0],
            "asr": s["text"],
        }
        if 1 <= dist <= 3:
            hard.append(rec)
        elif dist >= 4:
            soft.append(rec)

    # 漏停：标点边界没被 whisper 认出来
    missing = []
    for idx, (ln, core, bs) in enumerate(sents):
        for b in sorted(bs):
            gp = starts[idx] + b
            if gp not in hit_punct:
                missing.append({
                    "sent": idx + 1,
                    "ref_pos": gp,
                    "line": ln,
                    "before": ref_core[max(0, gp - 5):gp],
                    "after": ref_core[gp:gp + 5],
                })

    print("═" * 68)
    print("配音听写回验 · %d 句 / whisper 切出 %d 段" % (len(sents), len(segs)))
    print("═" * 68)

    if hard:
        print("\n【A 级 · 短句被切断，必须改文案重配】%d 处" % len(hard))
        for r in hard:
            print("  第%d句  %.2fs  距标点%d字" % (r["sent"], r["at"], r["dist"]))
            print("    读出的是：「…%s】｜【%s…」" % (r["before"], r["after"]))
            print("    原句：%s" % r["line"])
    else:
        print("\n【A 级】无 —— 没有短句被从中间切断")

    if soft:
        print("\n【B 级 · 自然韵律，通常可接受】%d 处" % len(soft))
        for r in soft:
            print("  第%d句  %.2fs  距标点%d字 「…%s】｜【%s…」"
                  % (r["sent"], r["at"], r["dist"], r["before"], r["after"]))

    if missing:
        print("\n【B 级 · 标点处漏气口】%d 处" % len(missing))
        for r in missing:
            print("  第%d句 「…%s，%s…」一口气读过去了" % (r["sent"], r["before"], r["after"]))

    if a.json:
        json.dump({"hard": hard, "soft": soft, "missing_pause": missing,
                   "segments": segs}, open(a.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("\n报告：%s" % a.json)

    print()
    if hard:
        print("✗ 不合格：%d 处 A 级。改那一句的文案（消灭歧义），重配这一句。" % len(hard))
        return 5
    if a.soft and (soft or missing):
        print("✗ 按 --soft 判定不合格：B 级 %d 处。" % (len(soft) + len(missing)))
        return 5
    if soft or missing:
        print("○ 通过（B 级 %d 处，不阻断）" % (len(soft) + len(missing)))
        return 6
    print("✓ 通过：逐句断点全部落在标点上")
    return 0


if __name__ == "__main__":
    sys.exit(main())
