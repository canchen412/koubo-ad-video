#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fit_shot_duration.py — 2 秒母版「镜长适配」闸门（2026-11-06 老板拍板）

老板原话：「他的视频要求是两秒多到三秒的，你可以把我这个 2 秒的视频再缓速一下，拉长到 2 秒多就行了；
如果是只有一秒多的话，你就把它加速到一秒多，也可以作为分镜的。所以说这个 2 秒有很大的空间和作用。」

规则（与 references/libtv_生成通道.md 铁律〇之六 一一对应）：
  目标 1.3–2.0s → 加速  speed 1.0–1.55
  目标 2.0–2.6s → 慢放  speed 0.78–1.0
  目标 2.6–3.1s → 慢放 + minterpolate 光流补帧（否则 60 帧摊到 3s 只剩 20fps，顿挫）
  超窗（>3.1s / <1.3s）→ 拒绝执行，exit 2，提示按目标时长重出

输出永远是工作副本（默认 -an 无音），绝不覆盖原稿、绝不入库。

用法：
  python fit_shot_duration.py --src 原稿.mp4 --target 2.5
  python fit_shot_duration.py --src 原稿.mp4 --target 1.6 --out /tmp/a.mp4
  python fit_shot_duration.py --src 原稿.mp4 --target 2.5 --dry    # 只算不转

