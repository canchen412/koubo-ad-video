#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""i2v 动静闸门 —— 确认「该动的真动了、该静的真空了」。

背景：2026-11-13 镜5 三版实测证明，「写保持不动」会渲出一屋木偶；
而反过来，想静的元素又常常被模型重绘/漂移。这两件事肉眼都不好判断，
必须靠分区差分量化。判据见 references/i2v_提示词规范.md §二十。

用法
----
  # 只出九宫格报告，不判定（第一次看素材时用）
  check_i2v_motion.py --video gen/x.mp4 --grid

  # 带区域判定（推荐）
  check_i2v_motion.py --video gen/x.mp4 \
      --still 430,0,900,720 \          # 该静的区（人物），变化率必须 ≤ 10%
      --move  1000,0,1280,400 \        # 该动的区（挂钟），变化率必须 ≥ 25%
      --move  60,180,290,610           # 可多次

  --box 是 x0,y0,x1,y1（像素，基于视频原始分辨率）。

退出码
------
  0 = 全部达标
  1 = 有区域不达标（该动的没动 / 该静的动了）
  2 = 参数或文件错误
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

# 阈值（与 §二十 保持一致，改动请同步文档）
STILL_MAX = 10.0   # 静止区变化率上限 %
MOVE_MIN = 25.0    # 事件区变化率下限 %
DIFF_LEVEL = 25    # 单像素判定为"变了"的阈值（0-255）
EDGE_IOU_MIN = 0.45  # 静止区边缘 IoU 下限。实测：人物没动时 0.55~0.63，被重绘/位移时 <0.40


def find_ffmpeg():
    for c in (os.path.expanduser("~/.local/bin/ffmpeg"),
              "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"):
        if os.path.sep in c:
            if os.path.exists(c):
                return c
        elif shutil.which(c):
            return shutil.which(c)
    sys.exit("[错误] 找不到 ffmpeg")


def probe_duration(ffprobe, video):
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 2.02


def grab(ffmpeg, video, t, out_png):
    subprocess.run([ffmpeg, "-v", "error", "-ss", f"{t:.3f}", "-i", video,
                    "-frames:v", "1", "-y", out_png], check=False)
    return out_png if os.path.exists(out_png) else None


def grab_last(ffmpeg, video, out_png):
    """抽末帧。必须用 -sseof（-ss 0 抽的是首帧，等于自己跟自己比）。"""
    subprocess.run([ffmpeg, "-v", "error", "-sseof", "-0.08", "-i", video,
                    "-frames:v", "1", "-y", out_png], check=False)
    return out_png if os.path.exists(out_png) else None


def parse_box(s):
    try:
        v = [int(round(float(x))) for x in s.replace(" ", "").split(",")]
        if len(v) != 4:
            raise ValueError
        return v
    except Exception:
        sys.exit(f"[错误] --box 格式应为 x0,y0,x1,y1，收到：{s}")


def rate(diff, box):
    x0, y0, x1, y1 = box
    h, w = diff.shape
    x0, x1 = max(0, min(x0, w)), max(0, min(x1, w))
    y0, y1 = max(0, min(y0, h)), max(0, min(y1, h))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return float((diff[y0:y1, x0:x1] > DIFF_LEVEL).mean() * 100.0)


def edge_map(gray, pct=80):
    """Sobel 幅度二值化。边缘位置不随亮度变化移动，所以对「窗光扫过」这类强光变鲁棒。"""
    g = gray.astype(np.float32)
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1, :] = g[2:, :] - g[:-2, :]
    mag = np.hypot(gx, gy)
    thr = max(float(np.percentile(mag, pct)), 6.0)
    return mag > thr


def edge_iou(ea, eb, box):
    x0, y0, x1, y1 = box
    h, w = ea.shape
    x0, x1 = max(0, min(x0, w)), max(0, min(x1, w))
    y0, y1 = max(0, min(y0, h)), max(0, min(y1, h))
    if x1 <= x0 or y1 <= y0:
        return 1.0
    a = ea[y0:y1, x0:x1]
    b = eb[y0:y1, x0:x1]
    union = int((a | b).sum())
    return float((a & b).sum()) / union if union else 1.0


