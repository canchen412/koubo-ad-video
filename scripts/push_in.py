# -*- coding: utf-8 -*-
"""分段推镜：把静图做成「外景 → 中景 → 主体特写」的多段推进镜头。

为什么要有这个脚本（2026-11-09 老板）：
  「要加一点镜头推动……先是外景，然后推进到中景，中景再推进到他的脸部
    或者物体的一个主体大的地方。」
  现有 still_to_clip.py 只有 zoom_in(1.00→1.14)、匀速、中心固定 ——
  推完几乎看不出来，等于买了一张静图。

  这里做真推镜：路径由关键帧定义（缩放 + 取景中心 + 进度），段与段速度不同
  （外景段慢、落到主体段快），落幅自动 clamp，保证不出画。

用法：
  python3 push_in.py --src 图.jpg --out 片.mp4 --dur 3.49 \\
      --path "1.00:0.50:0.50@0, 1.15:0.50:0.46@0.45, 1.42:0.43:0.34@1"

  --path 每段格式： zoom:cx:cy@进度
    zoom  1.0 起，越大越近
    cx/cy 取景中心（0~1 的画面比例），推近时中心往哪挪
    进度  0~1，必须首个是 0、末个是 1，中间递增

  不写 --path 时用默认三段「慢起—中段—收尾」。

设计要点：
  · 先放大到 2 倍分辨率再推（zoompan 的常见糊法就是直接在原图上推）；
  · 分段用 ffmpeg 表达式 if(lt(...)) 逐帧求值，线性插值，不改帧率；
  · 落幅 clamp：视窗越界时把中心拉回，避免出现黑边；
  · 输出与成片同规格（默认 1920x1080 / 30fps）。
"""
import argparse
import os
import subprocess
import sys

FF = os.environ.get("FFMPEG_BIN") or (
    "/Users/yourname/.local/bin/ffmpeg" if os.path.exists("/Users/yourname/.local/bin/ffmpeg") else "ffmpeg")
W, H, FPS = 1920, 1080, 30

DEFAULT_PATH = "1.00:0.50:0.50@0, 1.15:0.50:0.47@0.50, 1.38:0.46:0.40@1"


def parse_path(s):
    """→ [(zoom, cx, cy, p), ...]，已校验"""
    pts = []
    for seg in s.split(","):
        seg = seg.strip()
        if not seg:
            continue
        head, _, prog = seg.partition("@")
        vals = [float(x) for x in head.split(":")]
        if len(vals) != 3:
            raise SystemExit("路径段格式不对：%r（应为 zoom:cx:cy@进度）" % seg)
        z, cx, cy = vals
        p = float(prog) if prog else None
        pts.append([z, cx, cy, p])
    if len(pts) < 2:
        raise SystemExit("路径至少两段")
    if pts[0][3] is None:
        pts[0][3] = 0.0
    if pts[-1][3] is None:
        pts[-1][3] = 1.0
    last = -1.0
    for i, pt in enumerate(pts):
        if pt[3] is None:
            pt[3] = i / (len(pts) - 1)
        if pt[3] <= last:
            raise SystemExit("路径进度必须递增且首 0 末 1：%s" % s)
        last = pt[3]
    if abs(pts[0][3]) > 1e-6 or abs(pts[-1][3] - 1.0) > 1e-6:
        raise SystemExit("路径首段进度必须 0、末段必须是 1：%s" % s)
    return [tuple(p) for p in pts]


def seg_expr(pts, idx, n):
    """为第 idx 个分量（0=z 1=cx 2=cy）生成分段线性表达式。
    P = on/(n-1) ∈ [0,1]"""
    P = "(on/%.1f)" % (n - 1)
    vals = [(pt[3], pt[idx]) for pt in pts]
    expr = "%.5f" % vals[-1][1]
    for k in range(len(vals) - 2, -1, -1):
        p0, v0 = vals[k]
        p1, v1 = vals[k + 1]
        span = max(1e-6, p1 - p0)
        seg = "(%.5f+(%.5f)*(%s-%.5f)/%.5f)" % (v0, v1 - v0, P, p0, span)
        expr = "if(lt(%s,%.5f),%s,%s)" % (P, p1, seg, expr)
    return expr


def build(src, out, dur, path_str, w=W, h=H, fps=FPS, crf=16):
    if not os.path.exists(src):
        raise SystemExit("源图不存在：%s" % src)
    pts = parse_path(path_str)
    n = max(2, int(round(dur * fps)))

    z = seg_expr(pts, 0, n)
    cx = seg_expr(pts, 1, n)
    cy = seg_expr(pts, 2, n)

    # 先放大 2 倍再推，避免直接在原图上插值导致糊
    vf = (
        "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d," % (w * 2, h * 2, w * 2, h * 2)
        + "zoompan=z='%s':x='(iw-iw/zoom)*%s':y='(ih-ih/zoom)*%s'"
          ":d=%d:s=%dx%d:fps=%d," % (z, cx, cy, n, w, h, fps)
        + "format=yuv420p"
    )
    cmd = [FF, "-y", "-v", "error", "-loop", "1", "-t", "%.3f" % (dur + 0.3), "-i", src,
           "-vf", vf, "-frames:v", str(n), "-an",
           "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise SystemExit("推镜失败：%s\n%s" % (src, (r.stderr or "")[-1200:]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dur", type=float, default=3.0)
    ap.add_argument("--path", default=DEFAULT_PATH,
                    help="zoom:cx:cy@进度，逗号分隔，如 1.0:0.5:0.5@0,1.42:0.43:0.34@1")
    ap.add_argument("--w", type=int, default=W)
    ap.add_argument("--h", type=int, default=H)
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--print-expr", action="store_true")
    a = ap.parse_args()

    if a.print_expr:
        pts = parse_path(a.path)
        n = max(2, int(round(a.dur * a.fps)))
        print("z  =", seg_expr(pts, 0, n))
        print("cx =", seg_expr(pts, 1, n))
        print("cy =", seg_expr(pts, 2, n))
        return

    p = build(a.src, a.out, a.dur, a.path, a.w, a.h, a.fps, a.crf)
    print("→ %s" % p)
    sz = os.path.getsize(p) / 1024 / 1024
    print("  %.2fs @ %dx%d  %.1fMB" % (a.dur, a.w, a.h, sz))


if __name__ == "__main__":
    main()
