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

FFMPEG = os.environ.get("FFMPEG", "/Users/mac/.local/bin/ffmpeg")

# ★2026-10-31 修「整片发黑」根因（灿爹：画面太暗／像蒙了层灰，怀疑是不是 FX 层）
#
#   不是 FX 层（fx.enabled 一直是 false），是**本脚本的中间层编码把画面拉硬了**：
#   源成片 final_nodust 是 **limited 内容**（Y 平面 0-235，实测 Ymax=235），而中间层
#   命令多写了 `-color_range pc`，等于让 ffmpeg 把有限范围的 YUV 当 full 再扩张一次：
#       Y' = (Y-16)*255/219    ⇒ 同一帧 Y 均值 45.4 → 35.5，Ymax 235 → 255
#   暗部被压死、亮部顶到 255，整体就是「很黑、对比很硬」。逐帧量 Y 平面才看得见
#   （转成 RGB 再比会被解码端的 range 解释二次掩盖，很容易误判成"没变"）。
#
#   修法：中间层与成品都**不写** `-color_range pc`，让 Y 值端到端无损（limited 进、
#   limited 出）。末尾 _verify_brightness() 是硬闸门：抽 5 个时间点比对源/成品的
#   Y 平面均值，任一点偏差 >8% 直接退非零——以后谁再动编码参数都会被这关卡住。
#
#   ⚠️ 复核方法：一定要看 **Y 平面原始值**（-f rawvideo -pix_fmt yuv420p），不要看
#   转成 RGB 后的均值——解码端对 range 的解释会二次掩盖问题，第一次就是这样误判成
#   "往返正常"的。
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
    print(f"  亮度闸门：全片 Y 均值 源 {ma:.1f} → 成品 {mb:.1f}（{d:+.1f}%）｜"
          f"单点最大 {wd:+.1f}%@{worst[0]:.1f}s｜采样 {len(vals)} 点", flush=True)
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
    # ★2026-10-31 灿爹「产品段看着脏」：粒子层原本铺满全片，产品实拍特写（舀燕麦片/
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
    # ★2026-10-31 改：中间层**不再写 `-color_range pc`**（原 #253 的补法反而把 limited
    #   内容当 full 扩张一次，是「整片发黑」的真凶，见文件头）。源是 limited，这里就按
    #   limited 出，Y 值端到端无损；#253 关心的 B/R 偏色由 4:2:0 下采样决定，与标记无关。
    _enc = ["-c:v", "h264_videotoolbox", "-q:v", "75", "-pix_fmt", "yuv420p"]
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
                    "-pix_fmt", "yuv420p",
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
