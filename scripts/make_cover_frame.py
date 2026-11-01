#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_cover_frame.py — 带货片封面帧生成器（2026-10-29 灿爹定式）

规则（见 references/cover_frame.md）：
  封面**必须取自分镜底图**，不许从成片截图（截图会带字幕 / 圆环 / 重点字动效）。
  取 3:4 竖幅窗口 → 放大到画布高 → **居中**贴在 16:9 画布上，左右纯黑填充
  → 作为视频第 0 帧停留 0.5s（15 帧 @30fps），音频整体后移同长。

用法：
  # 只出封面图（自动 3:4 居中裁切）
  python make_cover_frame.py --src 底图.png --out-dir ./cover

  # 指定裁切窗口（w:h:x:y，从底图左上角起算）
  python make_cover_frame.py --src 底图.png --rect 648:864:444:0 --out-dir ./cover

  # 出图 + 直接贴到成片（生成 <视频>_cover.mp4，交付用这个）
  python make_cover_frame.py --src 底图.png --video 成片.mp4 --out-dir ./cover --apply

输出：
  <out-dir>/封面_3x4.png        810x1080（精准 3:4，抖音手动指定封面用这个）
  <out-dir>/封面_3x4.jpg        810x1080 同上（体积小，上传用）
  <out-dir>/封面_16x9_居中.png  1920x1080（3:4 居中 + 左右纯黑，贴首帧用）
  <out-dir>/封面_参数.txt       裁切参数与自检数据（抄进「发布文案.txt」）