def light_normalize(B, A):
    """把 B 的整体亮度/色温拉到和 A 一致，排除「光变了」被误判成「物体动了」。

    逐通道按均值比缩放。延时摄影里窗光扫过会整体提亮 40%+，
    不归一化的话，静止区会被误判成 30%+ 在动。
    """
    out = B.astype(np.float32).copy()
    for c in range(3):
        ma, mb = float(A[:, :, c].mean()), float(B[:, :, c].mean())
        if mb > 1e-6 and ma > 1e-6:
            out[:, :, c] *= (ma / mb)
    return np.clip(out, 0, 255).astype(np.int16)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--still", action="append", default=[], metavar="x0,y0,x1,y1",
                    help="该静的区，边缘IoU 须 >= %.2f（可多次）" % EDGE_IOU_MIN)
    ap.add_argument("--move", action="append", default=[], metavar="x0,y0,x1,y1",
                    help="该动的区，变化率须 >= %.0f%%（可多次）" % MOVE_MIN)
    ap.add_argument("--grid", action="store_true", help="输出 3x3 九宫格变化率")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--no-light-normalize", action="store_true",
                    help="关闭光照归一化（默认开启，用于排除窗光/整体提亮造成的误判）")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        sys.exit(f"[错误] 文件不存在：{args.video}")

    ffmpeg = find_ffmpeg()
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    dur = probe_duration(ffprobe, args.video)
    tmp = tempfile.mkdtemp(prefix="i2vmot_")

    first = grab(ffmpeg, args.video, 0.03, os.path.join(tmp, "a.png"))
    last = grab_last(ffmpeg, args.video, os.path.join(tmp, "b.png"))
    if not first or not last:
        sys.exit("[错误] 抽帧失败")

    A = np.asarray(Image.open(first).convert("RGB")).astype(np.int16)
    B = np.asarray(Image.open(last).convert("RGB")).astype(np.int16)
    if A.shape != B.shape:
        sys.exit("[错误] 首末帧尺寸不一致")
    diff = np.abs(B - A).max(axis=2)
    Bn = light_normalize(B, A)
    diff_n = np.abs(Bn - A).max(axis=2)
    if not args.no_light_normalize:
        raw = float(np.abs(B - A).mean())
        norm = float(np.abs(Bn - A).mean())
        print(f"光照归一化：全画面平均差 {raw:.1f} → {norm:.1f}"
              f"（{'已启用' if norm <= raw else '本帧亮度差异小'}，判定用归一化后的值）\n")
    use = diff if args.no_light_normalize else diff_n
    h, w = diff.shape
    ea = edge_map(np.asarray(Image.open(first).convert("L")))
    eb = edge_map(np.asarray(Image.open(last).convert("L")))

    print(f"视频：{os.path.basename(args.video)}   {w}x{h}   时长 {dur:.2f}s")
    print(f"判据：事件区像素变化 ≥ {MOVE_MIN:.0f}%   静止区边缘IoU ≥ {EDGE_IOU_MIN:.2f}\n")

    grid_rows = None
    if args.grid:
        print("九宫格变化率：")
        grid_rows = []
        for r in range(3):
            row = []
            for c in range(3):
                box = [c * w // 3, r * h // 3, (c + 1) * w // 3, (r + 1) * h // 3]
                v = rate(use, box)
                row.append(round(v, 1))
            grid_rows.append(row)
            print("  " + "   ".join(f"{v:5.1f}%" for v in row))
        print()
        flat = [v for row in grid_rows for v in row]
        print(f"  最活跃格 {max(flat):.1f}%   最静止格 {min(flat):.1f}%\n")

    failed = []
    results = {"video": os.path.basename(args.video), "size": [w, h],
               "duration": round(dur, 3), "still": [], "move": []}

    for s in args.still:
        box = parse_box(s)
        v = rate(use, box)
        iou = edge_iou(ea, eb, box)
        ok = iou >= EDGE_IOU_MIN
        print(f"  [{'通过' if ok else '不通过'}] 静止区 {box}  边缘IoU {iou:.3f}"
              f"（须 ≥{EDGE_IOU_MIN:.2f}）  像素变化 {v:5.1f}%（仅参考）")
        results["still"].append({"box": box, "edge_iou": round(iou, 3),
                                 "pixel_rate": round(v, 1), "ok": ok})
        if not ok:
            failed.append(("静止区轮廓走样", box, iou))

    for s in args.move:
        box = parse_box(s)
        v = rate(use, box)
        ok = v >= MOVE_MIN
        print(f"  [{'通过' if ok else '不通过'}] 事件区 {box}  变化 {v:5.1f}%  （须 ≥{MOVE_MIN:.0f}%）")
        results["move"].append({"box": box, "rate": round(v, 1), "ok": ok})
        if not ok:
            failed.append(("事件区没动", box, v))

    if grid_rows is not None:
        results["grid"] = grid_rows

    print()
    if not args.still and not args.move:
        print("只出了报告（未给 --still / --move，不判定）")
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0

    if failed:
        print("判定：不通过")
        for what, box, v in failed:
            print(f"  · {what} {box} 实测 {v:.1f}%")
        if any(x[0] == "事件区没动" for x in failed):
            print("  → 事件区几乎没动：画面退化成会动的静图。按 §二十 的「抽象手法词」改写法重抽。")
        if any(x[0] == "静止区动了" for x in failed):
            print("  → 静止区被重绘或漂移：可能是模型重新构图，也可能是光整体变化。先排光，再排位移。")
        results["verdict"] = "fail"
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=1))
        return 1

    print("判定：通过（该动的动了，该静的静了）")
    results["verdict"] = "pass"
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
