#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_banner_handoff.py — 卷播/封面接缝「碎片镜」硬闸门

【为什么有这个脚本】
2026-11-02 老板反馈：「卷播过后又闪了一下」。
根因：卷播（banner）切点算得比下一镜起点晚，把本该 1.48s 的「聚光灯全身」镜
挤成只剩 2 帧（0.07s）—— 肉眼就是一闪。
这类残帧不会触发任何现有质检（无黑帧、无卡帧、字幕正常、响度正常），
只有把成片按切点切开量间隔才看得见。

【判据】
成片里任意两个相邻切点之间（= 一个镜的可见时长）< --min-visible（默认 0.30s）
⇒ 判为碎片镜，exit 1。
片头 --head-guard 内不参与判定（封面段本身可能很短）。

【为什么默认只看前 8 秒】
这条规则只管「封面→卷播→第一镜」的接缝。全片扫会误报：
科普段/情绪段的**画面内闪烁、闪光、粒子爆点**同样会被 scene 检测当切点
（261102 实测 14.5~16.6s 连续 12 个 0.167s 假切点，全是镜内闪效）。
要看别处就用 --window 指定。默认 --window 0,8。
窗口外的疑似碎片只提示、不判 FAIL。

【用法】
  python check_banner_handoff.py --video 成片.mp4
  python check_banner_handoff.py --video 成片.mp4 --window 0,10 --min-visible 0.25

通过 → 打印切点表 + PASS，exit 0
不通过 → 打印碎片时刻 + 建议补法，exit 1
"""
import argparse
import re
import subprocess
import sys

FFMPEG = "/Users/yourname/.local/bin/ffmpeg"


def scene_cuts(video, threshold):
    """返回成片里所有场景切换时刻（秒）"""
    cmd = [FFMPEG, "-hide_banner", "-nostats", "-i", video,
           "-vf", f"select='gt(scene,{threshold})',showinfo",
           "-f", "null", "-"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        subprocess.run(["which", "ffmpeg"], check=False)
        p = subprocess.run(["ffmpeg"] + cmd[1:], capture_output=True, text=True, timeout=900)
    txt = (p.stderr or "") + (p.stdout or "")
    ts = [round(float(m), 3) for m in re.findall(r"pts_time:([0-9.]+)", txt)]
    return sorted(set(ts))


def duration(video):
    try:
        out = subprocess.run([FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "error",
                              "-show_entries", "format=duration", "-of", "csv=p=0", video],
                             capture_output=True, text=True, timeout=120).stdout.strip()
        return float(out)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--min-visible", type=float, default=0.30,
                    help="单镜最小可见时长（秒），低于此判碎片，默认 0.30")
    ap.add_argument("--scene", type=float, default=0.28, help="场景检测阈值，默认 0.28")
    ap.add_argument("--head-guard", type=float, default=0.40,
                    help="片头保护秒数，此前的切点不参与判定")
    ap.add_argument("--window", default="0,8",
                    help="判定窗口 start,end（秒），默认 0,8 只看接缝区；窗口外只提示")
    a = ap.parse_args()

    try:
        w0, w1 = [float(x) for x in a.window.split(",")]
    except Exception:
        print(f"  ❌ --window 格式应为 start,end，收到 {a.window}")
        return 2

    cuts = scene_cuts(a.video, a.scene)
    dur = duration(a.video)

    print(f"=== check_banner_handoff · {a.video.split('/')[-1]} ===")
    print(f"  场景切点 {len(cuts)} 个：{[round(c, 2) for c in cuts[:14]]}"
          + (" …" if len(cuts) > 14 else ""))
    print(f"  判定窗口 {w0}~{w1}s ／ 碎片阈值 <{a.min_visible}s")
    if dur:
        print(f"  成片时长 {dur:.2f}s")

    if len(cuts) < 2:
        print("  ⚠️ 切点少于 2 个，无法判定（片子是不是全静止？）")
        return 0

    bad, soft = [], []
    for i in range(len(cuts) - 1):
        seg = cuts[i + 1] - cuts[i]
        if cuts[i] < a.head_guard:
            continue
        if seg >= a.min_visible:
            continue
        item = (round(cuts[i], 3), round(cuts[i + 1], 3), round(seg, 3))
        (bad if w0 <= cuts[i] <= w1 else soft).append(item)

    # 末镜（最后一个切点到片尾）
    if dur and 0.01 < dur - cuts[-1] < a.min_visible:
        item = (round(cuts[-1], 3), round(dur, 3), round(dur - cuts[-1], 3))
        (bad if w0 <= cuts[-1] <= w1 else soft).append(item)

    if soft:
        print("\n  ℹ️ 窗口外疑似碎片（多为镜内闪效，仅供参考、不判废）：")
        for s, e, d in soft[:6]:
            print(f"     {s}s → {e}s  仅 {d}s")
        if len(soft) > 6:
            print(f"     …另 {len(soft)-6} 处")

    if bad:
        print("\n  ❌ 发现碎片镜（卷播/封面接缝吃镜）：")
        for s, e, d in bad:
            print(f"     {s}s → {e}s  仅 {d}s（{round(d*30)} 帧）")
        print("\n  修法（不重渲整片）：")
        print("    把 [s, e] 剪掉，用前一镜末帧 freeze 补同等时长，音频整段不动：")
        print(f"    ffmpeg -i in.mp4 -filter_complex \\")
        print(f"      \"[0:v]trim=0:{bad[0][0]},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={bad[0][2]}[a];\"")
        print(f"      \"[0:v]trim={bad[0][1]},setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]\" \\")
        print(f"      -map \"[v]\" -map 0:a -c:a copy out.mp4")
        print("\n=== 结论: ❌ FAIL ===")
        return 1

    print("  ✅ 无碎片镜，卷播/封面接缝干净")
    print("\n=== 结论: ✅ PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
