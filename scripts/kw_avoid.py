#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kw_avoid.py —— 重点字「不压主体」自动落位（2026-11-07）

为什么要有它：`build_ad_video.py` 的自动落位只看**画面能量**（哪里平），
它不知道小绿人站在哪 —— 所以「字压头/压身」只能靠人眼发现。
老板 2026-11-07：「重点字不要挡住主体」；且技能铁律：规则写进文档 ≠ 会执行，
每条硬规则都要配带退出码的闸门。本脚本就是那道闸门 + 自动定位器。

做法：
  ① 取该 keyword 所在镜的素材帧（视频按 `--seek` 抽，图片直读）
  ② Vision 显著性求主体 bbox（IP 小绿人）；显著性太弱时用**绿掩膜**兜底
  ③ 字块尺寸复用渲染器公式 `kw_box_px(text, size)`（同一口径，不靠估）
  ④ 网格搜索合法位：完整落在安全框内、与主体 bbox（外扩 PAD）零相交、
     避开右上合规小字区
  ⑤ 打分 = 块内边缘密度（越平越好）+ 贴角偏好 + 离主体距离（有关联感）
  ⑥ 打印每词的建议 pos；`--write` 回写 config 的 keywords[i]["pos"]

用法：
  PY=/Users/yourname/.workbuddy/binaries/python/envs/default/bin/python
  S=~/.workbuddy/skills/koubo-ad-video/scripts/kw_avoid.py

  $PY $S --config config_v1.json                    # 只给建议
  $PY $S --config config_v1.json --write            # 回写 pos
  $PY $S --config config_v1.json --draw qc/kwpos.jpg  # 出联络图（框出主体与字块）

退出码：0 全部有合法位；2 有词找不到合法位（需改字号或换镜）。
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

FF = "/Users/yourname/.local/bin/ffmpeg"
W, H = 1920, 1080
PAD = 20            # 主体 bbox 外扩（禁放区）
MARGIN = 40         # 字块距画边
Y_TOP = 140         # 顶部安全线（片头大字/合规小字）
Y_BOT = 780         # 字块下沿上限（字幕带 820 起，留 40px 不贴脸）
STEP = 30           # 网格步长
GW, GH = W // 10, H // 10           # 主体连通域用的粗网格（1 格 = 10px）
DISC_RECT = (1240, 20, 1900, 175)   # 右上合规声明小字区（必让）


# ---------------------------------------------------------------- 字块尺寸
def kw_box_px(text, size):
    """与 build_ad_video.kw_box_px 完全同口径（中文 1.0 字宽 / 英数 0.56）"""
    n = 0.0
    for c in text:
        n += 0.56 if (c.isascii() and (c.isalnum() or c in "%.+-")) else 1.0
    return int(round(n * size * 1.06 + 80)), int(round(size * 1.60))


# ---------------------------------------------------------------- 取帧
def grab(config, pi, seek, tmp):
    cfg = json.load(open(config, encoding="utf-8"))
    src = cfg["shots"][pi - 1]
    out = os.path.join(tmp, f"p{pi}_{int(seek * 100):03d}.png")
    os.makedirs(tmp, exist_ok=True)
    if src.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        im = Image.open(src).convert("RGB")
        # 与渲染器 cover 口径一致：等比放大铺满 1920x1080 后居中裁
        r = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * r + 0.5), int(im.height * r + 0.5)), Image.LANCZOS)
        x0 = (im.width - W) // 2
        y0 = (im.height - H) // 2
        im.crop((x0, y0, x0 + W, y0 + H)).save(out)
    else:
        subprocess.run([FF, "-v", "error", "-ss", f"{seek:.2f}", "-i", src,
                        "-frames:v", "1", "-vf",
                        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                        "-y", out], check=False)
    return out


