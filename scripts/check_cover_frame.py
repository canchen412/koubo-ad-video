# -*- coding: utf-8 -*-
"""封面首帧闸门：确认成片第一帧的「居中 3:4 区」就是封面本体。

配套 `add_cover_frame.py`。2026-11-08 老板定：封面要放进视频第一帧，
平台抓首帧当封面 —— 那第一帧就必须真的等于封面，不能差一格、不能带黑边。

查四件事：
  1. 成片 1920×1080 / 30fps；
  2. 首帧裁 555,0,1365,1080 后与封面比，平均差 < tol（默认 12）；
  3. 总帧数 == 正片帧数 + dur*30（给了 --body-frames 才查）；
  4. 容器时长 ≈ 总帧数/30（差 > 0.05s 报错，通常是 trim 漏了）。

用法：
  python3 check_cover_frame.py --video 带封面.mp4 --cover 封面.jpg --body-frames 877
退出码：0 过 / 2 不过 / 3 只警告
"""
import argparse
import json
import subprocess
import sys
import tempfile
import os

W, H = 1920, 1080
COVER_W, COVER_H = 810, 1080
X0 = (W - COVER_W) // 2          # 555


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True).stdout
    return json.loads(out)


def mean_diff(a_path, b_path):
    from PIL import Image, ImageChops
    import numpy as np
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB").resize(a.size, Image.LANCZOS)
    d = np.asarray(ImageChops.difference(a, b)).astype("float32")
    return float(d.mean()), int(d.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--cover", required=True)
    ap.add_argument("--body-frames", type=int, default=0, help="正片帧数（不含封面）")
    ap.add_argument("--dur", type=float, default=0.5)
    ap.add_argument("--tol", type=float, default=12.0)
    a = ap.parse_args()

    if not (os.path.exists(a.video) and os.path.exists(a.cover)):
        sys.exit("[ERR] 文件不存在")

    meta = ffprobe(a.video)
    vs = [s for s in meta["streams"] if s["codec_type"] == "video"][0]
    w, h = int(vs["width"]), int(vs["height"])
    fps = eval(vs.get("avg_frame_rate", "30/1")) if "/" in vs.get("avg_frame_rate", "") else 30
    nb = int(vs.get("nb_frames") or 0)
    dur = float(meta["format"]["duration"])
    errs, warns = [], []

    if (w, h) != (W, H):
        errs.append(f"尺寸 {w}x{h}，应为 {W}x{H}")
    if abs(fps - 30) > 0.01:
        errs.append(f"帧率 {fps}，应为 30")

    tmpd = tempfile.mkdtemp(prefix="covframe_")
    f0 = os.path.join(tmpd, "f0.png")
    if subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video,
                       "-frames:v", "1", f0]).returncode != 0:
        sys.exit("[ERR] 抽首帧失败")
    from PIL import Image
    Image.open(f0).convert("RGB").crop((X0, 0, X0 + COVER_W, COVER_H)).save(
        os.path.join(tmpd, "c.png"))
    md, mx = mean_diff(os.path.join(tmpd, "c.png"), a.cover)
    tag = "PASS" if md < a.tol else "FAIL"
    print(f"[{tag}] 首帧居中 3:4 平均差 {md:.2f}（上限 {a.tol}，最大 {mx}）")
    if md >= a.tol:
        errs.append("首帧居中区与封面不一致（封面没接上，或接了但被缩放/裁错）")

    exp_cover = int(round(a.dur * 30))
    if a.body_frames:
        exp = a.body_frames + exp_cover
        if nb and nb != exp:
            msg = f"总帧数 {nb}，应为 {a.body_frames}+{exp_cover}={exp}"
            (errs if abs(nb - exp) > 1 else warns).append(msg)
        else:
            print(f"[PASS] 总帧数 {nb} = 正片 {a.body_frames} + 封面 {exp_cover}")
    if nb and abs(dur - nb / 30.0) > 0.05:
        warns.append(f"容器时长 {dur:.3f}s 与帧数换算 {nb/30:.3f}s 差 {abs(dur-nb/30):.3f}s")

    for m in warns:
        print(f"[WARN] {m}")
    for m in errs:
        print(f"[FAIL] {m}")
    if errs:
        sys.exit(2)
    print("[ok] 封面首帧闸门通过")
    sys.exit(3 if warns else 0)


if __name__ == "__main__":
    main()