自检：脚本会打印首帧的中间区 / 左右黑边亮度，交付前对照 references/cover_frame.md 的判据。
"""
import argparse
import json
import os
import subprocess
import sys

FFMPEG = os.environ.get("FFMPEG_BIN", "/Users/mac/.local/bin/ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "/Users/mac/.local/bin/ffprobe")


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("命令失败: %s\n%s\n" % (" ".join(cmd), r.stderr[-1500:]))
        raise SystemExit(1)
    return r.stdout


def probe_size(path):
    out = sh([FFPROBE, "-v", "error", "-select_streams", "v:0",
              "-show_entries", "stream=width,height", "-of", "csv=p=0", path])
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def auto_rect(sw, sh, ratio=0.75):
    """在 sw×sh 里取最大 ratio（默认 3:4=0.75）窗口，居中。返回 (w,h,x,y)。"""
    src_ratio = sw / sh
    if src_ratio >= ratio:                 # 原图比 3:4 更宽 → 高度撑满，横向选窗
        ch = sh
        cw = int(round(sh * ratio))
        cw -= cw % 2
        cx = (sw - cw) // 2
        cy = 0
    else:                                  # 原图比 3:4 更窄 → 宽度撑满，纵向选窗
        cw = sw - (sw % 2)
        ch = int(round(sw / ratio))
        ch -= ch % 2
        cx = 0
        cy = (sh - ch) // 2
    return cw, ch, cx, cy


def build_cover(src, rect, canvas, out_34, out_169, ratio=0.75):
    """从底图生成 3:4 竖图与 16:9 居中图，返回实际使用的裁切参数。"""
    sw, shh = probe_size(src)
    if rect:
        cw, ch, cx, cy = [int(v) for v in rect.split(":")]
        cw -= cw % 2
        ch -= ch % 2
        if cw > sw or ch > shh or cx + cw > sw or cy + ch > shh:
            raise SystemExit("裁切窗口超出底图范围：底图 %dx%d，窗口 %d:%d:%d:%d"
                             % (sw, shh, cw, ch, cx, cy))
    else:
        cw, ch, cx, cy = auto_rect(sw, shh, ratio)

    W, H = canvas
    up = (H / float(ch))
    # 目标 3:4 尺寸：高度对齐画布高，宽度按 3:4 反算（保证平台裁 3:4 时严丝合缝）
    tw = int(round(H * ratio))
    tw -= tw % 2
    th = H
    pad_x = (W - tw) // 2

    sharp = ",unsharp=5:5:0.5:5:5:0" if up > 1.1 else ""   # 放大超 1.1 倍补锐
    vf34 = "crop=%d:%d:%d:%d,scale=%d:%d:flags=lanczos%s" % (cw, ch, cx, cy, tw, th, sharp)
    sh([FFMPEG, "-y", "-v", "error", "-i", src, "-vf", vf34, "-frames:v", "1", out_34])
    sh([FFMPEG, "-y", "-v", "error", "-f", "lavfi",
        "-i", "color=c=black:s=%dx%d" % (W, H), "-i", out_34,
        "-filter_complex", "[0:v][1:v]overlay=%d:0:shortest=1" % pad_x,
        "-frames:v", "1", out_169])
    return {
        "src": src, "src_size": [sw, shh],
        "rect": "crop=%d:%d:%d:%d" % (cw, ch, cx, cy),
        "rect_xywh": [cw, ch, cx, cy],
        "upscale": round(up, 3),
        "canvas": [W, H], "strip": [tw, th], "pad_x": pad_x,
        "black_side": pad_x,
    }


def luma_stats(png):
    """返回 (整帧均值, 中间 3:4 均值, 左黑边均值, 右黑边均值)。"""
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return None
    a = np.asarray(Image.open(png).convert("L"), dtype="float32")
    h, w = a.shape
    tw = int(round(h * 0.75))
    x0 = (w - tw) // 2
    return (round(float(a.mean()), 1), round(float(a[:, x0:x0 + tw].mean()), 1),
            round(float(a[:, :x0].mean()), 2), round(float(a[:, x0 + tw:].mean()), 2))


def apply_to_video(video, cover169, dur, out_path):
    """把封面贴成视频第 0 帧段（dur 秒），音频整体后移 dur，重编码一次。"""
    delay = int(round(dur * 1000))
    sh([FFMPEG, "-y", "-v", "error",
        "-loop", "1", "-t", "%.3f" % dur, "-framerate", "30", "-i", cover169,
        "-i", video,
        "-filter_complex",
        "[0:v]scale=1920:1080,fps=30,format=yuv420p,setsar=1[v0];"
        "[1:v]fps=30,format=yuv420p,setsar=1[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[vout];"
        "[1:a]adelay=%d|%d,apad[aout]" % (delay, delay),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", "-shortest", out_path])
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="分镜底图（不许用成片截图）")
    ap.add_argument("--rect", default=None, help="裁切窗口 w:h:x:y；不给则自动 3:4 居中")
    ap.add_argument("--canvas", default="1920x1080", help="画布尺寸，默认 1920x1080")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", default="封面")
    ap.add_argument("--video", default=None, help="要贴封面的成片")
    ap.add_argument("--dur", type=float, default=0.5, help="封面停留秒数，默认 0.5")
    ap.add_argument("--apply", action="store_true", help="出图后直接贴到 --video")
    a = ap.parse_args()

    W, H = [int(v) for v in a.canvas.lower().split("x")]
    os.makedirs(a.out_dir, exist_ok=True)
    o34 = os.path.join(a.out_dir, "%s_3x4.png" % a.name)
    o169 = os.path.join(a.out_dir, "%s_16x9_居中.png" % a.name)

    info = build_cover(a.src, a.rect, (W, H), o34, o169)
    sh([FFMPEG, "-y", "-v", "error", "-i", o34, "-q:v", "2",
        os.path.join(a.out_dir, "%s_3x4.jpg" % a.name)])

    lines = []
    lines.append("封面来源底图：%s（%d×%d）" % (os.path.basename(a.src),
                                          info["src_size"][0], info["src_size"][1]))
    lines.append("裁切参数：%s → 放大 %.3f× → 竖幅 %d×%d（3:4）" %
                 (info["rect"], info["upscale"], info["strip"][0], info["strip"][1]))
    lines.append("画布布局：%d×%d，竖幅居中 x=%d，左右各 %d 像素纯黑" %
                 (W, H, info["pad_x"], info["pad_x"]))
    st = luma_stats(o169)
    if st:
        lines.append("自检亮度：整帧 %.1f｜中间 3:4 %.1f｜左黑边 %.2f｜右黑边 %.2f" % st)
        ok = st[2] < 1.0 and st[3] < 1.0 and st[1] > 20
        lines.append("判据：中间区 >20 且两侧黑边 <1 → %s" % ("PASS" if ok else "FAIL"))
    lines.append("贴帧参数：第 0 帧起停留 %.2fs（%d 帧@30fps），音频 adelay=%dms" %
                 (a.dur, int(round(a.dur * 30)), int(round(a.dur * 1000))))

    if a.apply:
        if not a.video:
            raise SystemExit("--apply 需要 --video")
        out = os.path.join(a.out_dir, os.path.splitext(os.path.basename(a.video))[0] + "_cover.mp4")
        apply_to_video(a.video, o169, a.dur, out)
        lines.append("已贴成片：%s" % out)

    txt = "\n".join(lines) + "\n"
    with open(os.path.join(a.out_dir, "封面_参数.txt"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