# ---------------------------------------------------------------- 主体
def _green_bbox(frame_png):
    """小绿人 IP 恒为绿 → 绿掩膜是比显著性更准的主体判据。
    显著性常把「最显眼的东西」认成主体（实测把产品罐认成人）。
    ★必须取**最大连通域**：科普镜里有绿光球（B族/锌），全图包络会把球也圈进来，
    于是「主体」虚胖一整圈，哪儿都不能放字（实测无解）。"""
    im = Image.open(frame_png).convert("RGB").resize((GW, GH), Image.LANCZOS)
    a = np.asarray(im).astype(np.int16)
    m = (a[:, :, 1] > 60) & (a[:, :, 1] > a[:, :, 0] + 15) & (a[:, :, 1] > a[:, :, 2] + 15)
    if int(m.sum()) < GW * GH * 0.008:
        return None
    seen = np.zeros_like(m, dtype=bool)
    best_n, best_box = 0, None
    for sy in range(GH):
        for sx in range(GW):
            if not m[sy, sx] or seen[sy, sx]:
                continue
            q = [(sy, sx)]
            seen[sy, sx] = True
            n, x0, x1, y0, y1 = 0, sx, sx, sy, sy
            while q:
                y, x = q.pop()
                n += 1
                x0, x1 = min(x0, x), max(x1, x)
                y0, y1 = min(y0, y), max(y1, y)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < GH and 0 <= xx < GW and m[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        q.append((yy, xx))
            if n > best_n:
                best_n, best_box = n, (x0, y0, x1, y1)
    if not best_box:
        return None
    k = W // GW
    x0, y0, x1, y1 = best_box
    return {"x0": x0 * k, "y0": y0 * k, "x1": min(W - 1, (x1 + 1) * k),
            "y1": min(H - 1, (y1 + 1) * k)}


def subject_bbox(frame_png, mode="auto"):
    """主体 = 绿掩膜（小绿人）∪ 显著性主体（常把**产品罐**认成主体 —— 这次正好用得上，
    带货片里罐子被大字盖住同样是废镜）。显著性只在其面积 ≤ 55% 画面时并入：
    科普镜里的发光环/光球会把显著性撑成几乎整屏，并进来就等于没有合法位。

    mode（2026-11-07 补，v2/v3 实测逼出来的）：
      auto   默认，绿掩膜 ∪ 显著性 —— 有产品罐的镜必须保护罐子
      person 只认绿掩膜 —— 画面里的「显眼东西」是**纹理**不是主体时用：
             实测 v2 镜6「原料气泡升浮」满屏彩色气泡，显著性并进来等于无合法位；
             而气泡只是配料概念的可视化，字压上去不伤任何东西
      none   无主体 —— 纯粒子/纯光效镜，只按平整度落位（慎用，要目视复核）
    """
    g = _green_bbox(frame_png)
    s = None
    if mode == "none":
        return None, "指定无主体"
    if mode != "person":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            import plan_behind_pos as pbp
            s = pbp.person_bbox(frame_png)
            if s and (s["x1"] - s["x0"]) * (s["y1"] - s["y0"]) > W * H * 0.55:
                s = None
        except Exception as e:
            print(f"  ⚠️ 显著性不可用：{e}")
    boxes = [b for b in (g, s) if b]
    if not boxes:
        return None, "无主体"
    tag = "+".join([t for t, b in (("绿掩膜", g), ("显著性", s)) if b])
    if len(boxes) == 1:
        return boxes[0], tag
    return {"x0": min(b["x0"] for b in boxes), "y0": min(b["y0"] for b in boxes),
            "x1": max(b["x1"] for b in boxes), "y1": max(b["y1"] for b in boxes)}, tag


# ---------------------------------------------------------------- 平整度
def edge_ii(frame_png):
    """返回 (边缘密度积分图, 亮度积分图)。亮度用来罚「压在发光球/高光上」——
    实测科普镜左上角那串光球边缘稀疏，光看边缘密度会误判成"空"。"""
    im = Image.open(frame_png).convert("L").resize((W, H), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float32) / 255.0
    gx = np.abs(np.diff(a, axis=1, prepend=a[:, :1]))
    gy = np.abs(np.diff(a, axis=0, prepend=a[:1, :]))
    g = gx + gy
    return (np.pad(g, ((1, 0), (1, 0))).cumsum(0).cumsum(1),
            np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1))


