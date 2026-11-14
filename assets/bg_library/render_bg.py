#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
背景库命令行（配合 bg_lib.py）
=============================
出静帧（做索引/审稿）：
    python3 render_bg.py --preset W7 --still /tmp/w7.jpg [--t 1.4]

出一整段背景视频（不带人物/字幕，给别的工程当底片）：
    python3 render_bg.py --preset W7 --dur 12 --out /tmp/w7.mp4

批量出全部预览：
    python3 render_bg.py --all-stills
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bg_lib as L


def add_grain(arr, rng, strength=3.0):
    """逐帧变化的颗粒 —— 静态背景「活起来」的另一半功劳"""
    n = rng.normal(0, strength, (arr.shape[0] // 2, arr.shape[1] // 2)).astype(np.float32)
    n = np.asarray(Image.fromarray(np.clip(128 + n, 0, 255).astype(np.uint8), "L")
                   .resize((arr.shape[1], arr.shape[0]), Image.BILINEAR)).astype(np.float32) - 128.0
    return np.clip(arr.astype(np.float32) + n[..., None], 0, 255).astype(np.uint8)


def still(pid, out, t=1.4, w=L.W, h=L.H, grain=False):
    bg = L.Background(pid, w, h)
    arr = bg.frame(t)
    if grain:
        arr = add_grain(arr, np.random.default_rng(7))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    Image.fromarray(arr, "RGB").save(out, quality=94)
    print("→", out)


def video(pid, out, dur, fps=30, w=L.W, h=L.H, grain=True):
    bg = L.Background(pid, w, h)
    n = int(round(dur * fps))
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, h),
           "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    rng = np.random.default_rng(11)
    for k in range(n):
        arr = bg.frame(k / float(fps))
        if grain:
            arr = add_grain(arr, rng)
        proc.stdin.write(arr.tobytes())
    proc.stdin.close()
    proc.wait()
    print("→", out)


def all_stills(outdir):
    os.makedirs(outdir, exist_ok=True)
    for pid in L.REGISTRY:
        still(pid, os.path.join(outdir, "%s.jpg" % pid), 1.4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default=None)
    ap.add_argument("--dur", type=float, default=4.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--t", type=float, default=1.4, help="静帧取第几秒")
    ap.add_argument("--still", default=None, help="出静帧到该路径")
    ap.add_argument("--out", default=None, help="出视频到该路径")
    ap.add_argument("--all-stills", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for g, (tbl, label) in L.GROUPS.items():
            print("[%s] %s" % (g, label))
            for pid, p in tbl.items():
                mark = "  ★默认" if pid == L.DEFAULT else ""
                print("   %-3s %s%s" % (pid, p["name"], mark))
        return

    if a.all_stills:
        all_stills(os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview"))
        return

    pid = a.preset or L.DEFAULT
    if a.still:
        still(pid, a.still, a.t)
    if a.out:
        video(pid, a.out, a.dur, a.fps)
    if not a.still and not a.out:
        print("要么 --still，要么 --out（或 --all-stills / --list）")


if __name__ == "__main__":
    main()
