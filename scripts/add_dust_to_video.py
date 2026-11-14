#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_dust_to_video.py —— 给**已有成片**叠加「漂浮粒子」（画面零改动，只加光点，0 积分）

为什么不直接 ffmpeg `blend=screen`：实测本机 ffmpeg 的 blend 在 YUV/RGB 转换上
会把整帧颜色带偏（输出 BGR 均值变成品红 [216,59,209]），故改为逐帧 Python 合成，
颜色完全可控，且原帧除粒子外零改动。

用法：
  $PY add_dust_to_video.py --src 原片.mp4 --out 加粒子.mp4
        [--count 72] [--strength 1.6] [--warm 1.0] [--seed 2026]
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from img_to_motion import make_dust  # noqa: E402

FFMPEG = os.environ.get("FFMPEG", "/Users/yourname/.local/bin/ffmpeg")
FFPROBE = os.environ.get("FFPROBE", FFMPEG.replace("ffmpeg", "ffprobe"))

# ★2026-11-02 修「亮度闸门 +5.3%」根因（第二次栽在 range 上，这次方向相反）
#
#   现象：粒子闸门报「源 82.6 → 成品 86.9（+5.3%）」，降 count/strength 完全不变。
#   真因：**源 final_nodust 是 full range（yuvj420p / color_range=pc）**，而本脚本
#   中间层写的是 `-pix_fmt yuv420p` 且不带 `-color_range`，ffmpeg 便按 limited 转换：
#       Y = 16 + 219/255 × 源Y   ⇒ 82.6 → 86.9，分毫不差。
#   即：整片画面没变亮，只是 **Y 数值被塞进了 16-235 区间** 又被当 limited 解回去。
#   上一版（2026-10-31「整片发黑」）源恰好是 limited 内容，于是"不写 -color_range"
#   是对的；换了片源、上游 build_ad_video 出的是 pc，同一条命令就翻了车。
#
#   结论（写死成规则）：**中间层与成品的 color_range 必须跟源一致，不许写死**。
#   现在开头先 ffprobe 源的 color_range，pc→`-color_range pc`、tv→`-color_range tv`，
#   同一份标记贯穿中间层与成品，Y 值端到端无损。
#
#   ⚠️ 复核方法：一定要看 **Y 平面原始值**（-f rawvideo -pix_fmt yuv420p），并且源与
#   成品必须同 range 才可比——跨 range 直接比 Y 均值，永远会差 5%（0-255 vs 16-235）。
def _probe_range(ffprobe, path):
    """取源的 color_range，返回 ffmpeg 的取值字符串 'pc' / 'tv'。

    yuvj420p 是 full range 的历史写法，ffprobe 会给 color_range=pc；元数据缺失时
    按 tv（绝大多数 H.264 交付片的实际内容）处理。
    """
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=pix_fmt,color_range",
                            "-of", "default=noprint_wrappers=1", path],
                           capture_output=True, text=True, check=True).stdout
        d = dict(l.split("=", 1) for l in r.strip().splitlines() if "=" in l)
        if d.get("pix_fmt", "").startswith("yuvj"):
            return "pc"
        if d.get("color_range") in ("pc", "full", "jpeg"):
            return "pc"
        return "tv"
    except Exception:
        return "tv"


