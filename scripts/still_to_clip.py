# -*- coding: utf-8 -*-
"""静图 → 镜头（Ken Burns 缓推/缓移）。

为什么要有这个脚本（2026-11-07 老板）：
  「科普段有很多的文案和图片视频，它没有含义匹配不上……我有很多新图的」。
  图库里语义最贴的素材常常只有**静图**（双角色搭讪、梳妆收拾、抱蔬果篮…），
  而硬闸 0b 规定「产品点名镜之前一镜都不许用静图」⇒ 好图被挡在门外，
  只能退而求其次拿一条语义勉强对得上的视频凑。

  老板自己就是这么干的（原话：「我很多图片都转了视频的」）。
  这里把这件事脚本化：任意静图 → 2s 1080p 缓推镜头，可直接写进 shot_map 当 imgvid。

用法：
  python3 scripts/still_to_clip.py <静图> [<静图> ...] [--dur 2.0] [--motion zoom_in|zoom_out|pan_l|pan_r]
  python3 scripts/still_to_clip.py --list-cache          # 看已转好的
  输出默认落在 <静图所在目录>/_clips/<图名>__<motion>_<dur>s.mp4（跟随素材盘，跨项目复用）

设计要点：
  · zoompan 用「先放大到 4K 再推」避免推近时糊；
  · 一律 h264_videotoolbox（8GB 机器软编太慢）；
  · 产物按 (源文件 mtime + 参数) 做缓存，重复调用 0.0x 秒返回。
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

FF = os.environ.get("FFMPEG_BIN") or (
    "/Users/yourname/.local/bin/ffmpeg" if os.path.exists("/Users/yourname/.local/bin/ffmpeg") else "ffmpeg")
FFPROBE = FF.replace("ffmpeg", "ffprobe")
W, H, FPS = 1920, 1080, 30

# motion 参数：(起始缩放, 结束缩放, 起始cx, 结束cx, 起始cy, 结束cy)
MOTIONS = {
    "zoom_in":  (1.00, 1.14, 0.50, 0.50, 0.50, 0.50),
    "zoom_out": (1.14, 1.00, 0.50, 0.50, 0.50, 0.50),
    "pan_l":    (1.10, 1.10, 0.56, 0.44, 0.50, 0.50),
    "pan_r":    (1.10, 1.10, 0.44, 0.56, 0.50, 0.50),
    "pan_up":   (1.10, 1.10, 0.50, 0.50, 0.56, 0.44),
}


def probe_size(p):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "csv=p=0", p],
                         capture_output=True, text=True).stdout.strip()
    try:
        w, h = out.split(",")[:2]
        return int(w), int(h)
    except Exception:
        return 0, 0


def cache_key(src, motion, dur):
    st = os.stat(src)
    raw = "%s|%d|%.1f|%s|%.2f|%dx%d" % (os.path.abspath(src), st.st_size, st.st_mtime, motion, dur, W, H)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def out_path(src, motion, dur):
    d = os.path.join(os.path.dirname(os.path.abspath(src)), "_clips")
    os.makedirs(d, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(d, "%s__%s_%gs_%s.mp4" % (base, motion, dur, cache_key(src, motion, dur)))


def build(src, motion="zoom_in", dur=2.0, force=False, zoom=1.0, cx=0.5):
    if not os.path.exists(src):
        raise SystemExit("源图不存在：%s" % src)
    dst = out_path(src, motion, dur) if zoom == 1.0 and cx == 0.5 else \
        out_path(src, "%s_z%.2f_x%.2f" % (motion, zoom, cx), dur)
    if os.path.exists(dst) and not force and os.path.getsize(dst) > 8000:
        return dst
    z0, z1, cx0, cx1, cy0, cy1 = MOTIONS[motion]
    # zoom/cx 是「取景修正」：白瓶/杂物在边上时把画面推近一点、往一侧偏一点，把它们挤出去
    z0, z1 = z0 * zoom, z1 * zoom
    cx0 = min(1.0, max(0.0, cx0 * cx / 0.5)) if cx != 0.5 else cx0
    cx1 = min(1.0, max(0.0, cx1 * cx / 0.5)) if cx != 0.5 else cx1
    n = max(2, int(round(dur * FPS)))
    # 先等比放大铺满 1920x1080（裁切不拉伸），再 zoompan 推
    vf = (
        "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d," % (W * 2, H * 2, W * 2, H * 2)
        + "zoompan=z='%.4f+(%.4f)*on/%d':x='(iw-iw/zoom)*(%.3f+(%.3f)*on/%d)':"
          "y='(ih-ih/zoom)*(%.3f+(%.3f)*on/%d)':d=%d:s=%dx%d:fps=%d,"
        % (z0, z1 - z0, n, cx0, cx1 - cx0, n, cy0, cy1 - cy0, n, n, W, H, FPS)
        + "format=yuv420p"
    )
    cmd = [FF, "-y", "-v", "error", "-loop", "1", "-t", "%.3f" % (dur + 0.2), "-i", src,
           "-vf", vf, "-frames:v", str(n), "-an",
           "-c:v", "h264_videotoolbox", "-q:v", "62", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst):
        # videotoolbox 不可用时退软编
        cmd[cmd.index("h264_videotoolbox")] = "libx264"
        cmd[cmd.index("-q:v")] = "-crf"
        cmd[cmd.index("-q:v") + 1] = "20"
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("转镜头失败：%s\n%s" % (src, (r.stderr or "")[-800:]))
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srcs", nargs="*")
    ap.add_argument("--dur", type=float, default=2.0)
    ap.add_argument("--motion", default="zoom_in", choices=sorted(MOTIONS))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--zoom", type=float, default=1.0, help="整体再推近（>1 会裁掉四边，用于挤掉边上杂物）")
    ap.add_argument("--cx", type=float, default=0.5, help="取景中心 x（<0.5 往左偏、>0.5 往右偏）")
    ap.add_argument("--list-cache", action="store_true")
    ap.add_argument("--json", action="store_true", help="输出 JSON，便于喂给 shot_map")
    a = ap.parse_args()

    if a.list_cache:
        root = os.environ.get("KOU_SPRITE_LIB", "/Volumes/素材库/广告视频/分镜图库")
        n = 0
        for dp, _, fs in os.walk(root):
            if os.path.basename(dp) != "_clips":
                continue
            for f in fs:
                if f.endswith(".mp4"):
                    print(os.path.join(dp, f))
                    n += 1
        print("共 %d 条" % n)
        return

    if not a.srcs:
        ap.print_help()
        return
    res = []
    for s in a.srcs:
        p = build(s, a.motion, a.dur, a.force, a.zoom, a.cx)
        res.append(p)
        print("→ %s" % p)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
