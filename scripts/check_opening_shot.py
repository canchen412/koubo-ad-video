#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_opening_shot.py —— 开头第一镜「钩子画面」体检（2026-11-09 老板第三次返工后立）

起因（老板原话）：
  「我做的是带货短视频，开头要抓人，要有画面感，要有冲击力。你开头这一张图片太过于普通了，
    而且形象投资这四个字还写到黑板的边缘上去了，没有写到正中的位置，很丑这张图片，
    放在开头就很不好。我记得我图库有那一张图片，就是小绿人站在街道上面，
    周围建筑上都是他的脸，那一张很有脑洞，那一张可以用啊。以后你不要犯这种错误。」

根因不是审美，是**检索方式**：
  我按文案字面词搜（「形象投资」→ 搜 黑板/大字/字卡），第一张命中的黑板图就用了；
  真正该用的是 `_通用池/场景空镜/场景_赛博城市大屏环绕背影_中景_16x9.jpg`
  —— 它名字里一个「形象」字都没有，按字面词永远搜不到。

判据三条（能算的算，算不了的出图给人眼）：
  ① 教学型开头（黑板/教室/讲台/白板/PPT/字卡/标语）→ **FAIL**，一票否决
     （讲课式画面天生没冲击力，且这类图爱带大字，必被裁边）
  ② 镜1 素材非 16:9 且裁切率 > 3% → **WARN**（带字的图被裁就是「字切到边上」的物理原因）
  ③ 出首帧图 + 四边 8% 安全区框 → 人工目视「字有没有完整落在框内、有没有被裁」

用法：
  python3 check_opening_shot.py --config ws/cfg_v1.json
  python3 check_opening_shot.py --config ws/cfg_v1.json --final ws/v1/render/final.mp4 --out /tmp/op1.png
  python3 check_opening_shot.py --final 成片.mp4 --out /tmp/op1.png     # 只验成片首帧

