#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静图 → 「冲镜」片段（慢起 + 急推 + 定格），带可选音效。

为什么要有这个脚本（2026-11-11 老板）：
  原话：「科普段……把静态图可以做成动态的效果，就这个图片后面几帧就定格在
  包子油条那里，突然镜头拉近放大，快速的拉近放大这样」。
  still_to_clip.py 的 Ken Burns 是**匀速**缓推，做不出「先定住、再猛地怼上去」的
  冲击感——那种效果要靠「静止段 + 极短爆发段 + 定格段」三段式，ease 曲线在爆发段
  起步最快（ease_out_back），推到 Z1 还过冲 8% 再回落，像镜头怼到脸前撞一下。

  用它替换科普段里语义最贴但只有静图的那几镜（如"包子油条煎饼"→早餐摊）。
  实测成本 0 积分（纯本地逐帧），一镜 2~3 秒渲染 <2 秒。

用法：
  python3 scripts/still_punch.py <静图> --dur 3.07 --focus 0.42,0.755 --z1 2.1
  python3 scripts/still_punch.py <静图> --dur 3.07 --focus 0.42,0.755 --sfx
  # 输出默认 <静图目录>/_clips/<图名>__punch_<dur>s.mp4（跟随素材盘，跨项目复用）

参数怎么定：
  --dur    必须等于该镜在成片里的时长（build 日志的 trim=duration，或 assets 逆推）。
           **宁长勿短**：短了 build 会用 tpad 冻末帧硬撑，节奏被拉长且总长偏移。
  --focus  归一化焦点 x,y（0-1）。推近后框住谁就写谁；用 python3 -c "from PIL import Image;
           Image.open(p).size" 看原图尺寸，再按比例估算。避开人物手臂/杂物。
  --z1     终点倍率。1.9~2.2 是「怼到脸上」，1.6~1.7 更温和。>2.3 画质开始软。
  --hold   静止段秒数（默认 0.52）。这段是冲击力的来源，别低于 0.4。
  --push   爆发段秒数（默认 0.52）。0.34 = 极猛（略跳）；0.52 = 稳推；0.7 = 慢推。

音效（--sfx）：
  kw_riser（上升，-16dB）从 hold 段末尾起，落到窗口时一记 impact（-9dB）。
  做进片段里而不是让 pipeline 加，是为了和画面严格同帧——pipeline 的 sfx
  是按句子/转场触发的，对不上这种镜内时间点。
  ⇒ shot_map 里必须写 "ambient": true, "ambient_gain": 1.0，否则默认 0.14 会被压成垫音。
