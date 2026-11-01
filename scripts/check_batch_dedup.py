# -*- coding: utf-8 -*-
"""同批多片去重体检（2026-10-29 灿爹拍板：一次出多条，禁判重禁违规）。

## 为什么需要它

单条片子的质量靠七道硬闸把关，但**一批片子彼此太像**是另一回事：
平台对「同一账号短期内批量上传高度相似内容」是按**批**判的，画面指纹（逐帧抽帧）、
音频指纹（BGM / 音色）、文本相似度、以及权重最高的**开头 3 秒**，任何一项撞了都会降权。
`dup_shot_check.py` 只管单条片内部重复，`asset_usage.py` 只管历史被用了几次，
**跨片这层一直是空的**，本脚本补这一层。

本脚本**只体检、不改文件、不生成图**。红了就去重生成图 / 换开头。

## 用法

    # 一条片一个 --job，格式 名字:config.json[:文案.txt]
    python3 check_batch_dedup.py \
        --job A:brand_a.json:texts/v1.txt \
        --job B:brand_b.json:texts/v2.txt \
        --job C:brand_c.json:texts/v3.txt

    # 开头形式想纳入比对时显式声明（不声明就只提示不判定）
    python3 check_batch_dedup.py --job ... --form A=轮播 --form B=标准 --form C=标准

    # 只要结论、不要逐条明细
    python3 check_batch_dedup.py --job ... --quiet

## 判定分级

- ❌ FAIL：必须整改，这批不能一起发（开头撞 / 素材跨片复用 / 首句撞 / 文案整体撞）
- ⚠️ WARN：建议整改（开头形式全同 / 近似同图 / 音频指纹同源 / 同系列构图跨片）
- ✅ PASS

阈值都放在文件顶部常量区，不同品类可以按需放宽，但**开头那两项不建议放宽**。
"""
import argparse
import hashlib
import json
import os
import re
import sys
from difflib import SequenceMatcher

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 pillow：python3 -m pip install pillow")

# ============================ 阈值 ============================
# dHash(16x16=256bit) 汉明距离：同图不同缩放通常 <10，不同图 >35。
NEAR_DUP_HAMMING = 12       # < 12 视为「近似同一张画面」
HDIFF_MIN = 12              # 开头镜两两距离 < 12 判 FAIL（开头撞）
OPEN_HEAD_SIM_MAX = 0.60    # 首句文案相似度上限，超过判 FAIL
CROSS_REUSE_MAX = 1         # 同一素材最多允许出现在几条片里（1=不许跨片）
CROSS_REUSE_RATIO = 0.15    # 两片之间共用的素材数 / 较少一方镜数，超过判 FAIL
TEXT_SIM_MAX = 0.55         # 全片文案相似度上限，超过判 FAIL
TEXT_SIM_WARN = 0.42        # 超过则 WARN

SENT_SPLIT = re.compile(r"[。！？!?；;\n]+")

FAIL_MARK, WARN_MARK, OK_MARK = "❌", "⚠️ ", "✅"


# ============================ 小工具 ============================
def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dhash(path, size=16):
    """16x16 差分哈希，抗缩放/轻微压缩，对构图变化敏感。返回 int 或 None。"""
    try:
        im = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    except Exception:
        return None
    px = im.tobytes()          # 比 getdata() 快且不触发 Pillow 14 的弃用警告
    bits = 0
    for y in range(size):
        row = y * (size + 1)
        for x in range(size):
            bits = (bits << 1) | (1 if px[row + x] > px[row + x + 1] else 0)
    return bits


def hamming(a, b):
    if a is None or b is None:
        return 999
    return bin(a ^ b).count("1")


def sentences(txt):
    return [s.strip() for s in SENT_SPLIT.split(txt) if s.strip()]


def sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


def ratio(a, b):
    """相似度百分比（用于文案）。"""
    return round(SequenceMatcher(None, a, b).ratio(), 3)


def _is_near_dup(name_a, name_b, cfg_a, cfg_b):
    """文件名「同系列」判定：去掉景别后缀后前 6 字相同 ⇒ 同构图系列。"""
    def stem(n):
        s = os.path.splitext(os.path.basename(n))[0]
        s = re.sub(r"^(产品|科普|对比|展示|餐食|收尾|开头|结尾)_", "", s)
        s = re.sub(r"_(近景|中景|全景|特写|远景|全身)$", "", s)
        return s
    sa, sb = stem(name_a), stem(name_b)
    return len(sa) >= 4 and len(sb) >= 4 and sa[:6] == sb[:6]


