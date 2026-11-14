#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卷播段音轨 = mix.wav 前段（配音第一句已在里面）+ 卷播音效；正文接 mix.wav 后段。

关键：**不新建时间轴**。整条音频仍是原来那条 mix.wav，只是在拼接口把
卷播音效（滚动 + 定格咚）叠上去 —— 所以卷播和口播是同一个时钟，
第一句话一字不差地对在卷播起手和定格上。

用法（2026-11-08 燕麦两条定稿时定的参数）：
  python3 mux_banner_cut.py \
      --mix  out/mix.wav \
      --out  /tmp/banner_full_audio.wav \
      --total-frames 877 --banner-frames 67 --focus 1.05

后续拼片（本脚本只管音频，视频两步在文档里）：
  ffmpeg -f concat -safe 0 -i cat.txt -c copy joined.mp4
  ffmpeg -i joined.mp4 -i /tmp/banner_full_audio.wav -map 0:v -map 1:a \
         -c:v copy -c:a aac -b:a 192k \
         -af "loudnorm=I=-8.5:TP=-1.0:LRA=11,alimiter=limit=0.95:level=0,aresample=44100" \
         -t <总帧数/FPS> -movflags +faststart 成片.mp4
  ★ -t 必给：loudnorm 有延迟，不加会让容器时长多出 2 帧。
"""
import argparse
import os
import subprocess
import sys

import numpy as np

SR = 48000
FPS = 30
HERE = os.path.dirname(os.path.abspath(__file__))
SFX_DIR = os.path.normpath(os.path.join(HERE, "..", "assets", "sfx_banner"))
ROLL = os.path.join(SFX_DIR, "卷播滚动_突然加速到暂停_原版.mp3")
DONG = os.path.join(SFX_DIR, "卷播定格_咚_综艺开头.mp3")


def rd(p):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", str(SR),
         "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def main():
    ap = argparse.ArgumentParser(description="卷播音效叠加（不重建时间轴）")
    ap.add_argument("--mix", required=True, help="原成片混音轨（minimal_audio.py mix 的输出）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--total-frames", type=int, required=True, help="成片总帧数（= plan 总时长×30）")
    ap.add_argument("--banner-frames", type=int, default=67,
                    help="卷播段帧数。默认 67（2.2333s，只吃 s01）；吃两句写 137 左右，"
                         "必须与 banner_onbg.py 的 NF 完全一致")
    ap.add_argument("--focus", type=float, default=1.05, help="定格时刻(s)，咚压在这里")
    ap.add_argument("--roll", default=ROLL)
    ap.add_argument("--dong", default=DONG)
    ap.add_argument("--roll-gain", type=float, default=0.38,
                    help="滚动声增益，垫在人声下面；0.38 实测不抢口播")
    ap.add_argument("--dong-gain", type=float, default=0.62)
    ap.add_argument("--sr", type=int, default=SR)
    a = ap.parse_args()

    sr = a.sr
    cut = a.banner_frames / float(FPS)
    total = a.total_frames / float(FPS)
    mix = rd(a.mix)
    n_cut = int(round(cut * sr))
    n_total = int(round(total * sr))

    sfx = np.zeros(n_cut, np.float32)
    roll = rd(a.roll)
    idx = np.linspace(0, len(roll) - 1, int(a.focus * sr))
    r = np.interp(idx, np.arange(len(roll)), roll)
    r = r / (np.abs(r).max() + 1e-9) * a.roll_gain
    sfx[:len(r)] += r
    dong = rd(a.dong)[:int(0.30 * sr)]
    d = dong / (np.abs(dong).max() + 1e-9) * a.dong_gain
    s = int(a.focus * sr)
    e = min(n_cut, s + len(d))
    sfx[s:e] += d[:e - s]

    head = mix[:n_cut].copy()
    head += sfx
    tail = mix[n_cut:n_total]
    out = np.concatenate([head, tail])
    if len(out) < n_total:
        out = np.pad(out, (0, n_total - len(out)))
    print("卷播段 %.3fs（口播第一句 + 滚动 + 定格咚）｜正文 %.3fs｜合计 %.3fs"
          % (n_cut / sr, len(tail) / sr, len(out) / sr))
    print("拼接口电平：head 末 %.3f → tail 首 %.3f（差 %.3f，应≈0）"
          % (np.abs(head[-200:]).max(), np.abs(tail[:200]).max(),
             abs(np.abs(head[-200:]).max() - np.abs(tail[:200]).max())))
    print("峰值 %.3f  RMS %.3f" % (float(np.abs(out).max()),
                                  float(np.sqrt((out ** 2).mean()))))

    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(sr),
                    "-ac", "1", "-i", "-", a.out], input=pcm.tobytes(), check=True)
    print("→", a.out)


if __name__ == "__main__":
    sys.exit(main())
