# -*- coding: utf-8 -*-
"""短素材缺口闸门（check_gap_fill.py）—— 2026-11-07 老板立规则时配套。

为什么要这个脚本（2026-11-07 老板）：
  他先说「2s 素材填不满分镜就末帧急推」，紧接着收窄：「差 0.3 秒、差零点几秒的，
  整体做一个慢放，这样就看不出来了，又能保证视频是动态的。」
  ⇒ 规则写进 SKILL.md 了。但**规则写在文档里 ≠ 执行时会被记得**——
  当晚第一次执行就手滑：明明 `fit_shot_duration.py` 早就能慢放（11-06 定的），
  我却直接上了新写的推镜脚本，白推一次。

  所以补这道闸：渲染前扫一遍 shot_map，任何「素材比镜短」的镜都点名，
  告诉你是该慢放还是该推镜。有未处理缺口就 exit 1，逼着先处理再渲。

用法：
  python3 scripts/check_gap_fill.py --work <工程根>          # 扫 pipeline/v1 v2 v3
  python3 scripts/check_gap_fill.py --work <工程根> --only v3
  python3 scripts/check_gap_fill.py --pipeline <工程根>/pipeline/v3

退出码：0 全部填满 ｜ 1 有未处理缺口 ｜ 4 环境/输入问题

判定（与 SKILL.md §一之二 两级规则一一对应）：
  缺口 ≤ 0.05s            → OK（1 帧以内，pipeline 自己补得掉）
  0.05 < 缺口 ≤ 0.55s     → **慢放**：fit_shot_duration.py --target <镜长> --no-interp
  缺口 > 0.55s（speed<0.78）→ **末帧急推**：tail_push.py --dur <镜长> --zoom 2.0~2.4
"""
import argparse
import glob
import json
import os
import subprocess
import sys

FFPROBE = os.environ.get("FFPROBE_BIN") or (
    "/Users/yourname/.local/bin/ffprobe" if os.path.exists("/Users/yourname/.local/bin/ffprobe") else "ffprobe")

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")
OK_GAP = 0.05      # 1.5 帧，pipeline 的 tpad 补得掉
SLOW_MAX = 0.55    # 超过这个缺口就别慢放了，改推镜


def probe_dur(p):
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", p], capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def check_one(ver_dir):
    v = os.path.basename(ver_dir.rstrip("/"))
    smap = os.path.join(ver_dir, v + ".shot_map.json")
    bounds = os.path.join(ver_dir, "audio", "shot_bounds.json")
    if not (os.path.exists(smap) and os.path.exists(bounds)):
        return None
    shots = json.load(open(smap, encoding="utf-8"))
    bs = json.load(open(bounds, encoding="utf-8"))
    rows, bad = [], 0
    for i, sh in enumerate(shots):
        if i >= len(bs):
            break
        src = sh["src"] if isinstance(sh, dict) else sh
        if not str(src).lower().endswith(VIDEO_EXT):
            continue                     # 静图不参与（静图由 img 分支自己处理运动）
        dur = bs[i][1] - bs[i][0]
        L = probe_dur(src)
        if L <= 0:
            rows.append((v, i + 1, dur, L, None, "读不到时长"))
            continue
        gap = dur - L
        speed = L / dur if dur > 0 else 9
        if gap <= OK_GAP:
            advice = "OK"
        elif gap <= SLOW_MAX:
            advice = "慢放 speed %.2f" % speed
            bad += 1
        else:
            advice = "推镜（speed %.2f 太慢）" % speed
            bad += 1
        rows.append((v, i + 1, dur, L, gap, advice))
    return rows, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=None, help="工程根（下面有 pipeline/v*）")
    ap.add_argument("--pipeline", default=None, help="单个版本目录（…/pipeline/v3）")
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()

    dirs = []
    if a.pipeline:
        dirs = [a.pipeline]
    elif a.work:
        for d in sorted(glob.glob(os.path.join(a.work, "pipeline", "*"))):
            if os.path.isdir(d) and (not a.only or os.path.basename(d) in a.only):
                dirs.append(d)
    if not dirs:
        print("[FAIL] 没找到 pipeline/*：%s" % (a.work or a.pipeline), file=sys.stderr)
        sys.exit(4)

    total_bad = 0
    for d in dirs:
        res = check_one(d)
        if not res:
            continue
        rows, bad = res
        total_bad += bad
        print("══ %s（%d 个视频镜）" % (os.path.basename(d), len(rows)))
        for v, n, dur, L, gap, advice in rows:
            mark = "✅" if advice == "OK" else "❌"
            g = "—" if gap is None else "%+.2fs" % gap
            print("  %s 镜%02d  镜长%.2f  素材%.2f  缺口%s  %s"
                  % (mark, n, dur, L, g, advice))

    print()
    if total_bad == 0:
        print("════ 全部镜已填满（≥97% 素材覆盖）✓")
        return 0
    print("════ %d 个镜有未处理缺口 ⇒ 先补再渲（慢放优先，推镜兜底）" % total_bad)
    return 1


if __name__ == "__main__":
    sys.exit(main())
