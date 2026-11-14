#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""shot_fit_audit.py — 镜长 vs 素材长匹配闸门（2026-11-13 老板反馈后新增）

为什么要这个闸门
----------------
老板原话：「前面的视频很短，但是那句话还没说完这个视频就放完了，最后一帧一直在那里杵着」。
实测 v1 镜1：句子 3.87s，素材只有 2.02s ⇒ build_ad_video 用 tpad clone 冻末帧 1.85s，
而这镜就在片子最开头。三条片合计 7 处冻帧，其中 6 处只要慢放就能吃掉，
1 处（0.52x）超窗必须拆句/换素材 —— 靠人眼永远发现不了，必须做成带退出码的闸门。

规则（对应 references/镜长匹配规范.md）
--------------------------------------
  素材 ≥ 镜长                    → OK（直接 trim 截短）
  素材 × (1/0.55) ≥ 镜长 > 素材  → 慢放 speed = 素材/镜长 ∈ [0.55, 1.0)，--apply 时生成变速副本
  镜长 > 素材 × (1/0.55)         → REJECT：拆句成两镜 / 换长素材 / 换静图（静图可任意长）
  短镜 < 1.2s                    → 警告：0.34s 转场前后各吃一次，实际可见不足四成

  ★2026-11-13 老板新规「开头尽量用视频」：
  镜1（开场钩子）是静图           → REJECT：开场第一眼必须是人动起来的视频，
                                    静图靠 Ken Burns 推近撑 2 秒以上观感是「照片贴上去」。
                                    确无合适视频时才加 --allow-img-open 放行。
  平均镜长 > 3.2s                 → 警告：节奏偏慢（目标 2.6~2.8s；下限每镜 ≥1.75s）

用法
----
  # 只体检（排完 shot_map 立刻跑）
  python3 shot_fit_audit.py --shot-map v1/shot_map.json --bounds v1/.../shot_bounds.json

  # 体检 + 生成慢放副本 + 回写 shot_map.fit.json（可直接喂 pipeline_run --shot-map）
  python3 shot_fit_audit.py --shot-map v1/shot_map.json --bounds v1/.../shot_bounds.json --apply

退出码：0 全过 ｜ 2 有镜超窗或有无法消除的冻帧 ｜ 4 环境/输入问题
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SPEED_MIN = 0.55          # 慢放下限（低于此值 30fps 素材摊到 >3.67s 会明显顿挫）
FREEZE_TOL = 0.10         # 允许残留的冻帧（秒）；超过即视为未解决
SHORT_SHOT = 1.20         # 短镜警戒线（秒）
PACE_AVG_MAX = 3.20       # 平均镜长上限：超过说明节奏偏慢（老板 2026-11-13 目标 2.6~2.8s）
PACE_AVG_MIN = 1.75       # 平均镜长下限：低于此值短镜必被转场吃掉
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def ff():
    return (os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")
            or ("/Users/yourname/.local/bin/ffmpeg" if os.path.exists("/Users/yourname/.local/bin/ffmpeg") else "ffmpeg"))