# ============================ 读入 ============================
class Job(object):
    def __init__(self, name, cfg_path, txt_path=None):
        self.name = name
        self.cfg_path = os.path.abspath(cfg_path)
        base = os.path.dirname(self.cfg_path)
        with open(self.cfg_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.shots = [os.path.abspath(p) if not os.path.isabs(p)
                      else p for p in self.cfg.get("shots", [])]
        self.shots = [p if os.path.exists(p) else os.path.join(base, os.path.basename(p))
                      for p in self.shots]
        self.brand = self.cfg.get("brand", "")
        self.product = self.cfg.get("product", "")
        self.bgm = self.cfg.get("bgm", "")
        self.ref_audio = self.cfg.get("ref_audio", "")
        self.cards_dir = self.cfg.get("cards_dir", "")
        self.text = ""
        self.sents = []
        if txt_path and os.path.exists(txt_path):
            with open(txt_path, encoding="utf-8") as f:
                self.text = f.read().strip()
            self.sents = sentences(self.text)
        self.hashes = [dhash(p) for p in self.shots]
        self.md5s = []
        for p in self.shots:
            try:
                self.md5s.append(md5_of(p))
            except Exception:
                self.md5s.append("")

    @property
    def head(self):
        return self.shots[0] if self.shots else ""

    @property
    def head_sent(self):
        return self.sents[0] if self.sents else ""

    def product_shot(self):
        """产品点名镜：首个提到 brand 的句子按比例映射到镜号（估）。"""
        if not self.sents or not self.shots:
            return None
        for i, s in enumerate(self.sents):
            if self.brand and self.brand in s:
                return max(0, min(len(self.shots) - 1,
                                  int(round(i / max(1, len(self.sents)) * len(self.shots)))))
        return None


# ============================ 体检 ============================
def run(jobs, forms=None, quiet=False):
    forms = forms or {}
    fails, warns, oks = [], [], []
    lines = []

    def say(s=""):
        lines.append(s)

    n = len(jobs)
    say("=" * 74)
    say("同批去重体检 · %d 条片：%s" % (n, " / ".join(j.name for j in jobs)))
    say("=" * 74)

    # ---------- ① 开头对比（权重最高） ----------
    say("")
    say("【① 开头对比】← 平台判重权重最高的一段，先看这里")
    heads_same_path, heads_same_md5 = [], []
    for i in range(n):
        for k in range(i + 1, n):
            a, b = jobs[i], jobs[k]
            if a.head and a.head == b.head:
                heads_same_path.append((a.name, b.name))
            elif a.md5s and b.md5s and a.md5s[0] and a.md5s[0] == b.md5s[0]:
                heads_same_md5.append((a.name, b.name))

    for j in jobs:
        say("  %-3s 镜1素材 %s" % (j.name, os.path.basename(j.head) or "(无)"))
    if heads_same_path or heads_same_md5:
        for a, b in heads_same_path + heads_same_md5:
            fails.append("%s 与 %s 的开头镜是同一张图" % (a, b))
        say("  %s 开头镜有重复（路径或 md5 相同）" % FAIL_MARK)
    else:
        say("  %s 开头镜素材各不相同" % OK_MARK)

    # 开头画面近似度
    if n >= 2:
        pairs = []
        for i in range(n):
            for k in range(i + 1, n):
                d = hamming(jobs[i].hashes[0], jobs[k].hashes[0])
                pairs.append((jobs[i].name, jobs[k].name, d))
        txt = "  ".join("%s-%s=%d" % (a, b, d) for a, b, d in pairs)
        bad = [p for p in pairs if p[2] < HDIFF_MIN]
        say("  镜1画面距离  %s   （< %d 视为同一幅画面）" % (txt, HDIFF_MIN))
        if bad:
            for a, b, d in bad:
                fails.append("%s 与 %s 开头画面几乎相同（距离 %d）" % (a, b, d))
        elif all(p[2] < HDIFF_MIN * 2 for p in pairs):
            warns.append("开头画面距离偏近（%s），建议再拉开场景/景别" %
                         "/".join(str(p[2]) for p in pairs))

    # 首句文案
    if all(j.sents for j in jobs):
        say("")
        for j in jobs:
            say("  %-3s 首句「%s」" % (j.name, j.head_sent[:26]))
        for i in range(n):
            for k in range(i + 1, n):
                r = ratio(jobs[i].head_sent, jobs[k].head_sent)
                if r >= OPEN_HEAD_SIM_MAX:
                    fails.append("%s 与 %s 的首句太像（相似度 %.2f）：「%s」vs「%s」"
                                 % (jobs[i].name, jobs[k].name, r,
                                    jobs[i].head_sent[:18], jobs[k].head_sent[:18]))
                elif r >= 0.42:
                    warns.append("%s 与 %s 首句偏像（%.2f），建议换钩子角度"
                                 % (jobs[i].name, jobs[k].name, r))
        say("  首句两两相似度  %s   （≥ %.2f 判撞）" % (
            "  ".join("%s-%s=%.2f" % (jobs[i].name, jobs[k].name,
                                      ratio(jobs[i].head_sent, jobs[k].head_sent))
                      for i in range(n) for k in range(i + 1, n)),
            OPEN_HEAD_SIM_MAX))

    # 开头形式
    if forms:
        vals = [forms.get(j.name, "") for j in jobs]
        say("  开头形式   %s" % "  ".join("%s=%s" % (j.name, v or "?")
                                         for j, v in zip(jobs, vals)))
        if len(set(v for v in vals if v)) == 1 and n >= 2:
            warns.append("同批 %d 条开头形式全是「%s」，建议至少一条换成另一种（轮播/标准交替）"
                         % (n, vals[0]))
    else:
        say("  开头形式   未声明（加 --form A=轮播 --form B=标准 纳入判定）")

    # ---------- ② 素材跨片复用 ----------
    say("")
    say("【② 素材跨片复用】← 同一张图出现在两条片里，就是最硬的重复证据")
    owner = {}
    reuse = []
    near_reuse = []
    for j in jobs:
        for idx, p in enumerate(j.shots):
            base = os.path.basename(p)
            for prev in owner.get(base, []):
                if prev[0] != j.name:
                    reuse.append((base, prev[0], j.name, idx))
            owner.setdefault(base, []).append((j.name, idx))
    if reuse:
        for base, na, nb, idx in reuse:
            fails.append("素材跨片复用：%s 同时用在 %s 和 %s（后者第 %d 镜）"
                         % (base, na, nb, idx + 1))
        say("  %s 发现 %d 处路径级跨片复用" % (FAIL_MARK, len(reuse)))
        for base, na, nb, idx in reuse:
            say("      %s  %s → %s(镜%d)" % (base, na, nb, idx + 1))
    else:
        say("  %s 无任何素材跨片复用（路径级）" % OK_MARK)

    # 近似同图（不同路径但画面一样）
    all_items = [(j.name, i, j.shots[i], j.hashes[i]) for j in jobs for i in range(len(j.shots))]
    for x in range(len(all_items)):
        for y in range(x + 1, len(all_items)):
            na, ia, pa, ha = all_items[x]
            nb, ib, pb, hb = all_items[y]
            if na == nb or os.path.basename(pa) == os.path.basename(pb):
                continue
            d = hamming(ha, hb)
            if d < NEAR_DUP_HAMMING:
                near_reuse.append((os.path.basename(pa), na, ia, os.path.basename(pb), nb, ib, d))
    if near_reuse:
        for pa, na, ia, pb, nb, ib, d in near_reuse:
            warns.append("近似同图跨片：%s(%s镜%d) ≈ %s(%s镜%d) 距离 %d"
                         % (pa, na, ia + 1, pb, nb, ib + 1, d))
        say("  %s 有 %d 对「换了个文件名但画面几乎一样」" % (WARN_MARK, len(near_reuse)))
        for pa, na, ia, pb, nb, ib, d in near_reuse:
            say("      %s(镜%d) ≈ %s(镜%d)  距离%d" % (na, ia + 1, nb, ib + 1, d))
    elif not reuse:
        pass

    # 按段统计（科普段 / 产品段）
    say("")
    say("【③ 分段装载】")
    for j in jobs:
        ps = j.product_shot()
        tot = len(j.shots)
        if not j.sents:
            say("  %-3s 共 %d 镜（未传文案，跳过分段；补 :texts/vN.txt 即可）" % (j.name, tot))
        elif ps is None:
            say("  %-3s 共 %d 镜（文案里没出现 brand「%s」，请确认 cfg.brand 是否写对）"
                % (j.name, tot, j.brand or "(空)"))
        else:
            say("  %-3s 共 %d 镜：科普段 镜1~%d，产品段 镜%d~%d"
                % (j.name, tot, max(0, ps), ps + 1, tot))
    # 同段位跨片复用（更细的提示）
    seg_hits = []
    for i in range(n):
        for k in range(i + 1, n):
            a, b = jobs[i], jobs[k]
            shared = set(os.path.basename(p) for p in a.shots) & \
                     set(os.path.basename(p) for p in b.shots)
            if shared:
                smaller = min(len(a.shots), len(b.shots))
                if len(shared) / max(1, smaller) > CROSS_REUSE_RATIO:
                    fails.append("%s 与 %s 共用 %d/%d 个素材（超 %.0f%%）"
                                 % (a.name, b.name, len(shared), smaller,
                                    CROSS_REUSE_RATIO * 100))
                seg_hits.append((a.name, b.name, len(shared), smaller))
    if seg_hits:
        for a, b, s, m in seg_hits:
            say("  %s %s↔%s 共用 %d/%d 张" % (WARN_MARK, a, b, s, m))

    # ---------- ④ 文案整体 ----------
    if all(j.text for j in jobs):
        say("")
        say("【④ 全片文案相似度】")
        for i in range(n):
            for k in range(i + 1, n):
                r = ratio(jobs[i].text, jobs[k].text)
                mark = FAIL_MARK if r >= TEXT_SIM_MAX else (WARN_MARK if r >= TEXT_SIM_WARN else OK_MARK)
                say("  %s %s↔%s = %.2f" % (mark, jobs[i].name, jobs[k].name, r))
                if r >= TEXT_SIM_MAX:
                    fails.append("文案整体太像：%s↔%s = %.2f（≥ %.2f）"
                                 % (jobs[i].name, jobs[k].name, r, TEXT_SIM_MAX))
                elif r >= TEXT_SIM_WARN:
                    warns.append("文案偏像：%s↔%s = %.2f，建议换论证角度"
                                 % (jobs[i].name, jobs[k].name, r))

    # ---------- ⑤ 音频指纹（只提示，不擅自改） ----------
    say("")
    say("【⑤ 音频指纹】← 只提示，改不改你定（同一 BGM + 同一音色本身就是重复信号）")
    for field, label in (("bgm", "BGM"), ("ref_audio", "配音音色")):
        vals = {}
        for j in jobs:
            v = getattr(j, field, "")
            if v:
                vals.setdefault(os.path.basename(v), []).append(j.name)
        if len(vals) == 1 and n >= 2:
            only = list(vals)[0]
            warns.append("同批 %d 条全用同一个%s「%s」" % (n, label, only))
            say("  %s %s 全同：%s（%s）" % (WARN_MARK, label, only,
                                          "/".join(vals[only])))
        elif vals:
            say("  %s %s：%s" % (OK_MARK, label,
                                 "；".join("%s→%s" % (k, ",".join(v)) for k, v in vals.items())))

    # 卡片目录
    cds = {}
    for j in jobs:
        if j.cards_dir:
            cds.setdefault(os.path.basename(j.cards_dir), []).append(j.name)
    if len(cds) == 1 and n >= 2:
        warns.append("同批全用同一个卡片目录「%s」，卷播卡池建议每批换" % list(cds)[0])

    # ---------- 结论 ----------
    say("")
    say("=" * 74)
    if fails:
        say("结论：%s FAIL — %d 项必须整改，这批先别发" % (FAIL_MARK, len(fails)))
        for i, f in enumerate(fails, 1):
            say("   %d. %s" % (i, f))
    elif warns:
        say("结论：%s PASS（%d 项建议整改）" % (OK_MARK, len(warns)))
        for i, w in enumerate(warns, 1):
            say("   %d. %s" % (i, w))
    else:
        say("结论：%s PASS — 无跨片重复，可以发" % OK_MARK)
    say("=" * 74)

    if quiet and fails:
        print("\n".join(lines[-len(fails) - 4:]))
    else:
        print("\n".join(lines))
    return 0 if not fails else 2


def parse_form(pairs):
    out = {}
    for p in pairs or []:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main():
    ap = argparse.ArgumentParser(
        description="同批多片去重体检（跨片素材复用 / 开头撞车 / 文案相似度 / 音频指纹）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python3 check_batch_dedup.py --job A:brand_a.json:texts/v1.txt "
               "--job B:brand_b.json:texts/v2.txt")
    ap.add_argument("--job", action="append", required=True,
                    metavar="NAME:CONFIG[:TEXT]",
                    help="一条片，可重复传入")
    ap.add_argument("--form", action="append", metavar="NAME=轮播|标准",
                    help="开头形式，可重复传入")
    ap.add_argument("--quiet", action="store_true", help="只打结论")
    a = ap.parse_args()

    jobs = []
    for raw in a.job:
        parts = raw.split(":")
        # 兼容 Windows 盘符与含冒号路径：从右往左找 .json
        idx = next((i for i, p in enumerate(parts) if p.lower().endswith(".json")), 1)
        name = ":".join(parts[:idx])
        cfg = parts[idx]
        txt = ":".join(parts[idx + 1:]) or None
        if not os.path.exists(cfg):
            sys.exit("找不到 config：%s" % cfg)
        jobs.append(Job(name, cfg, txt))

    if len(jobs) < 2:
        print("只有一条片，无需跨片去重（单条重复请用 dup_shot_check.py）")
        return 0
    return run(jobs, parse_form(a.form), a.quiet)


if __name__ == "__main__":
    sys.exit(main())
