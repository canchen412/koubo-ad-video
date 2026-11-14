# -*- coding: utf-8 -*-
"""短素材补齐：末帧急推（tail push）。

为什么要有这个脚本（2026-11-07 老板）：
  原话：「有一个视频……它只做了一半的动态，然后另一半就是完全静止的在后面了。
  可以这个样子，如果以后这个两秒的视频填补不了两秒多的这个分镜的长度的话，
  可以在最后一帧停止，然后这个镜头做成往前推，比如说急往前推，推到女主的脸部那里，
  这样子看起来整个视频既有动态的效果，又后面又不至于很呆滞。」

  痛点：AI 动态素材普遍只有 2s（模型单段上限），而分镜常常 2.4~2.6s。
  旧做法是 tpad 克隆末帧 ⇒ 后半段完全静止，观感像卡住。

  新做法（本脚本）：前段正常播放 → 在动态最好的一帧**停住** → 对那一帧做急推
  （ease-in 幂曲线，越推越快），推到指定的主体（人脸/瓶身）上。
  「动 → 停 → 推」比「动 → 死」活得多，而且推镜本身就是天然转场。

用法：
  python3 scripts/tail_push.py <视频> --dur 2.45 --zoom 2.0 --cx 0.65 --cy 0.36
  python3 scripts/tail_push.py --pick <视频>      # 只打印时长诊断，不生成

参数语义：
  --dur   目标镜头时长（秒）。比源素材长才有意义；不传则自动取「源长 + 0.35」。
  --play  前段播放秒数。默认自动 = dur - push，push 取 clamp(dur*0.45, 1.0, 1.4)。
  --zoom  推镜终点倍率（1.8~2.4 是「急推」，1.3~1.5 是「缓推」）。
  --cx/--cy 终点希望**画面正中**对准的位置（0~1，直观坐标，内部自动换算成 zoompan 参数）。
  --ease  推镜节奏幂指数：1.0 匀速，1.35 默认（后半程发力），2.0 极急。

设计要点：
  · 推镜段的源帧取自 play 时刻那一帧（不一定是素材末帧）—— 保证与 A 段无缝，
    同时允许裁掉素材尾部本来就不动的部分（那部分留给推镜用）；
  · 先 2x 放大再 zoompan，z=2.0 时有效分辨率仍是 1080p，不糊；
  · 一条 filter_complex 只编码一次，2.5s 片约 1.5s 出片。
"""
import argparse
import hashlib
import json
import os
import subprocess

from PIL import Image

FF = os.environ.get("FFMPEG_BIN") or (
    "/Users/yourname/.local/bin/ffmpeg" if os.path.exists("/Users/yourname/.local/bin/ffmpeg") else "ffmpeg")
FFPROBE = FF.replace("ffmpeg", "ffprobe")
W, H, FPS = 1920, 1080, 30


def probe(p):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate:format=duration",
         "-of", "json", p], capture_output=True, text=True).stdout
    try:
        d = json.loads(out)
        st = d["streams"][0]
        num, den = st.get("r_frame_rate", "30/1").split("/")
        fps = float(num) / float(den or 1)
        return int(st["width"]), int(st["height"]), float(d["format"]["duration"]), fps
    except Exception:
        return 0, 0, 0.0, 30.0


