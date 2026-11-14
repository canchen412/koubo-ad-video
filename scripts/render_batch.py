# -*- coding: utf-8 -*-
"""多版并行渲染（2026-11-07 老板：「现在一个视频生成的速度太慢了……可以让这个视频更快一点渲染出来」）。

背景（先把账说清）：
  · 本链路**没有 Remotion** —— 底片是 PIL 逐帧 + ffmpeg，单条 1080P / 30s 的片子约 **24 秒**。
  · 真正吃掉时间的是**事后又单独跑了 `fx_cards.py` 叠数字卡**：那是把整片再解一遍、再编一遍，
    每条多 **17 秒**（24s → 41s，多了 70%）。
  · 所以「取消动效」在本链路的落地动作 = **默认不跑 fx_cards**，交付 `render/final.mp4` 本体。

本脚本做两件事：
  ① 三版**并行**跑主流程（默认 2 路；8GB 机器别开 3，swap 会炸）；
  ② 默认**不叠动效卡**；确实要数字卡才加 `--fx`（会慢 17s/条，且成品是 final_num.mp4）。

用法：
  python3 scripts/render_batch.py --work <工程根>
  python3 scripts/render_batch.py --work <工程根> --jobs 1          # 内存紧时串行
  python3 scripts/render_batch.py --work <工程根> --fx              # 仍要数字卡
  python3 scripts/render_batch.py --work <工程根> --only v1 v3      # 只渲指定版本
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or "python3"


def find_versions(work, only=None):
    out = []
    for cfg in sorted(glob.glob(os.path.join(work, "pipeline", "*", "config.json"))):
        v = os.path.basename(os.path.dirname(cfg))
        if only and v not in only:
            continue
        txt = os.path.join(os.path.dirname(cfg), "copy.txt")
        smap = os.path.join(os.path.dirname(cfg), v + ".shot_map.json")
        out.append(dict(v=v, cfg=cfg, txt=txt, smap=smap if os.path.exists(smap) else None))
    return out


def run_one(item, logdir="/tmp"):
    t0 = time.time()
    cmd = [PY, os.path.join(SKILL, "scripts", "pipeline_run.py"),
           "--config", item["cfg"], "--text", item["txt"], "--name", item["v"],
           "--skip-tts", "--skip-banner"]
    if item["smap"]:
        cmd += ["--shot-map", item["smap"]]
    log = os.path.join(logdir, "rb_%s.log" % item["v"])
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return item["v"], r.returncode, time.time() - t0, log


def run_fx(work, versions, logdir="/tmp"):
    t0 = time.time()
    cmd = [PY, os.path.join(SKILL, "scripts", "fx_cards.py"), "--work", work] + list(versions)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, time.time() - t0, (r.stdout or "")[-400:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="工程根目录（下面有 pipeline/v1 …）")
    ap.add_argument("--jobs", type=int, default=2, help="并行路数，默认 2（8GB 机型别超 2）")
    ap.add_argument("--fx", action="store_true", help="仍叠数字卡（每条多 ~17s）")
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()

    items = find_versions(a.work, a.only)
    if not items:
        raise SystemExit("没找到 pipeline/*/config.json：%s" % a.work)
    print("并行 %d 路｜%d 条：%s｜动效卡 %s"
          % (a.jobs, len(items), ",".join(i["v"] for i in items), "开" if a.fx else "关"))

    t_all = time.time()
    done = []
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = {ex.submit(run_one, it): it for it in items}
        for f in as_completed(futs):
            v, rc, dt, log = f.result()
            done.append((v, rc, dt))
            print("  %s %s  %.1fs  %s" % (v, "✓" if rc == 0 else "✗", dt, log), flush=True)

    t_render = time.time() - t_all
    if a.fx and all(rc == 0 for _, rc, _ in done):
        rc, dt, tail = run_fx(a.work, [v for v, _, _ in done])
        print("  fx_cards %s  %.1fs" % ("✓" if rc == 0 else "✗", dt))
        print(tail)
    print("══ 渲染合计 %.1fs（串行约 %.0fs）" % (time.time() - t_all, sum(d for _, _, d in done)))


if __name__ == "__main__":
    main()