def fp():
    return os.environ.get("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"


def vdur(path):
    o = subprocess.run([fp(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(o.stdout.strip())
    except Exception:
        return 0.0


def is_img(item):
    if str(item.get("kind") or "").lower() in ("img", "image"):
        return True
    return os.path.splitext(str(item.get("src") or ""))[1].lower() in IMG_EXT


def make_slow(src, target, out, fps=30):
    """把 src 整体慢放到 target 秒（speed = 原长/目标 < 1）。返回 (ok, 实际时长, 说明)"""
    d = vdur(src)
    if d <= 0:
        return False, 0.0, "读不到素材时长"
    speed = d / target
    vf = f"setpts=PTS/{speed:.6f},fps={fps}"
    cmd = [ff(), "-y", "-v", "error", "-i", src, "-filter_complex", f"[0:v]{vf}[v]",
           "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "17", "-preset", "medium",
           "-pix_fmt", "yuv420p", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, 0.0, (r.stderr or "")[-400:]
    return True, vdur(out), f"speed {speed:.3f}x"


def main():
    ap = argparse.ArgumentParser(description="镜长 vs 素材长匹配闸门")
    ap.add_argument("--shot-map", required=True)
    ap.add_argument("--bounds", required=True, help="audio/shot_bounds.json（逐镜 [起,止]）")
    ap.add_argument("--work-dir", default=None,
                    help="慢放副本输出目录，默认 <shot_map 同目录>/_fit")
    ap.add_argument("--apply", action="store_true", help="真的生成慢放副本并回写 shot_map.fit.json")
    ap.add_argument("--min-speed", type=float, default=SPEED_MIN)
    ap.add_argument("--allow-img-open", action="store_true",
                    help="★2026-11-13 老板「开头尽量用视频」：镜1 是静图默认 REJECT，"
                         "确无合适视频时才用这个开关放行")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    for p in (a.shot_map, a.bounds):
        if not os.path.isfile(p):
            print(f"[FAIL] 找不到 {p}", file=sys.stderr)
            sys.exit(4)

    shots = json.load(open(a.shot_map, encoding="utf-8"))
    bounds = json.load(open(a.bounds, encoding="utf-8"))
    work = a.work_dir or os.path.join(os.path.dirname(os.path.abspath(a.shot_map)), "_fit")

    rows, n_reject, n_slow, tot_freeze = [], 0, 0, 0.0
    out_shots = []

    # ★2026-11-13 老板新规「开头尽量用视频」：开场第一镜必须是动起来的视频。
    #   静图靠 Ken Burns 推近撑 1.75s 以上，观感仍然是「一张照片贴上去」，
    #   而钩子镜是全片唯一必须抓人的位置，这里破例允许 REJECT。
    open_is_img = bool(shots) and is_img(shots[0])

    for i, it in enumerate(shots):
        if i >= len(bounds):
            rows.append(dict(i=i + 1, status="EXTRA", note="shot_map 多于 bounds，忽略"))
            out_shots.append(it)
            continue
        L = bounds[i][1] - bounds[i][0]
        item = dict(it)
        if is_img(it):
            rows.append(dict(i=i + 1, need=round(L, 3), src=os.path.basename(it["src"]),
                             status="IMG", freeze=0.0,
                             note="静图，长度任意（靠 Ken Burns 推近维持运动）"))
            out_shots.append(item)
            if L < 1.0:
                rows[-1]["warn"] = f"静图只有 {L:.2f}s，推近幅度需加大"
            continue

        src = it["src"]
        ss = float(it.get("ss", 0) or 0)
        d = max(0.0, vdur(src) - ss)
        gap = L - d
        cap = d / a.min_speed           # 该素材能撑到的最长镜长
        row = dict(i=i + 1, need=round(L, 3), src=os.path.basename(src), src_len=round(d, 3),
                   freeze=round(max(0.0, gap), 3))
        if gap <= 0.02:
            row["status"] = "OK"
            row["note"] = f"素材够长，截短 {-gap:.2f}s" if gap < -0.05 else "刚合适"
        elif L <= cap:
            speed = d / L
            row["status"] = "SLOW"
            row["speed"] = round(speed, 3)
            row["note"] = f"慢放 {speed:.2f}x → {L:.2f}s"
            n_slow += 1
            if a.apply and ss <= 0.01:
                os.makedirs(work, exist_ok=True)
                base = os.path.splitext(os.path.basename(src))[0]
                dst = os.path.join(work, f"shot{i + 1:02d}_{base}_slow{speed:.2f}x.mp4")
                if not (os.path.isfile(dst) and abs(vdur(dst) - L) <= 0.06):
                    ok, got, info = make_slow(src, L, dst)
                    if not ok:
                        row["status"] = "FAIL"
                        row["note"] = f"慢放转码失败：{info}"
                        n_reject += 1
                        rows.append(row)
                        out_shots.append(item)
                        continue
                    row["note"] += f"（副本 {os.path.basename(dst)} 实际 {got:.2f}s, {info}）"
                item["src"] = dst
                item["ss"] = 0
                item["no_zoom"] = it.get("no_zoom", False)
                item.pop("ss", None) if False else None
                row["note"] += " ✅已生成副本"
            elif ss > 0.01:
                row["status"] = "MANUAL"
                row["note"] = f"有 ss={ss:.2f}，慢放需人工处理"
                n_reject += 1
        else:
            row["status"] = "REJECT"
            row["note"] = (f"超慢放上限：素材 {d:.2f}s 最多撑 {cap:.2f}s，"
                           f"差 {gap:.2f}s ⇒ 拆句成两镜 / 换 ≥{L * a.min_speed:.2f}s 的素材 / 换静图")
            n_reject += 1
            tot_freeze += gap

        if row.get("freeze", 0) > 0 and row["status"] == "OK":
            tot_freeze += row["freeze"]
        if L < SHORT_SHOT:
            row["warn"] = f"短镜 {L:.2f}s（0.34s 转场前后各吃一次，可见不足四成）"
        rows.append(row)
        out_shots.append(item)

    # 回写
    if a.apply:
        dst_map = os.path.join(os.path.dirname(os.path.abspath(a.shot_map)), "shot_map.fit.json")
        json.dump(out_shots, open(dst_map, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n已回写 → {dst_map}")

    if a.json:
        print(json.dumps(dict(rows=rows, reject=n_reject, slow=n_slow,
                              freeze=round(tot_freeze, 3)), ensure_ascii=False))
    else:
        print(f"\n{'镜':<5}{'镜长':>7}{'素材':>7}{'冻帧':>7}  {'判定':<8}说明")
        print("-" * 96)
        for r in rows:
            if r.get("status") == "EXTRA":
                print(f"{r['i']:<5}{'-':>7}{'-':>7}{'-':>7}  EXTRA   {r['note']}")
                continue
            need = r.get("need", 0)
            sl = r.get("src_len", 0)
            fz = r.get("freeze", 0)
            print(f"{r['i']:<5}{need:>7.2f}{sl if sl else '-':>7}{fz if fz else '-':>7}  "
                  f"{r['status']:<8}{r['note']}")
            if r.get("warn"):
                print(f"{'':<5}{'':>7}{'':>7}{'':>7}  {'⚠':<8}{r['warn']}")
        print("-" * 96)
        print(f"合计：慢放 {n_slow} 镜 ｜ 打回 {n_reject} 镜 ｜ 残留冻帧 {tot_freeze:.2f}s")

    if n_reject > 0:
        print("\n[REJECT exit=2] 有镜无法靠变速解决，必须先改分镜：拆句 / 换长素材 / 换静图。")
        print("  拆句写法：工程目录 文案.split.json 里给该句加 parts，例如 "
              '{"parts": {"1": ["前半句，", "后半句。"]}}，再重跑 --tts-only 重算边界。')
        sys.exit(2)
    if open_is_img and not a.allow_img_open:
        print("\n[REJECT exit=2] 镜1 是静图 —— 老板 2026-11-13 新规：开头尽量用视频。")
        print(f"  当前镜1：{os.path.basename(str(shots[0].get('src', shots[0])))}")
        print("  静图靠推近撑 1.75s 以上，观感仍是「一张照片贴上去」，钩子镜不能这么干。")
        print("  正解：① 换成 分镜图库/<IP>/视频素材/ 里 ≥镜长 的视频；")
        print("        ② 首句太长撑不住就先在 文案.split.json 拆句，再给每一半各配视频；")
        print("        ③ 确实没有合适视频，才加 --allow-img-open 显式放行。")
        sys.exit(2)
    if tot_freeze > FREEZE_TOL:
        print(f"\n[REJECT exit=2] 残留冻帧 {tot_freeze:.2f}s > {FREEZE_TOL}s 容差。")
        sys.exit(2)
    avg = (sum(b[1] - b[0] for b in bounds[:len(shots)]) / len(shots)) if shots else 0
    if avg > PACE_AVG_MAX:
        print(f"\n[慢警告] 平均镜长 {avg:.2f}s > {PACE_AVG_MAX}s —— 节奏偏慢。")
        print("  老板 2026-11-13 定的节奏：平均 2.6~2.8s，每镜不得短于 1.75s。")
        print("  做法：在 文案.split.json 里挑「跨了两个分句」的长句拆成两镜，"
              "或用更长素材撑住长句。别硬拆成 1.7s 以下的碎镜。")
    print(f"\n[PASS exit=0] 所有镜都能靠调速或截短匹配，无冻帧；平均镜长 {avg:.2f}s。")


if __name__ == "__main__":
    main()