退出码：0 = 过；1 = 有 FAIL（教学型开头）；2 = 只有 WARN（裁切风险，要人眼确认）
"""
import argparse
import json
import os
import subprocess
import sys

FF = os.environ.get("FFMPEG_BIN", "/Users/yourname/.local/bin/ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "/Users/yourname/.local/bin/ffprobe")

# 教学型／信息图型镜头的词表：这些画面放在开头＝没冲击力
BOARD_KWS = ["黑板", "教室", "讲台", "白板", "PPT", "ppt", "字卡", "标语",
             "讲台", "讲桌", "板书", "课堂"]
# 有脑洞的画面意象（只用于打印提示，不参与判定）
HOOK_HINT = ["巨幕", "大屏", "城市", "街道", "巨物", "倒影", "人群", "仰望",
             "天空", "全景", "逆光", "霓虹", "机甲", "废墟", "沙漠", "宇宙"]

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")


def probe_size(p):
    """图片走 PIL，视频走 ffprobe。"""
    if p.lower().endswith(VIDEO_EXT):
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", p],
            capture_output=True, text=True).stdout.strip()
        w, h = out.split("x")[:2]
        return int(w), int(h)
    from PIL import Image
    with Image.open(p) as im:
        return im.size


def crop_ratio(w, h, tw=1920, th=1080):
    """按 cover 缩放到 tw×th 之后，被裁掉的原图面积占比。"""
    s = max(tw / w, th / h)
    kept = (tw / s) * (th / s)
    return 1.0 - kept / (w * h)


def first_shot(cfg_path):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    shots = cfg.get("shots") or []
    if not shots:
        raise SystemExit(f"✗ {cfg_path} 里没有 shots")
    s0 = shots[0]
    if isinstance(s0, dict):
        s0 = s0.get("src") or s0.get("path")
    return s0, cfg


def grab_frame(final, t, out):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    subprocess.run([FF, "-v", "error", "-ss", f"{t:.2f}", "-i", final,
                    "-frames:v", "1", "-y", out], check=True)


def draw_safe(src_png, dst_png, margin=0.08):
    """在首帧上画四边 8% 安全区 + 中心十字，方便人眼判「字有没有贴边」。"""
    from PIL import Image, ImageDraw
    im = Image.open(src_png).convert("RGB")
    W, H = im.size
    d = ImageDraw.Draw(im)
    mx, my = int(W * margin), int(H * margin)
    box = (mx, my, W - mx, H - my)
    d.rectangle(box, outline=(255, 60, 60), width=max(3, W // 640))
    cx, cy = W // 2, H // 2
    arm = max(20, W // 60)
    col = (60, 220, 255)
    d.line([(cx - arm, cy), (cx + arm, cy)], fill=col, width=max(2, W // 960))
    d.line([(cx, cy - arm), (cx, cy + arm)], fill=col, width=max(2, W // 960))
    im.save(dst_png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="cfg_*.json（取 shots[0] 当镜1）")
    ap.add_argument("--final", help="成片 mp4（抽首帧目视）")
    ap.add_argument("--out", default="/tmp/opening_shot.png", help="安全区检查图输出路径")
    ap.add_argument("--t", type=float, default=None,
                    help="抽帧时刻；默认 cover_dur+1.2（跳过封面帧和开场转场，取镜1 稳定帧）")
    ap.add_argument("--allow-board", action="store_true",
                    help="确需教学型开头时放行（留痕用，默认不许）")
    a = ap.parse_args()

    if not a.config and not a.final:
        ap.error("至少给 --config 或 --final 之一")

    fails, warns = [], []

    src, cfg = (None, {})
    if a.config:
        src, cfg = first_shot(a.config)
        name = os.path.basename(src)
        print(f"══ 镜1 素材\n  {src}")

        hit = [k for k in BOARD_KWS if k in name]
        if hit and not a.allow_board:
            fails.append(f"镜1 是教学型画面（命中 {hit}）—— 讲课式开头没有冲击力")
        elif hit:
            print(f"  ⚠️ 教学型画面（{hit}）已被 --allow-board 放行（留痕）")

        if os.path.exists(src):
            w, h = probe_size(src)
            cr = crop_ratio(w, h)
            print(f"  尺寸 {w}×{h}  裁切率 {cr * 100:.1f}%")
            if cr > 0.03:
                warns.append(
                    f"镜1 素材裁切率 {cr * 100:.1f}% > 3% —— 图里若带大字，"
                    f"必被切到边上（本轮「形象投资」贴边就是这个原因）")
            if abs(w / h - 16 / 9) < 0.005:
                print("  ✓ 原生 16:9，零裁切")
            hint = [k for k in HOOK_HINT if k in name]
            if hint:
                print(f"  ✓ 画面意象像是钩子图（{hint}）")
            else:
                print("  · 名字里没有明显「钩子意象」词 —— 请目视确认它够不够抓人")
        else:
            warns.append(f"素材文件不存在：{src}")

    # 首帧 / 安全区图
    if a.final:
        t = a.t
        if t is None:
            cd = float(cfg.get("cover_dur") or 0.5)
            # ★+1.2 而不是 +0.3：封面后还有 0.3s 左右淡入 + 切片转场，
            #   抽早了会抽到「画面被切成横条」的转场中间帧（本轮实撞，白判一次）。
            t = cd + 1.2
        raw = a.out.replace(".png", "_raw.png")
        grab_frame(a.final, t, raw)
        draw_safe(raw, a.out)
        print(f"\n══ 首帧目视\n  {a.out}（红框＝四边 8% 安全区，蓝十字＝画面正中）")
        print("  看三件事：① 画面有没有脑洞/压迫感　② 图里的字是否完整落在红框内且居正"
              "　③ 0.5 秒内能不能看懂")

    print()
    if fails:
        print("════ 结论：❌ FAIL ════")
        for f in fails:
            print("  · " + f)
        print("  → 换一张有脑洞的画面：先去 `_通用池/场景空镜/` 按**画面意象**（城市/巨幕/人群/巨物/倒影）"
              "扫一遍，别按文案字面词搜。")
        return 1
    if warns:
        print("════ 结论：⚠️ WARN（需人眼确认后再发）════")
        for w in warns:
            print("  · " + w)
        return 2
    print("════ 结论：✅ PASS ════")
    return 0


if __name__ == "__main__":
    sys.exit(main())
