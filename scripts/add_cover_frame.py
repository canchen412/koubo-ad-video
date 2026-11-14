# -*- coding: utf-8 -*-
"""把 3:4 竖版封面接到成片第一帧（抖音/快手抓首帧当封面）。

背景：老板要求「封面不单独交一张图，直接放进视频第一帧，我发视频就行」。
     平台按 3:4 居中裁 16:9 首帧 ⇒ 中间 810×1080 必须正好是封面本体，
     左右两侧留什么不影响裁切，所以这里用「底图放大高斯模糊」填满两侧
     （比纯黑好看，且平台裁切时完全在裁切区之外）。

工序：cover 810×1080 居中 + 模糊底铺满 1920×1080，定格 dur 秒，
     然后与正片首尾相接；音频整体后移 dur 秒（话一开口仍与画面严格对齐）。

用法：
  python3 add_cover_frame.py --video 成片.mp4 --cover 封面.jpg \
      --out 带封面.mp4 [--dur 0.5] [--fill blur|black] [--crf 19]

退出码：0 成功 / 2 输入文件或尺寸不对
"""
import argparse
import os
import subprocess
import sys

W, H = 1920, 1080
COVER_W, COVER_H = 810, 1080          # 1080×1440 的 3:4 封面，等比缩到高 1080
FPS = 30


def probe(path):
    if not os.path.exists(path):
        sys.exit(f"[ERR] 找不到文件：{path}")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    try:
        w, h = [int(x) for x in out.split(",")[:2]]
    except Exception:
        sys.exit(f"[ERR] 读不出视频尺寸：{path} -> {out!r}")
    return w, h


def build(video, cover, out, dur, fill, crf, maxrate, audio_bitrate):
    bg = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},gblur=sigma=42,eq=brightness=-0.10:saturation=0.85[bgv]"
    ) if fill == "blur" else (
        f"color=c=black:s={W}x{H}:d=1[bgv]"
    )
    fg = f"[0:v]scale={COVER_W}:{COVER_H}:flags=lanczos[fgv]"
    flt = (
        f"{bg};{fg};"
        # trim 卡到 dur 秒：-loop 1 -t dur 会多送一帧（末帧正好落在 dur 上），
        # 不裁的话总帧数会多 1、容器时长多 0.033s
        f"[bgv][fgv]overlay=(W-w)/2:(H-h)/2,format=yuv420p,fps={FPS},"
        f"trim=duration={dur},setpts=PTS-STARTPTS[cv];"
        f"[1:v]fps={FPS},setsar=1,format=yuv420p[bv];"
        f"[cv][bv]concat=n=2:v=1:a=0[v];"
        # 音频后移 dur 秒，开口与画面保持原来的对齐关系
        f"[1:a]adelay={int(round(dur * 1000))}:all=1[a]"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-loop", "1", "-t", f"{dur}", "-i", cover,
        "-i", video,
        "-filter_complex", flt,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-maxrate", maxrate, "-bufsize", "12M",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-movflags", "+faststart", out,
    ]
    print("[run]", " ".join(cmd[:6]), "...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("[ERR] ffmpeg 失败：\n" + r.stderr[-1500:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="正片 mp4")
    ap.add_argument("--cover", required=True, help="3:4 竖版封面 jpg/png")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dur", type=float, default=0.5, help="封面停留秒数，默认 0.5")
    ap.add_argument("--fill", choices=["blur", "black"], default="blur",
                    help="3:4 两侧怎么填（默认 blur 模糊底）")
    ap.add_argument("--crf", type=int, default=19)
    ap.add_argument("--maxrate", default="6M")
    ap.add_argument("--abitrate", default="192k")
    a = ap.parse_args()

    w, h = probe(a.video)
    if (w, h) != (W, H):
        sys.exit(f"[ERR] 成片必须是 {W}x{H}，实际 {w}x{h}")
    from PIL import Image
    cw, ch = Image.open(a.cover).size
    if abs(cw / ch - 0.75) > 0.02:
        print(f"[WARN] 封面比例 {cw}x{ch} 不是 3:4，会等比缩到高 {COVER_H} 后居中，平台裁切可能带边")
    build(a.video, a.cover, a.out, a.dur, a.fill, a.crf, a.maxrate, a.abitrate)
    print(f"[ok] {a.out}")


if __name__ == "__main__":
    main()
