#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ambient_motion.py —— 静图 → 氛围微动视频（0 积分，构图 100% 不变）

用途：当一张图**不能做 i2v**（模型必然重绘构图，见 references/i2v_提示词规范.md 〇之四），
      但用户要求「人物可以不动、运镜可以不动，但石头/雾/那一滴油要动」时，走这条通道。

它把「动」拆到六个可独立控制的层：
  ① 液滴下淌（可选，需要给球心/半径/位移）
  ② 尘粒飘落（自动检测画面里的亮小点，逐粒随机漂移）
  ③ 断面/表面热气（低频噪声缓慢上升，低 alpha）
  ④ 暖雾 / 光带呼吸（区域加权的亮度调制）
  ⑤ 人物呼吸（局部亚像素位移，脚底锁定）
  ⑥ 整幅极缓推近 + 手持微摆（去"静图感"，但不是唯一动源）

用法：
  python3 ambient_motion.py --src 图.png --out 出.mp4 \
      --drop 1039,313,19.5,28 --col 1027,1053,226

  没有液滴就省略 --drop / --col，退化为纯氛围层（②~⑥）。
"""
import argparse, os, subprocess, numpy as np
from PIL import Image, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--dur", type=float, default=2.0)
ap.add_argument("--w", type=int, default=1280)
ap.add_argument("--h", type=int, default=720)
ap.add_argument("--zoom", type=float, default=1.11, help="推近倍率 1.0~1.15")
ap.add_argument("--drop", type=str, default="", help="球心x,球心y,半径,位移px（原图坐标）")
ap.add_argument("--col", type=str, default="", help="油柱 x0,x1,柱顶y（原图坐标）")
ap.add_argument("--person", type=str, default="", help="人物框 x0,y0,x1,y1（可选，做呼吸）")
ap.add_argument("--crf", type=int, default=17)
ap.add_argument("--tmp", type=str, default="/tmp/ambient_frames")
a = ap.parse_args()

W, H, FPS = a.w, a.h, a.fps
N = int(round(a.dur * FPS))
os.makedirs(a.tmp, exist_ok=True)

src_im = Image.open(a.src).convert("RGB")
SW, SH = src_im.size
src = np.asarray(src_im).astype(np.float32)
Z0, Z1 = 1.0, a.zoom


def blur_mask(m, s):
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(s)), dtype=np.float32) / 255.0


def coons(y0, y1, x0, x1, m=20):
    h, w = y1 - y0, x1 - x0
    left  = src[y0:y1, max(0, x0 - m):x0].mean(axis=1)
    right = src[y0:y1, x1:min(SW, x1 + m)].mean(axis=1)
    top   = src[max(0, y0 - m):y0, x0:x1].mean(axis=0)
    bot   = src[y1:min(SH, y1 + m), x0:x1].mean(axis=0)
    tx = np.linspace(0, 1, w)[None, :, None]
    ty = np.linspace(0, 1, h)[:, None, None]
    return 0.5 * (left[:, None, :] * (1 - tx) + right[:, None, :] * tx) + \
           0.5 * (top[None, :, :] * (1 - ty) + bot[None, :, :] * ty)


# ---------- 液滴三件套 ----------
HAS_DROP = bool(a.drop)
if HAS_DROP:
    C_X, C_Y, C_R, DY_MAX = [float(v) for v in a.drop.split(",")]
    RX0 = int(C_X - C_R - 6); RX1 = int(C_X + C_R + 6)
    BAL_Y0 = int(C_Y - C_R - 3); BAL_Y1 = int(C_Y + C_R + 2)
    SHD_Y0 = BAL_Y1; SHD_Y1 = int(BAL_Y1 + C_R * 0.85)

    byy, bxx = np.mgrid[BAL_Y0:BAL_Y1, RX0:RX1].astype(np.float32)
    _d = np.sqrt((bxx - C_X) ** 2 + (byy - C_Y) ** 2)
    _reg = src[BAL_Y0:BAL_Y1, RX0:RX1]
    _R, _G, _B = _reg[:, :, 0], _reg[:, :, 1], _reg[:, :, 2]
    _gold = np.clip((_R - _B - 50) / 40.0, 0, 1) * np.clip((_R - 120) / 55.0, 0, 1)
    _circ = np.clip((C_R + 3.0 - _d) / 4.0, 0, 1)
    M_BALL = blur_mask(np.clip(_gold * _circ, 0, 1), 1.4)

    syy, sxx = np.mgrid[SHD_Y0:SHD_Y1, RX0:RX1].astype(np.float32)
    M_SHD = blur_mask(np.clip((1.0 - np.sqrt(((sxx - C_X) / (C_R * 1.25)) ** 2 +
                                             ((syy - (SHD_Y0 + (SHD_Y1 - SHD_Y0) / 2)) / ((SHD_Y1 - SHD_Y0) / 2 * 1.1)) ** 2)) * 2.8, 0, 1), 3.4)

    P_BALL = src[BAL_Y0:BAL_Y1, RX0:RX1].copy()
    P_SHD  = src[SHD_Y0:SHD_Y1, RX0:RX1].copy()
    FILL_BALL = 0.65 * src[min(BAL_Y0 + 110, SH - (BAL_Y1 - BAL_Y0)):min(BAL_Y0 + 110, SH - (BAL_Y1 - BAL_Y0)) + (BAL_Y1 - BAL_Y0), RX0:RX1] + \
                0.35 * coons(BAL_Y0, BAL_Y1, RX0, RX1)
    FILL_SHD  = 0.65 * src[min(SHD_Y0 + 110, SH - (SHD_Y1 - SHD_Y0)):min(SHD_Y0 + 110, SH - (SHD_Y1 - SHD_Y0)) + (SHD_Y1 - SHD_Y0), RX0:RX1] + \
                0.35 * coons(SHD_Y0, SHD_Y1, RX0, RX1)

    HAS_COL = bool(a.col)
    if HAS_COL:
        COL_X0, COL_X1, COL_TOP = [int(float(v)) for v in a.col.split(",")]
        P_COL = src[COL_TOP:BAL_Y0, COL_X0:COL_X1].copy()
        FE = max(2, (COL_X1 - COL_X0) // 6)
        COL_AX = np.ones(COL_X1 - COL_X0, np.float32)
        COL_AX[:FE] = np.linspace(0, 1, FE, endpoint=False)
        COL_AX[-FE:] = np.linspace(1, 0, FE, endpoint=False)
        COL_AX = COL_AX[None, :, None]

# ---------- 人物呼吸 ----------
HAS_PERSON = bool(a.person)
if HAS_PERSON:
    PX0, PY0, PX1, PY1 = [int(float(v)) for v in a.person.split(",")]
    py_g, px_g = np.mgrid[PY0:PY1, PX0:PX1].astype(np.float32)
    cx_ = (PX0 + PX1) / 2; cy_ = (PY0 + PY1) / 2
    wgt = np.exp(-(((px_g - cx_) / ((PX1 - PX0) * 0.38)) ** 2 + ((py_g - cy_) / ((PY1 - PY0) * 0.42)) ** 2))
    wgt *= (1.0 - np.clip((py_g - (PY1 - (PY1 - PY0) * 0.22)) / ((PY1 - PY0) * 0.25), 0, 1))
    PERSON_MASK = wgt.astype(np.float32)

# ---------- 尘粒 ----------
small = np.asarray(src_im.resize((W, H), Image.LANCZOS)).astype(np.float32)
gray = small.mean(axis=2)
loc = np.asarray(Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.BoxBlur(7)), dtype=np.float32)
score = (gray - loc).ravel()
idx = np.argsort(score)[::-1][:8000]
pts = []
for i in idx:
    y, x = divmod(int(i), W)
    if score[i] < 22: break
    if any((x - px) ** 2 + (y - py) ** 2 < 100 for px, py, _ in pts): continue
    pts.append((x, y, float(score[i])))
    if len(pts) >= 260: break
rng = np.random.default_rng(11)
PR = 4
gy, gx = np.mgrid[-PR:PR + 1, -PR:PR + 1]
AL_SOFT = np.exp(-((gx ** 2 + gy ** 2) / (2 * (PR * 0.82) ** 2)))[:, :, None].astype(np.float32)
PARTS, PATCHES = [], []
for (px, py, s) in pts:
    if py > H * 0.88: continue
    patch = small[max(0, py - PR):py + PR + 1, max(0, px - PR):px + PR + 1]
    if patch.shape[0] != 9 or patch.shape[1] != 9: continue
    PARTS.append(dict(x=float(px), y=float(py), vy=float(rng.uniform(18, 48)),
                      amp=float(rng.uniform(2.0, 6.0)), ph=float(rng.uniform(0, 6.28)),
                      fr=float(rng.uniform(0.5, 1.4)), a=float(min(1.0, s / 55.0))))
    PATCHES.append((patch.astype(np.float32), AL_SOFT.copy(),
                    np.percentile(patch.reshape(-1, 3), 30, axis=0)))

# ---------- 噪声 ----------
def smooth_noise(h_, w_, seed):
    r = np.random.default_rng(seed).random((h_, w_)).astype(np.float32)
    im = Image.fromarray((r * 255).astype(np.uint8)).resize((w_, h_), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32) / 255.0

NZ1, NZ2, NZ3 = smooth_noise(H, W, 21), smooth_noise(H, W, 22), smooth_noise(H, W, 23)
NZ4 = smooth_noise(H // 2, W // 2, 24)
gr_y = (np.arange(H, dtype=np.float32) / H)[:, None]
gr_x = (np.arange(W, dtype=np.float32) / W)[None, :]
W_TOP   = np.clip((0.50 - gr_y) * 2.4, 0, 1) * np.clip((gr_x - 0.10) * 3.0, 0, 1)
W_LEFT  = np.clip((0.55 - gr_x) * 2.2, 0, 1) * np.clip((0.75 - gr_y) * 2.0, 0, 1)
W_STEAM = np.clip((gr_x - 0.42) * 2.4, 0, 1) * np.clip((0.88 - gr_y) * 1.6, 0, 1) * \
          np.clip((gr_y - 0.10) * 4.0, 0, 1)


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def upscale(nz, mode=Image.BICUBIC):
    return np.asarray(Image.fromarray((nz * 255).astype(np.uint8)).resize((W, H), mode),
                      dtype=np.float32) / 255.0


for i in range(N):
    t = i / max(N - 1, 1)
    z = Z0 + (Z1 - Z0) * t
    frame = src.copy()

    if HAS_PERSON:
        fb = 1.2 * np.sin(6.283 * (t * 0.85) - 1.2)
        d_int = int(np.floor(fb)); frac = fb - d_int
        reg = frame[PY0:PY1, PX0:PX1]
        mixed = np.roll(reg, d_int, axis=0) * (1 - frac) + np.roll(reg, d_int + 1, axis=0) * frac
        m3 = PERSON_MASK[:, :, None]
        frame[PY0:PY1, PX0:PX1] = reg * (1 - m3) + mixed * m3

    if HAS_DROP:
        dyi = int(round(DY_MAX * smoothstep((t - 0.10) / 0.66)))
        if dyi > 0:
            frame[BAL_Y0:BAL_Y1, RX0:RX1] = frame[BAL_Y0:BAL_Y1, RX0:RX1] * (1 - M_BALL[:, :, None]) + \
                                            FILL_BALL * M_BALL[:, :, None]
            frame[SHD_Y0:SHD_Y1, RX0:RX1] = frame[SHD_Y0:SHD_Y1, RX0:RX1] * (1 - M_SHD[:, :, None]) + \
                                            FILL_SHD * M_SHD[:, :, None]
            if HAS_COL:
                col_h = min(BAL_Y0 + 3 - COL_TOP + dyi, SH - COL_TOP)
                cw = COL_X1 - COL_X0
                col = np.asarray(Image.fromarray(P_COL.astype(np.uint8)).resize((cw, col_h), Image.BICUBIC),
                                 dtype=np.float32)
                cxa = int(np.clip(int(C_X) - cw // 2, 0, SW - cw)); cxb = cxa + cw
                ca = COL_AX
                tgt = frame[COL_TOP:COL_TOP + col_h, cxa:cxb]
                frame[COL_TOP:COL_TOP + col_h, cxa:cxb] = tgt * (1 - ca) + col * ca
            ty0, ty1 = int(C_Y + 4), int(C_Y + dyi + 8)
            hh = ty1 - ty0
            if hh > 4:
                tw = 22
                gy2, gx2 = np.mgrid[0:hh, 0:tw].astype(np.float32)
                ax_ = np.exp(-((gx2 - tw / 2) / (tw * 0.30)) ** 2)
                al = (ax_ * (0.10 + 0.14 * gy2 / max(hh - 1, 1)))[:, :, None]
                sx0 = int(C_X) - tw // 2
                sub = frame[ty0:ty1, sx0:sx0 + tw]
                frame[ty0:ty1, sx0:sx0 + tw] = sub * (1 - al) + \
                    np.array([216, 158, 64], np.float32)[None, None, :] * al
            s0, s1 = SHD_Y0 + dyi, SHD_Y1 + dyi
            if s1 < SH:
                frame[s0:s1, RX0:RX1] = frame[s0:s1, RX0:RX1] * (1 - M_SHD[:, :, None]) + \
                                        P_SHD * M_SHD[:, :, None]
            b0 = BAL_Y0 + dyi
            b1 = min(b0 + P_BALL.shape[0], SH)
            bp = P_BALL[:b1 - b0]; mk = M_BALL[:b1 - b0]
            frame[b0:b1, RX0:RX1] = frame[b0:b1, RX0:RX1] * (1 - mk[:, :, None]) + bp * mk[:, :, None]

    cw_, ch_ = int(round(SW / z)), int(round(SH / z))
    hx = 0.005 * SW * np.sin(6.283 * t * 0.9)
    hy = 0.0035 * SH * np.sin(6.283 * t * 0.9 + 1.6)
    cx = SW // 2 + int(SW * 0.010 * t) + int(hx)
    cy = SH // 2 - int(SH * 0.003) + int(hy)
    x0 = int(np.clip(cx - cw_ // 2, 0, SW - cw_)); y0 = int(np.clip(cy - ch_ // 2, 0, SH - ch_))
    crop = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).crop(
        (x0, y0, x0 + cw_, y0 + ch_)).resize((W, H), Image.LANCZOS)
    out = np.asarray(crop).astype(np.float32)

    for p, pp in zip(PARTS, PATCHES):
        patch, al, bgv = pp
        ox, oy = int(round(p["x"])), int(round(p["y"]))
        if PR <= ox < W - PR and PR <= oy < H - PR:
            m = np.clip(al * 1.6, 0, 1)
            sl = out[oy - PR:oy + PR + 1, ox - PR:ox + PR + 1]
            out[oy - PR:oy + PR + 1, ox - PR:ox + PR + 1] = sl * (1 - m) + bgv[None, None, :] * m
        nx = p["x"] + p["amp"] * np.sin(6.283 * p["fr"] * t * 2 + p["ph"])
        ny = p["y"] + p["vy"] * t * 2.0
        ix, iy = int(round(nx)), int(round(ny))
        if PR <= ix < W - PR and PR <= iy < H - PR:
            a2 = al * p["a"]
            out[iy - PR:iy + PR + 1, ix - PR:ix + PR + 1] = (
                out[iy - PR:iy + PR + 1, ix - PR:ix + PR + 1] * (1 - a2) + patch * a2)

    n_steam = upscale(np.roll(NZ4, -int(round(46 * t)), axis=0), Image.BILINEAR)
    a_steam = np.clip((n_steam - 0.46) * 0.30, 0, 0.07) * W_STEAM
    out = out * (1 - a_steam[:, :, None]) + np.array([255, 246, 232], np.float32)[None, None, :] * a_steam[:, :, None]

    n_top = np.roll(np.roll(NZ1, -int(round(30 * t)), axis=1), -int(round(7 * t)), axis=0)
    n_left = np.roll(np.roll(NZ2, int(round(20 * t)), axis=0), int(round(12 * t)), axis=1)
    breathe = 1.0 + 0.18 * np.sin(6.283 * (t * 0.8))
    mod = (n_top - 0.5) * 0.20 * W_TOP * breathe + (n_left - 0.5) * 0.13 * W_LEFT
    glow = (NZ3 - 0.5) * 0.07 * W_TOP * breathe
    out = out * (1.0 + mod[:, :, None]) + 30.0 * glow[:, :, None]

    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(f"{a.tmp}/f{i:03d}.jpg", quality=96)

subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
                "-i", f"{a.tmp}/f%03d.jpg", "-c:v", "libx264", "-crf", str(a.crf),
                "-pix_fmt", "yuv420p", "-r", str(FPS), a.out], check=True)
print("OK", a.out)
