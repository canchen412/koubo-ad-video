#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_first_scan.py —— 出片第 0 步：先把图库里的「动态视频」摊开看
─────────────────────────────────────────────────────────────────────
★ 2026-10-30 灿爹拍板：「首先要检测视频」——新窗口照着文案出片时，
  一条视频都没用、全拿静图顶上，因为没人去扫视频库。
  本脚本把「扫」变成一条命令，输出是给人/模型目视的候选表，不是自动选片。

用法:
  python3 video_first_scan.py                      # 扫全部 IP 库（小绿人+小男孩）
  python3 video_first_scan.py --ip 小绿人           # 只扫小绿人
  python3 video_first_scan.py --kw "餐食,碳水,米饭"  # 按关键词筛
  python3 video_first_scan.py --text copy.txt      # 文案逐句 ↔ 视频文件名 命中提示
  python3 video_first_scan.py --json /tmp/vids.json # 机器可读清单（供 shot_map 用）

判读口径:
  · 时长 ≥ 2 段文案时长 → 同一素材可以「续接」跨两镜，不许硬切（见 transitions.md §8）
  · 16:9 才可直接当 imgvid（非 16:9 会被 build_ad_video 拉伸）
  · 带 aac 音轨的多数是 2026-10 之后新一批 AI 动态视频，是最容易被漏掉的一批
  · 文件名里的 `_AI动态` / `视频_` 只是线索，最终必须抽帧目视确认内容