def cache_key(src, dur, play, zoom, cx, cy, ease):
    st = os.stat(src)
    raw = "%s|%d|%.2f|%.3f|%.3f|%.3f|%.3f|%.3f|%.3f|%dx%d" % (
        os.path.abspath(src), st.st_size, st.st_mtime, dur, play, zoom, cx, cy, ease, W, H)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def out_path(src, dur, zoom, cx, cy, ease, play):
    d = os.path.join(os.path.dirname(os.path.abspath(src)), "_clips")
    os.makedirs(d, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(d, "%s__tailpush_%gs_z%.2f_x%.2f_y%.2f_%s.mp4" % (
        base, dur, zoom, cx, cy, cache_key(src, dur, play, zoom, cx, cy, ease)))


def build(src, dur=None, play=None, zoom=2.0, cx=0.65, cy=0.38, ease=1.35, force=False):
    if not os.path.exists(src):
        raise SystemExit("源视频不存在：%s" % src)
    sw, sh, L, sfps = probe(src)
    if L <= 0.2:
        raise SystemExit("源视频时长异常：%s" % L)

    if dur is None:
        dur = L + 0.35
    dur = round(float(dur), 3)

    # 推镜段至少 1.0s，前段至少 0.8s
    if play is None:
        push = min(max(dur * 0.45, 1.0), 1.4)
        push = min(push, max(0.8, dur - 0.8))
        play = dur - push
    play = round(min(float(play), L), 3)
    push = round(dur - play, 3)
    if push < 0.35:
        raise SystemExit("推镜段只剩 %.2fs，太短：请把 --dur 调大（源长 %.2fs）" % (push, L))

    dst = out_path(src, dur, zoom, cx, cy, ease, play)
    if os.path.exists(dst) and not force and os.path.getsize(dst) > 8000:
        return dst, {"cached": True, "dur": dur, "play": play, "push": push, "src_len": L}

    # 推镜段源帧：play 时刻的最后一帧（与 A 段严格接续）
    grab_t = max(0.0, play - 1.0 / max(sfps, 1))
    key = cache_key(src, dur, play, zoom, cx, cy, ease)
    tmp_png = "/tmp/_tailpush_src_%s.png" % key
    r = subprocess.run(
        [FF, "-y", "-v", "error", "-ss", "%.3f" % grab_t, "-i", src, "-frames:v", "1",
         "-vf", "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,scale=%d:%d:flags=lanczos"
                % (W * 2, H * 2, W * 2, H * 2, W * 2, H * 2),
         tmp_png], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp_png):
        raise SystemExit("抽帧失败：%s\n%s" % (src, (r.stderr or "")[-600:]))

    n1 = max(2, int(round(play * FPS)))
    n2 = max(2, int(round(push * FPS)))

    # ── B 段：PIL 逐帧合成推镜
    #   为什么不用 zoompan 的 x/y 表达式：实测 z 会变、中心却几乎不跟手
    #   （推到女主脸时人被挤到画面边缘），逐帧算 crop 窗口才精确可控。
    src_img = Image.open(tmp_png).convert("RGB")
    sw, sh = src_img.size
    seq_dir = "/tmp/_tailpush_seq_%s" % key
    os.makedirs(seq_dir, exist_ok=True)
    for i in range(n2):
        p = 0.0 if n2 <= 1 else (i / float(n2 - 1)) ** ease
        z = 1.0 + (zoom - 1.0) * p
        ccx = 0.5 + (cx - 0.5) * p
        ccy = 0.5 + (cy - 0.5) * p
        vw, vh = sw / z, sh / z
        left = min(max(0.0, ccx * sw - vw / 2.0), sw - vw)
        top = min(max(0.0, ccy * sh - vh / 2.0), sh - vh)
        box = (int(round(left)), int(round(top)),
               int(round(left + vw)), int(round(top + vh)))
        src_img.crop(box).resize((W, H), Image.LANCZOS).save(
            os.path.join(seq_dir, "f%04d.png" % i))

    a_mp4 = "/tmp/_tailpush_a_%s.mp4" % key
    b_mp4 = "/tmp/_tailpush_b_%s.mp4" % key
    enc = ["-c:v", "h264_videotoolbox", "-q:v", "62", "-pix_fmt", "yuv420p"]

    # A 段：原样播放 play 秒（统一到 1080p / 30fps）
    ra = subprocess.run(
        [FF, "-y", "-v", "error", "-i", src, "-t", "%.3f" % play, "-an",
         "-vf", "fps=%d,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
                "setsar=1,format=yuv420p" % (FPS, W, H, W, H),
         "-frames:v", str(n1)] + enc + [a_mp4], capture_output=True, text=True)
    if ra.returncode != 0:
        raise SystemExit("A 段失败：%s" % (ra.stderr or "")[-600:])

    # B 段：逐帧序列 → mp4
    rb = subprocess.run(
        [FF, "-y", "-v", "error", "-framerate", str(FPS),
         "-i", os.path.join(seq_dir, "f%04d.png"), "-frames:v", str(n2)] + enc + [b_mp4],
        capture_output=True, text=True)
    if rb.returncode != 0:
        raise SystemExit("B 段失败：%s" % (rb.stderr or "")[-600:])

    # A+B 拼接（重编一次，2.5s 片约 1s）
    cmd = [FF, "-y", "-v", "error", "-i", a_mp4, "-i", b_mp4,
           "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
           "-map", "[v]", "-an", "-frames:v", str(n1 + n2)] + enc + \
          ["-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        cmd[cmd.index("h264_videotoolbox")] = "libx264"
        cmd[cmd.index("-q:v")] = "-crf"
        cmd[cmd.index("-q:v") + 1] = "19"
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("末帧急推失败：%s\n%s" % (src, (r.stderr or "")[-900:]))

    try:
        os.remove(tmp_png)
    except OSError:
        pass
    return dst, {"cached": False, "dur": dur, "play": play, "push": push, "src_len": L,
                 "zoom": zoom, "cx": cx, "cy": cy, "ease": ease,
                 "frames": n1 + n2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srcs", nargs="*")
    ap.add_argument("--dur", type=float, default=None, help="目标镜头时长")
    ap.add_argument("--play", type=float, default=None, help="前段播放秒数")
    ap.add_argument("--zoom", type=float, default=2.0)
    ap.add_argument("--cx", type=float, default=0.65)
    ap.add_argument("--cy", type=float, default=0.38)
    ap.add_argument("--ease", type=float, default=1.35)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--pick", action="store_true", help="只诊断时长")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.srcs:
        ap.print_help()
        return
    res = []
    for s in a.srcs:
        if a.pick:
            sw, sh, L, fps = probe(s)
            print("%.2fs  %dx%d  %.2ffps  %s" % (L, sw, sh, fps, os.path.basename(s)))
            continue
        p, info = build(s, a.dur, a.play, a.zoom, a.cx, a.cy, a.ease, a.force)
        print("→ %s  (播 %.2fs + 推 %.2fs = %.2fs, 源 %.2fs)" % (
            p, info["play"], info["push"], info["dur"], info["src_len"]))
        res.append(p)
    if a.json and res:
        print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