退出码：0 成功 ｜ 2 超窗（该重出）｜ 3 转完时长对不上 ｜ 4 环境/输入问题
"""
import argparse
import json
import os
import subprocess
import sys

FFMPEG = os.environ.get("FFMPEG_BIN") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE_BIN") or "ffprobe"

SPEED_MIN = 0.65   # 慢放上限（2.02s → 3.11s）
SPEED_MAX = 1.55   # 加速上限（2.02s → 1.30s）
INTERP_BELOW = 0.85  # speed 小于此值（目标 > 2.38s）必须补帧
TOL = 0.08         # 实际时长与目标允许偏差


def probe(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration",
         "-of", "json", path],
        capture_output=True, text=True)
    if out.returncode != 0:
        print(f"[FAIL] ffprobe 读不了：{path}", file=sys.stderr)
        sys.exit(4)
    d = json.loads(out.stdout)
    st = d["streams"][0]
    num, den = (st.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1)
    return {
        "dur": float(d["format"]["duration"]),
        "w": st.get("width"), "h": st.get("height"),
        "fps": round(fps, 3), "frames": st.get("nb_frames"),
    }


def main():
    ap = argparse.ArgumentParser(description="2 秒母版变速适配成片镜长（带窗口闸门）")
    ap.add_argument("--src", required=True, help="2 秒原稿 mp4")
    ap.add_argument("--target", required=True, type=float, help="目标镜长（秒），如 2.5 / 1.6")
    ap.add_argument("--out", default=None, help="输出路径，默认 <原名>_变速x<speed>_<target>s.mp4")
    ap.add_argument("--keep-audio", action="store_true", help="保留音轨（默认丢弃，成片用云端配音）")
    ap.add_argument("--dry", action="store_true", help="只算方案不转码")
    ap.add_argument("--no-interp", action="store_true",
                    help="禁用 minterpolate，改复制帧补（**轻度慢放 0.80–1.00 一律加这个**："
                         "光流在插画/3D 混合素材上容易糊边，还慢 5 倍；复制帧每 5 帧重复 1 帧，肉眼看不出来）")
    a = ap.parse_args()

    if not os.path.isfile(a.src):
        print(f"[FAIL] 文件不存在：{a.src}", file=sys.stderr)
        sys.exit(4)
    info = probe(a.src)
    src_dur = info["dur"]
    speed = src_dur / a.target

    print(f"源：{os.path.basename(a.src)}  {info['w']}x{info['h']} / {info['fps']}fps / "
          f"{src_dur:.3f}s / {info['frames']} 帧")
    print(f"目标：{a.target:.2f}s  ⇒ speed = {src_dur:.3f} / {a.target:.2f} = {speed:.3f}x")

    # ---- 闸门：窗口判断 ----
    if speed > SPEED_MAX or speed < SPEED_MIN:
        why = "太快（<1.3s，动作会像快进）" if speed > SPEED_MAX else "太慢（>3.1s，拖影/果冻）"
        print(f"\n[REJECT exit=2] {why}：speed {speed:.3f}x 超出 [{SPEED_MIN}, {SPEED_MAX}]")
        print(f"  ⇒ 不要硬拉。按目标时长 {a.target:.1f}s 用 Wan 2.7 直接重出"
              f"（Wan 2.7 支持 2–10s 连续），或改镜长到 "
              f"{src_dur/SPEED_MIN:.2f}–{src_dur/SPEED_MAX:.2f}s 之间。")
        sys.exit(2)

    need_interp = speed < INTERP_BELOW and not a.no_interp
    mode = "慢放+光流补帧" if need_interp else ("慢放" if speed < 1.0 else "加速")
    print(f"判定：{mode}　窗口内 ✅" + ("（speed<%.2f，必须 minterpolate）" % INTERP_BELOW if need_interp else ""))

    base = os.path.splitext(os.path.basename(a.src))[0]
    out = a.out or os.path.join(
        os.path.dirname(os.path.abspath(a.src)),
        f"{base}_变速x{speed:.2f}_{a.target:.2f}s.mp4")

    if a.dry:
        print(f"[DRY] 将输出 → {out}")
        return

    # ---- 转码 ----
    fps = int(round(info["fps"]))

    def build(extra=""):
        if need_interp:
            vf = (f"setpts=PTS/{speed:.6f},"
                  f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1")
        else:
            vf = f"setpts=PTS/{speed:.6f},fps={fps}"
        vf += extra
        cmd = [FFMPEG, "-y", "-v", "error", "-i", a.src,
               "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
        cmd += ["-map", "0:a?", "-c:a", "aac", "-b:a", "128k"] if a.keep_audio else ["-an"]
        cmd += ["-c:v", "libx264", "-crf", "17", "-preset", "medium",
                "-pix_fmt", "yuv420p", out]
        return cmd

    print("转码中……")
    r = subprocess.run(build(), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[FAIL exit=4] ffmpeg 失败：\n{r.stderr[-800:]}", file=sys.stderr)
        sys.exit(4)

    # ---- 补齐：minterpolate 会在尾部丢帧，差 >0.035s 时二次修（尾部冻帧 / 裁齐）----
    # tpad 每次会多出约 2 帧，所以按累积误差迭代，最多 3 轮，收敛到 ±1 帧内。
    got = probe(out)
    cum = 0.0
    for _ in range(3):
        err = a.target - got["dur"]
        if abs(err) <= 0.035:
            break
        if err > 0:
            cum += max(err - 0.02, 0.0)
            extra = f",tpad=stop_mode=clone:stop_duration={cum:.3f}"
            how = f"尾部冻帧 +{cum:.3f}s"
        else:
            extra = f",trim=duration={a.target:.3f},setpts=PTS-STARTPTS"
            how = f"裁掉多余 {-err:.3f}s"
        print(f"  时长修正：{got['dur']:.3f}s → 目标 {a.target:.2f}s（{how}）")
        r = subprocess.run(build(extra), capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[FAIL exit=4] ffmpeg 修正失败：\n{r.stderr[-800:]}", file=sys.stderr)
            sys.exit(4)
        got = probe(out)

    diff = abs(got["dur"] - a.target)
    print(f"输出：{out}")
    print(f"  实际 {got['dur']:.3f}s（目标 {a.target:.2f}s，差 {diff:.3f}s）"
          f" / {got['w']}x{got['h']} / {got['fps']}fps")
    if not a.keep_audio:
        print("  音轨：已丢弃（成片一律用云端配音）")
    if diff > TOL:
        print(f"[FAIL exit=3] 时长偏差 {diff:.3f}s > 容差 {TOL}s，检查源文件帧率/时长", file=sys.stderr)
        sys.exit(3)
    print("OK：工作副本，不入库（入库永远是 2 秒带音轨原稿）")


if __name__ == "__main__":
    main()
