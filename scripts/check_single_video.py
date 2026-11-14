# -*- coding: utf-8 -*-
"""出片后「一个版本只许留一个 mp4」闸门（2026-11-08 老板定）

老板原话：「以后我让你做视频你就只留两版就可以了，把以前的那些旧的工程文件就可以删了，
不然我搞不清是哪一个。」

起因：261108 燕麦两条片，工程里留了 6 个 mp4
（minimal.mp4 无音轨裸画面 / final.mp4 混音后 / final_deliver.mp4 重编交付，各 2 份），
他打开目录分不清哪个是成片。

判据（任一不满足 exit 1）：
  1. 每个「版本目录」下 mp4 数量 <= 1
  2. 保留下来的 mp4 文件名不许是无信息名：final / minimal / out / tmp / bak / deliver
     （必须带品名或版本标识）
  3. 全工程 mp4 总数 <= 预期条数（默认 = 版本目录个数）

用法：
  python3 check_single_video.py --work <工程根>            # 预期条数 = 一层子目录个数
  python3 check_single_video.py --work <工程根> --n 2      # 明确预期两条
  python3 check_single_video.py --work <工程根> --list     # 只列现状不判（清理前看账用）
"""
import os
import sys
import argparse

BAD_NAMES = ("final", "minimal", "out", "tmp", "bak", "deliver", "copy", "test")
SKIP_DIRS = {"_归档", ".git", "__pycache__", ".workbuddy"}


def walk_mp4(root):
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.lower().endswith(".mp4"):
                p = os.path.join(dirpath, fn)
                hits.append((p, os.path.getsize(p)))
    return hits


def version_dir(root, path):
    """返回 mp4 所属的「版本目录」——工程根下第一层子目录名（没有则 '根'）。"""
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    return parts[0] if len(parts) > 1 else "根"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="工程根目录")
    ap.add_argument("--n", type=int, default=0, help="预期条数，0 = 按版本目录个数")
    ap.add_argument("--list", action="store_true", help="只列现状，不判定")
    a = ap.parse_args()

    root = os.path.abspath(a.work)
    if not os.path.isdir(root):
        print(f"❌ 工程目录不存在：{root}")
        return 2

    hits = walk_mp4(root)
    by_ver = {}
    for p, sz in hits:
        by_ver.setdefault(version_dir(root, p), []).append((p, sz))

    print(f"工程：{root}")
    print(f"mp4 共 {len(hits)} 个 / 版本目录 {len(by_ver)} 个\n")
    for ver in sorted(by_ver):
        print(f"[{ver}]")
        for p, sz in sorted(by_ver[ver]):
            print(f"   {sz / 1048576:7.1f}MB  {os.path.relpath(p, root)}")
        print()

    if a.list:
        return 0

    fails = []
    for ver, items in sorted(by_ver.items()):
        if len(items) > 1:
            fails.append(f"[{ver}] 下有 {len(items)} 个 mp4，只许留 1 个成片"
                         f"（中间产物 minimal/final 出完即删）")
        for p, _ in items:
            stem = os.path.splitext(os.path.basename(p))[0].lower()
            for bad in BAD_NAMES:
                if stem == bad or stem.startswith(bad + "_") or stem.startswith(bad + "-"):
                    fails.append(f"[{ver}] 文件名无信息：{os.path.basename(p)}"
                                 f" → 改成 <品名>_<版本定位>_小绿人_v1.mp4")
                    break

    n = a.n or len(by_ver) or 1
    if len(hits) > n:
        fails.append(f"工程内 mp4 共 {len(hits)} 个 > 预期 {n} 条片")

    if fails:
        print("❌ FAIL")
        for f in fails:
            print("   -", f)
        print("\n清理命令（确认成片已进归档盘后再执行）：")
        print('   python3 -c "import os;[os.remove(p) for p in [...]]"')
        return 1

    print("✅ PASS：每个版本只剩一个带名成片")
    return 0


if __name__ == "__main__":
    sys.exit(main())