"""
import argparse
import json
import os
import subprocess
import sys

LIB_ROOT = "/Volumes/陈灿会展/广告视频/分镜图库"
CACHE = os.path.expanduser("~/.workbuddy/skills/koubo-ad-video/.cache/video_probe.json")
IP_DIRS = ["小绿人", "小男孩"]
POOL_SUB = "视频素材"          # ★每个 IP 下唯一视频池；出片先看这里
VID_EXT = (".mp4", ".mov", ".m4v")


def probe(path, cache):
    """ffprobe 结果带缓存（path|size|mtime 做 key），二次扫描秒回。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = f"{path}|{st.st_size}|{int(st.st_mtime)}"
    if key in cache:
        return cache[key]
    try:
        out = subprocess.run(
            ["/Users/mac/.local/bin/ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=25).stdout
        j = json.loads(out or "{}")
    except Exception:
        return None
    dur = float(j.get("format", {}).get("duration") or 0)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    info = {"path": path, "dur": round(dur, 2), "w": w, "h": h,
            "ar": round(w / h, 3) if h else 0,
            "audio": a is not None, "fps": v.get("r_frame_rate", ""),
            "size_mb": round(st.st_size / 1048576, 1)}
    cache[key] = info
    return info


def walk_videos(ips, skip_underscore=True):
    """→ (池内文件, 池外文件)。2026-10-30 起每个 IP 下 `视频素材/` 是唯一视频池。"""
    pool, other = [], []
    for ip in ips:
        root = os.path.join(LIB_ROOT, ip)
        if not os.path.isdir(root):
            print(f"  ⚠ 缺目录 {root}", file=sys.stderr)
            continue
        pd = os.path.join(root, POOL_SUB)
        for dp, dns, fns in os.walk(root):
            if skip_underscore:
                dns[:] = [d for d in dns if not d.startswith("_")]
            in_pool = dp == pd or dp.startswith(pd + os.sep)
            for fn in fns:
                if fn.startswith("."):
                    continue
                if os.path.splitext(fn)[1].lower() in VID_EXT:
                    (pool if in_pool else other).append(os.path.join(dp, fn))
    return sorted(pool), sorted(other)


def ask_ok(info):
    """是否可当 imgvid：16:9 ±2%（构建器硬写 scale=2304:1296，非 16:9 会拉伸）"""
    return info and info["h"] and abs(info["ar"] - 16 / 9) < 0.02


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default="all", help="小绿人 / 小男孩 / all")
    ap.add_argument("--kw", default="", help="关键词，逗号分隔，匹配相对路径")
    ap.add_argument("--min-dur", type=float, default=0, help="只列 ≥ 该时长的视频")
    ap.add_argument("--text", default="", help="文案 txt：逐句 ↔ 视频名 命中提示")
    ap.add_argument("--json", default="", help="写出机器可读清单")
    ap.add_argument("--pool-only", action="store_true",
                    help="只看 <IP>/视频素材/ 池里的，不列池外散落的")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    ips = IP_DIRS if a.ip == "all" else [a.ip]
    cache = {}
    if os.path.exists(CACHE) and not a.no_cache:
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}

    pool_files, other_files = walk_videos(ips)
    if not pool_files and not other_files:
        print("✗ 一条视频都没扫到 —— 先确认外置盘挂载")
        return 1

    def load(fs):
        rs = [r for r in (probe(p, cache) for p in fs) if r]
        if a.min_dur:
            rs = [r for r in rs if r["dur"] >= a.min_dur]
        kws = [k.strip() for k in a.kw.split(",") if k.strip()]
        if kws:
            rs = [r for r in rs if any(k in r["path"] for k in kws)]
        return rs

    pool_rows = load(pool_files)
    other_rows = [] if a.pool_only else load(other_files)
    if a.pool_only:
        other_files = []
    rows = pool_rows + other_rows

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    try:
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

    def dump(title, arr):
        if not arr:
            return
        print(f"\n【{title}】{len(arr)} 条")
        print(f"  {'时长':>6}  {'分辨率':>10}  {'16:9':>4}  {'MB':>6}  路径")
        for r in arr:
            rel = r["path"].replace(LIB_ROOT + "/", "")
            ok = "✓" if ask_ok(r) else "✗"
            print(f"  {r['dur']:>6.2f}s {r['w']:>4}×{r['h']:<5}  {ok:>4}  {r['size_mb']:>6.1f}  {rel}")

    def split_audio(rs):
        rs = sorted(rs, key=lambda r: (not r["audio"], -r["dur"]))
        return [r for r in rs if r["audio"]], [r for r in rs if not r["audio"]]

    poolA, poolN = split_audio(pool_rows)
    print(f"扫描 {os.path.join(LIB_ROOT, '{%s}' % ','.join(ips))}/{POOL_SUB} "
          f"→ 池内 {len(pool_rows)} 条｜池外 {len(other_rows)} 条")
    dump("★ 视频素材池 · 带音轨（2026-10 后新一批 AI 动态，最容易被漏）", poolA)
    dump("★ 视频素材池 · 无音轨（早期 AI 动态 / 实拍）", poolN)

    if other_rows:
        oA, oN = split_audio(other_rows)
        print(f"\n[!] 池外散落 {len(other_rows)} 条 —— 没归进「{POOL_SUB}/」，建议拖进去")
        dump("池外 · 带音轨", oA)
        dump("池外 · 无音轨", oN)

    ok_n = sum(1 for r in rows if ask_ok(r))
    long_n = sum(1 for r in rows if r["dur"] >= 4)
    print(f"\n小结：池内 {len(pool_rows)} 条 / 池外 {len(other_rows)} 条｜"
          f"16:9 可用 {ok_n} 条｜≥4s 可跨两镜续接 {long_n} 条")

    # ── 文案逐句 ↔ 视频名 关键词命中（粗筛，只作候选，必须抽帧目视）──
    if a.text and os.path.exists(a.text):
        sents = [s.strip() for s in open(a.text, encoding="utf-8").read()
                 .replace("。", "。\n").replace("，", "，\n").split("\n") if s.strip()]
        names = [(r["path"].replace(LIB_ROOT + "/", ""), r) for r in rows]
        print("\n【文案逐句候选】（只按文件名命中，语义是否真的对得上必须抽帧目视）")
        for s in sents:
            core = [w for w in s.replace("，", " ").replace("。", " ").split() if len(w) >= 2]
            hit = []
            for nm, r in names:
                if any(w in nm for w in core):
                    hit.append(nm)
            if hit:
                print(f"  · {s[:28]}")
                for h in hit[:3]:
                    print(f"      → {h}")

    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n清单已写入 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