def box_mean(ii, x0, y0, x1, y1):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    return (ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]) / max(1, (x1 - x0) * (y1 - y0))


def inter(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def vdur(path):
    probe = os.path.join(os.path.dirname(FF), "ffprobe")
    probe = probe if os.path.exists(probe) else "ffprobe"
    try:
        r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", path], capture_output=True, timeout=60)
        return float(r.stdout.decode().strip())
    except Exception:
        return 2.5


def place(iis, bw, bh, bb, ybot=None):
    """iis = 多帧的 (边缘积分图, 亮度积分图)。字要停 1.5–2.6s，人物会动、还在推镜，
    所以每个候选位都按**所有帧里最差的那一帧**打分，最小化最差分 = 全程站得住。"""
    ybot = Y_BOT if ybot is None else min(Y_BOT, ybot)
    if bb:
        keep = (bb["x0"] - PAD, bb["y0"] - PAD, bb["x1"] + PAD, bb["y1"] + PAD)
        bcx, bcy = (bb["x0"] + bb["x1"]) / 2, (bb["y0"] + bb["y1"]) / 2
    else:
        keep, bcx, bcy = None, W / 2, H / 2
    best = None
    for y0 in range(Y_TOP, ybot - bh + 1, STEP):
        for x0 in range(MARGIN, W - MARGIN - bw + 1, STEP):
            r = (x0, y0, x0 + bw, y0 + bh)
            if keep and inter(r, keep):
                continue
            if inter(r, DISC_RECT):
                continue
            edge_d = min(x0, W - r[2]) + min(y0, H - r[3])
            dc = ((x0 + bw / 2 - bcx) ** 2 + (y0 + bh / 2 - bcy) ** 2) ** 0.5
            worst, en_w, lum_w = -1.0, 0.0, 0.0
            for ii, lum in iis:
                en = box_mean(ii, x0, y0, x0 + bw, y0 + bh)
                lv = box_mean(lum, x0, y0, x0 + bw, y0 + bh)
                s = en * 1.0 + 0.75 * lv + 0.0006 * edge_d + 0.00012 * dc
                if s > worst:
                    worst, en_w, lum_w = s, en, lv
            if best is None or worst < best[0]:
                best = (worst, r, en_w, lum_w, edge_d, dc)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--kw-json", help="重点字清单另存的文件（如 v1.kw.json）；不给则读 config.keywords")
    ap.add_argument("--samples", default="0.12,0.5,0.88",
                    help="视频抽帧位置（该镜素材时长的比例，逗号分隔；默认 3 点取并集）")
    ap.add_argument("--tmp", default="/tmp/_kwavoid")
    ap.add_argument("--draw", help="联络图输出（框主体=红，字块=青）")
    ap.add_argument("--write", action="store_true", help="回写 keywords[i].pos")
    ap.add_argument("--subject-mode", default=None,
                    choices=["auto", "person", "none"],
                    help="主体判据：auto(默认)/person(只认绿掩膜)/none(无主体)；"
                         "单条可用 kw_json 里的 subject 字段覆盖")
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    kwsrc = a.kw_json or a.config
    src_obj = cfg if a.kw_json is None else json.load(open(a.kw_json, encoding="utf-8"))
    kws = src_obj.get("keywords") or []
    if not kws:
        print("无 keywords，跳过")
        return 0
    size_def = int(cfg.get("kw_size", 120))
    samples = [float(x) for x in a.samples.split(",") if x.strip()]
    tiles, bad = [], 0
    for j, kw in enumerate(kws):
        pi = int(kw["phrase"])
        size = int(kw.get("size") or (int(cfg.get("kw_super_size", 190))
                                      if (kw.get("super") or kw.get("tier") in ("super", "hero"))
                                      else size_def))
        bw, bh = kw_box_px(kw["kw"], size)
        src = cfg["shots"][pi - 1]
        is_vid = not src.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        # 字要停 1.5–2.6s，人物会动、还在推镜 ⇒ 多帧取**并集**主体，不能只看一帧
        pts = [s * (vdur(src) if is_vid else 1.0) for s in samples] if is_vid else [0.0]
        frames = [grab(a.config, pi, t, a.tmp) for t in pts]
        frames = [f for f in frames if os.path.exists(f) and os.path.getsize(f) > 1024]
        if not frames:
            print(f"  ✗ 镜{pi} 「{kw['kw']}」 抽帧失败：{os.path.basename(src)}")
            bad += 1
            continue
        boxes, hows = [], set()
        _mode = kw.get("subject") or a.subject_mode or "auto"
        for f in frames:
            b, h = subject_bbox(f, _mode)
            if b:
                boxes.append(b)
                hows.add(h)
        bb = None
        if boxes:
            bb = {"x0": min(b["x0"] for b in boxes), "y0": min(b["y0"] for b in boxes),
                  "x1": max(b["x1"] for b in boxes), "y1": max(b["y1"] for b in boxes)}
        how = "/".join(sorted(hows)) or "无主体"
        iis = [edge_ii(f) for f in frames]
        # 产品图镜：罐子/瓶排几乎总在画面下半，而显著性经常漏检它们
        # （实测 v3 镜10「比六手势六瓶排开」只框到人，字压在最左那瓶罐子上）
        ybot = None
        if os.path.basename(src).startswith(("产品_", "选品_")):
            ybot = int(H * 0.62)
        res = place(iis, bw, bh, bb, ybot)
        old = kw.get("pos")
        if not res:
            bad += 1
            print(f"  ✗ 镜{pi} 「{kw['kw']}」 {bw}x{bh} 无合法位（主体 {bb}）—— 缩字号或换镜")
            continue
        _, r, en, lum_v, edge_d, dc = res
        pos = [int((r[0] + r[2]) / 2), int((r[1] + r[3]) / 2)]
        if bb:
            print(f"  镜{pi:2d} 「{kw['kw']}」 {size}号 {bw}x{bh} 主体({how}"
                  f"{'' if _mode == 'auto' else ' · 模式=' + _mode})="
                  f"[{bb['x0']},{bb['y0']},{bb['x1']},{bb['y1']}]")
        else:
            print(f"  镜{pi:2d} 「{kw['kw']}」 {size}号 {bw}x{bh} 主体不可测（仅按平整度落位）")
        print(f"        → pos={pos} 框={r} 平整度={en:.3f} 亮度={lum_v:.2f} "
              f"边距={edge_d} 离主体={dc:.0f}px{'  (原 '+str(old)+')' if old else ''}")
        if a.write:
            kw["pos"] = pos
        if a.draw:
            im = Image.open(frames[len(frames) // 2]).convert("RGB").resize((W // 2, H // 2), Image.LANCZOS)
            d = ImageDraw.Draw(im)
            if bb:
                d.rectangle([bb["x0"] // 2, bb["y0"] // 2, bb["x1"] // 2, bb["y1"] // 2],
                            outline=(255, 60, 60), width=3)
            d.rectangle([r[0] // 2, r[1] // 2, r[2] // 2, r[3] // 2],
                        outline=(0, 255, 255), width=3)
            d.text((10, 8), f"p{pi} {kw['kw']} {pos}", fill=(255, 255, 0))
            tiles.append(im)
    if a.write:
        json.dump(src_obj, open(kwsrc, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"★ 已回写 {kwsrc}")
    if a.draw and tiles:
        cols = min(3, len(tiles))
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (W // 2), rows * (H // 2)), (16, 16, 16))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * (W // 2), (i // cols) * (H // 2)))
        os.makedirs(os.path.dirname(os.path.abspath(a.draw)) or ".", exist_ok=True)
        sheet.save(a.draw, quality=88)
        print(f"★ 联络图 → {a.draw}")
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