"""
import argparse
import hashlib
import os
import subprocess
import sys

from PIL import Image, ImageFilter

FF = os.environ.get("FFMPEG_BIN") or (
    "/Users/yourname/.local/bin/ffmpeg" if os.path.exists("/Users/yourname/.local/bin/ffmpeg") else "ffmpeg")
W, H, FPS = 1920, 1080, 30
SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")


def ease_out_back(p, s=1.5):
    """起步最快（猛地一下），末端过冲再轻微回落 —— 「怼到脸上撞一下」的手感。"""
    p -= 1.0
    return 1.0 + (s + 1.0) * p * p * p + s * p * p


def zoom_at(t, hold, push, z1, z_pre=1.03):
    if t <= hold:
        return 1.0 + (z_pre - 1.0) * (t / max(hold, 1e-6))
    if t >= hold + push:
        return z1
    p = (t - hold) / push
    return z_pre + (z1 - z_pre) * ease_out_back(p)


def cache_key(src, dur, focus, z1, hold, push):
    st = os.stat(src)
    raw = "%s|%d|%d|%.3f|%s|%.2f|%.2f|%.2f" % (
        os.path.abspath(src), st.st_size, st.st_mtime, dur, focus, z1, hold, push)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def out_path(src, dur, focus, z1, hold, push):
    d = os.path.join(os.path.dirname(os.path.abspath(src)), "_clips")
    os.makedirs(d, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(d, "%s__punch_%gs_%s.mp4" % (base, round(dur, 2),
                                                    cache_key(src, dur, focus, z1, hold, push)))


def render(src, dst, dur, fx, fy, z1, hold, push, super_scale=2):
    img = Image.open(src).convert("RGB")
    w0, h0 = img.size
    if super_scale > 1:                      # 母版放大再裁，杜绝推近时糊
        img = img.resize((w0 * super_scale, h0 * super_scale), Image.LANCZOS)
    Wm, Hm = img.size
    n = max(2, int(round(dur * FPS)))
    cx, cy = fx * Wm, fy * Hm

    cmd = [FF, "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H), "-r", str(FPS), "-i", "-",
           "-frames:v", str(n), "-an",
           "-c:v", "libx264", "-crf", "17", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            z = zoom_at(i / FPS, hold, push, z1)
            cw, ch = Wm / z, Hm / z
            left = min(max(cx - cw / 2.0, 0.0), Wm - cw)
            top = min(max(cy - ch / 2.0, 0.0), Hm - ch)
            fr = img.crop((int(round(left)), int(round(top)),
                           int(round(left + cw)), int(round(top + ch))))
            fr = fr.resize((W, H), Image.LANCZOS)
            fr = fr.filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=2))
            p.stdin.write(fr.tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode("utf-8", "ignore")
    if p.wait() != 0:
        raise SystemExit("逐帧编码失败：%s" % err[-800:])


def add_sfx(src, dst, hold, push, dur):
    """rising + impact 压进片段（与画面同帧），音量已配好，别再叠。"""
    riser = os.path.join(SFX_DIR, "kw_riser.wav")
    impact = os.path.join(SFX_DIR, "impact.wav")
    if not (os.path.exists(riser) and os.path.exists(impact)):
        print("  ! 音效池缺失，跳过音效", file=sys.stderr)
        return src
    r_ms = int((hold + 0.02) * 1000)
    i_ms = int((hold + push - 0.05) * 1000)
    fc = ("[1:a]volume=-16dB,adelay=%d|%d[r];"
          "[2:a]volume=-9dB,adelay=%d|%d[i];"
          "[r][i]amix=inputs=2:duration=longest:normalize=0,apad[a]" % (r_ms, r_ms, i_ms, i_ms))
    cmd = [FF, "-y", "-v", "error", "-i", src, "-i", riser, "-i", impact,
           "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           "-t", "%.4f" % dur, dst]
    if subprocess.run(cmd, capture_output=True).returncode != 0:
        print("  ! 音效合成失败，保留无声版", file=sys.stderr)
        return src
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--dur", type=float, required=True, help="该镜在成片里的时长（宁长勿短）")
    ap.add_argument("--focus", default="0.5,0.5", help="归一化焦点 x,y，推近后框住谁写谁")
    ap.add_argument("--z1", type=float, default=2.1, help="终点倍率，1.9~2.2 怼脸，>2.3 会软")
    ap.add_argument("--hold", type=float, default=0.52, help="静止段秒数，冲击力来源")
    ap.add_argument("--push", type=float, default=0.52, help="爆发段秒数，0.34 极猛 / 0.52 稳")
    ap.add_argument("--sfx", action="store_true", help="把 riser+impact 压进片段（shot_map 要配 ambient_gain 1.0）")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.src):
        raise SystemExit("源图不存在：%s" % a.src)
    fx, fy = [float(x) for x in a.focus.split(",")]
    dst = out_path(a.src, a.dur, a.focus, a.z1, a.hold, a.push)
    if os.path.exists(dst) and not a.force and os.path.getsize(dst) > 8000:
        print("→ %s（命中缓存）" % dst)
    else:
        # 带音效时先渲到 /tmp（自然过期，不在图库里留无声副本），再混音到 dst
        tmp = dst if not a.sfx else os.path.join(
            "/tmp", "punch_%s.mp4" % cache_key(a.src, a.dur, a.focus, a.z1, a.hold, a.push))
        render(a.src, tmp, a.dur, fx, fy, a.z1, a.hold, a.push)
        if a.sfx:
            dst = add_sfx(tmp, dst, a.hold, a.push, a.dur)
        print("→ %s" % dst)

    for t in (0.0, a.hold, a.hold + a.push * 0.5, a.hold + a.push, a.dur):
        print("   t=%.2fs zoom=%.3f" % (t, zoom_at(min(t, a.dur), a.hold, a.push, a.z1)))
    if a.json:
        import json
        print(json.dumps([dst], ensure_ascii=False))


if __name__ == "__main__":
    main()