def _ymean(ffmpeg, path, t):
    """取 t 秒处的 Y 平面均值（不解码成 RGB，避开 range 解释的干扰）。

    ★-ss 必须放在 -i 之后（输出侧精确 seek）：放在前面是"跳到最近关键帧"，
      源与成品的 keyframe 位置不同，会抽到两个不同时刻的帧——闪白切点曾因此
      测出 +67% 的假超差。
    """
    try:
        out = subprocess.run([ffmpeg, "-v", "error", "-i", path, "-ss", f"{t:.3f}",
                              "-frames:v", "1", "-f", "rawvideo",
                              "-pix_fmt", "yuv420p", "-"],
                             capture_output=True, check=True).stdout
        if not out:
            return None
        n = len(out)   # yuv420p 一帧 = W*H*1.5，Y 平面占 2/3
        y = np.frombuffer(out[: (n * 2) // 3], np.uint8)
        return float(y.mean())
    except Exception:
        return None


def _verify_brightness(ffmpeg, src, out, dur):
    """硬闸门：粒子层只许加光点，不许改整片亮度。

    判据用**全片均值**而不是逐点硬卡：片头卷播段画面在滚，源/成品差两三帧
    就是两个不同画面，逐点比会误报（实测 0.8~3.3s 报 +58%，画面其实一模一样）。
    采样从 3s 起（避开卷播+闪切），每 0.4s 一点，整片均值偏差 >4% 就退非零；
    单点最大偏差只打印出来备查。
    """
    vals = []
    t = 3.0
    while t < dur - 0.4:
        a, b = _ymean(ffmpeg, src, t), _ymean(ffmpeg, out, t)
        if a is not None and b is not None and a > 1:
            vals.append((t, a, b))
        t += 0.4
    if not vals:
        print("  ⚠️ 亮度闸门：采样为空，跳过", flush=True)
        return
    ma = sum(v[1] for v in vals) / len(vals)
    mb = sum(v[2] for v in vals) / len(vals)
    d = (mb - ma) / ma * 100.0
    worst = max(vals, key=lambda v: abs((v[2] - v[1]) / v[1]))
    wd = (worst[2] - worst[1]) / worst[1] * 100.0
    rs, ro = _probe_range(FFPROBE, src), _probe_range(FFPROBE, out)
    print(f"  亮度闸门：全片 Y 均值 源 {ma:.1f} → 成品 {mb:.1f}（{d:+.1f}%）｜"
          f"单点最大 {wd:+.1f}%@{worst[0]:.1f}s｜采样 {len(vals)} 点｜"
          f"range {rs}→{ro}", flush=True)
    if rs != ro:
        sys.exit(f"❌ 色域不一致：源 {rs} / 成品 {ro}"
                 " —— 中间层与成品的 -color_range 必须跟随源")
    if abs(d) > 4:
        sys.exit(f"❌ 亮度闸门未过：整片均值偏差 {d:+.1f}%（>4%）"
                 " —— 检查编码链的 color_range（粒子层不许改整体亮度）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=72)
    ap.add_argument("--strength", type=float, default=1.6, help="粒子亮度倍数")
    ap.add_argument("--warm", type=float, default=1.0, help="1=暖白尘粒，0=冷白")
    ap.add_argument("--size", type=float, default=1.0, help="粒子半径倍数")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--table", default=None, help="《分镜—文案—素材对应表》HTML，用来取镜边界")
    ap.add_argument("--focus-every", type=int, default=0,
                    help="每隔 N 镜在镜开头做「对焦呼吸」(0=关)；2=隔一张做一次")
    ap.add_argument("--focus-sec", type=float, default=0.45, help="合焦时长")
    ap.add_argument("--focus-max", type=float, default=5.5, help="起始模糊 sigma")
    ap.add_argument("--crf", type=int, default=21,
                    help="交付编码 CRF（★2026-10-15：本脚本曾是「体积爆炸」元凶——"
                         "旧版最后一步 -c:v copy 把中间层 h264_videotoolbox -q:v 75 "
                         "（1080p 实测 19~35 Mbps）原样交付 ⇒ 16MB 源被「加粒子」放大到 70MB，"
                         "且无 faststart（手机要下完才能播）。现改为 libx264 CRF + faststart。")
    ap.add_argument("--skip-first", type=int, default=1,
                    help="前 N 帧不画粒子（默认 1：保住 pipeline 贴的**封面首帧**干净，"
                         "平台抓封面不受粒子干扰）")
    # ★2026-10-31 老板「产品段看着脏」：粒子层原本铺满全片，产品实拍特写（舀燕麦片/
    #   桶身标签/静物）在上面像落了一层灰，把好不容易调暖的食欲感又糊掉了。
    #   --until 把粒子限制在前 N 秒（片头卷播 + 科普镜），产品段保持干净画面。
    #   0 = 全片（旧行为，向后兼容）。
    ap.add_argument("--until", type=float, default=0.0,
                    help="只在该秒数之前画粒子（0=全片）。产品段建议给到产品镜起点前")
    a = ap.parse_args()

    cap = cv2.VideoCapture(a.src)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    dur = total / fps if total else 0
    rng = np.random.default_rng(a.seed)
    dust = make_dust(a.count, W, H, rng)
    for q in dust:
        q["a"] = min(0.85, q["a"] * 2.1)      # 整体调亮，肉眼可见
    col = np.array([255, 236 - 36 * (1 - a.warm), 198 + 40 * (1 - a.warm)], np.float32)

    shots = []
    if a.table and a.focus_every > 0:
        from motion_fullfilm import parse_table
        shots = [(no, t0, t1) for (no, t0, t1, _t, _s, _h) in parse_table(a.table)]
        print(f"  对焦呼吸：每 {a.focus_every} 镜做一次（共 {len(shots)} 镜边界）")

    def focus_sigma(t_abs: float) -> float:
        if not shots:
            return 0.0
        for no, t0, t1 in shots:
            if t0 <= t_abs < t1:
                if (no - 1) % a.focus_every != 0:
                    return 0.0
                k = (t_abs - t0) / max(1e-6, a.focus_sec)
                return 0.0 if k >= 1.0 else a.focus_max * (1.0 - k) ** 2
        return 0.0

    tmp = a.out + ".v.mp4"
    # ★2026-11-02：range 跟随源（见文件头）。源 pc → 中间层与成品都写 `-color_range pc`，
    #   Y 值端到端无损；源 tv（大多数交付片）→ 都写 tv。**不许写死**，写反一次就是
    #   ±5% 的整体漂移（2026-10-31 黑过头、2026-11-02 亮 5%，同一类错）。
    _range = _probe_range(FFPROBE, a.src)
    print(f"  色域：源 color_range={_range}（中间层与成品同标记）", flush=True)
    _enc = ["-c:v", "h264_videotoolbox", "-q:v", "75",
            "-pix_fmt", "yuv420p", "-color_range", _range]
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-an"] + _enc + [tmp]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        t = (i / max(1, total - 1)) if total else (i / fps / max(dur, 1e-6))
        sig = focus_sigma(i / fps if fps else 0.0)
        if sig > 0.3:
            fr = cv2.GaussianBlur(fr, (0, 0), sig)
        img = fr.astype(np.float32)
        # ★前 skip_first 帧不画粒子：保住 pipeline 贴的封面首帧干净
        if i < a.skip_first or (a.until > 0 and (i / fps if fps else 0.0) >= a.until):
            p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
            i += 1
            continue
        for q in dust:
            px = (q["x"] + q["vx"] * t * dur) % (W + 80) - 40
            py = (q["y"] + q["vy"] * t * dur) % (H + 80) - 40
            al = q["a"] * (0.55 + 0.45 * math.sin(2 * math.pi * 0.8 * t + q["ph"])) * a.strength
            if al <= 0.015:
                continue
            r = int(max(2, q["r"] * a.size * (1 + 0.06 * math.sin(2 * math.pi * 0.9 * t + q["ph"]))))
            x0, x1, y0, y1 = int(px) - r, int(px) + r, int(py) - r, int(py) + r
            x0c, y0c = max(0, x0), max(0, y0)
            x1c, y1c = min(W, x1), min(H, y1)
            if x1c <= x0c or y1c <= y0c:
                continue
            yy, xx = np.mgrid[y0c:y1c, x0c:x1c]
            d = np.sqrt((xx - px) ** 2 + (yy - py) ** 2) / max(1, r)
            g = (np.clip(1.0 - d, 0, 1) ** 2 * al)[..., None]
            roi = img[y0c:y1c, x0c:x1c]
            # screen 混合（在 RGB 上做，颜色保真）
            img[y0c:y1c, x0c:x1c] = 255.0 - (255.0 - roi) * (1.0 - g) + col * g * 0.55
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
        i += 1
        if i % 300 == 0:
            print(f"  …{i}/{total or '?'} 帧", flush=True)
    cap.release()
    p.stdin.close()
    p.wait()
    if p.returncode != 0:
        sys.exit("ffmpeg 写失败")
    # ★2026-10-15 修（#253）：最后一步必须**重新按交付规格编码**，不能 -c:v copy。
    #   旧版 copy 把中间层 videotoolbox q:v75（19~35 Mbps）当成品交付 ⇒ 体积爆炸 + 无 faststart。
    #   中间层 q:v75 保持不变（只决定临时文件，高质量有利最终画质）；成品走 libx264 CRF21 + faststart。
    #   音频 -c:a copy：源已在 pipeline 末道限幅过，copy 不回退峰值。
    # ★2026-10-21：临时名原用 `<out>.web.mp4`，会被 host file policy 判成 web 预览缓存
    #   而拒绝 rename（`Brokered host rename source refused`）。改 `.part` + 失败兜底复制。
    tmp_out = a.out + ".part.mp4"
    # ★2026-10-21 修：原用 `-shortest`，AAC 音频（copy）报的时长比视频短 0.13s，
    #   -shortest 会**按音频截视频**：649 帧进去、645 帧出来（实测，片子尾巴少 4 帧）。
    #   改成显式 `-t` 到源视频时长，视频一帧不丢、音频按同长裁。
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", tmp, "-i", a.src,
                    "-map", "0:v:0", "-map", "1:a:0?",
                    "-c:v", "libx264", "-crf", str(a.crf),
                    "-preset", "medium", "-profile:v", "high", "-level", "4.0",
                    "-pix_fmt", "yuv420p", "-color_range", _range,
                    "-movflags", "+faststart",
                    "-c:a", "copy", "-t", f"{dur:.3f}", tmp_out], check=True)
    try:
        os.replace(tmp_out, a.out)
    except (PermissionError, OSError) as _e:
        print(f"  ⚠️ rename 被拦（{_e}）——改复制落盘", flush=True)
        with open(tmp_out, "rb") as _s, open(a.out, "wb") as _d:
            while True:
                _b = _s.read(8 << 20)
                if not _b:
                    break
                _d.write(_b)
        try:
            os.remove(tmp_out)
        except Exception:
            pass
    os.remove(tmp)
    _mb = os.path.getsize(a.out) / 1048576
    print(f"✅ {i} 帧 → {a.out}（{_mb:.1f} MB，libx264 CRF{a.crf} + faststart）")
    # ★2026-10-31 硬闸门：粒子层只许「加光」，不许改整体亮度。超差直接退非零。
    _verify_brightness(FFMPEG, a.src, a.out, dur)


if __name__ == "__main__":
    main()
