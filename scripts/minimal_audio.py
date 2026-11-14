#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简版音频 · 逐句配音 + 混音
===========================
两个子命令：

  tts   逐句云端配音 → vo/*.mp3 + vo/*.words.json + vo_index.json
        python3 minimal_audio.py tts --texts texts.txt --outdir work/out

  mix   按 timeline.json 拼口播 + 贴 UI 音效 + mux 回成片
        python3 minimal_audio.py mix --timeline work/out/minimal.timeline.json \\
               --vo work/out/vo_index.json --video work/out/minimal.mp4 \\
               --out work/out/final.mp4 [--bgm xxx.mp3]

为什么要逐句：极简版是「一句一贴纸」，贴纸弹入必须和这句语音严格同帧。
逐句合成才能拿到每句独立时长；同时必须**裁句首静音**，否则画面比声音早到。
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = os.path.expanduser("~/.workbuddy/secrets/dashscope.env")
WS = os.path.expanduser("~/.workbuddy/skills/cloud-tts/scripts/cloud_cosyvoice_ws.py")
SFX_DIR = os.path.join(HERE, "..", "assets", "sfx")
SR = 48000

# 贴纸弹入音：轻、短、不带长尾。轮换用，避免同一条片里声音重复
SFX_ROTATION = ["pop_in2.wav", "kw_pop.wav", "kw_tick.wav", "pop_in.wav",
                "kw_click.wav", "kw_marker.wav"]
SFX_VOL = 0.40          # 贴纸音统一压到 0.40（比重点字轻一档）

# 语义音效（2026-11-03 加）：plan 里写 "sfx": "shock" 就能用，值可带子目录。
# 为什么要有：原来 13 个镜全靠上面 6 个轻弹入音轮换，镜头说什么情绪都只有「啪」一声，
# 震惊、否定、通过、收尾听起来一模一样。这里按**语义**配，一条片挑 4~6 处挂。
SFX_SEMANTIC = {
    # 键            文件（相对 assets/sfx）                                    建议音量
    "shock":  ("爆款叙事音效_261008/10_震惊闷响.wav",         0.62),   # 震惊/惊恐：闷雷型反转
    "no":     ("semantic/sem_no_buzz.wav",                    0.58),   # 否定/不合格：双短促蜂鸣
    "stop":   ("semantic/sem_no_duang.wav",                   0.60),   # 禁止/叫停：低频闷咚
    "yes":    ("semantic/sem_yes_ding.wav",                   0.58),   # 合格/通过：清脆双音上行
    "happy":  ("kw_bellup.wav",                               0.50),   # 得意/占到便宜
    "doubt":  ("爆款叙事音效_261008/03_短促疑问音.wav",       0.55),   # 疑问/悬念
    "reveal": ("爆款叙事音效_261008/12_天光一现_高频闪.wav",  0.55),   # 揭示/答案落地
    "heavy":  ("爆款叙事音效_261008/08_沉重心跳_低频重击.wav", 0.62),   # 重锤/结论砸下
    "end":    ("爆款叙事音效_261008/14_恍然大悟_收束.wav",    0.55),   # 收尾/CTA 前
    "num":    ("爆款叙事音效_261008/02_叮叮叮_清脆点缀.wav",  0.55),   # 数字/价格点缀
    "point":  ("kw_marker.wav",                               0.45),   # 指向左下角
}

# BGM 与标准模式（build_ad_video.py）同一套判据，别各走一套
BGM_DIR = os.path.join(HERE, "..", "assets", "bgm")
BGM_OFFSET_DB = 10.0    # 自动配平目标：BGM 比口播低 10dB
BGM_DUCK = dict(thr=0.05, ratio=5.0, attack=0.025, release=0.380)   # thr = 标准版 sidechain 的 threshold
BGM_FADE_IN, BGM_FADE_OUT = 0.4, 1.0

# 整体响度：与标准模式同一条链（基础 -11.5 + boost 3.0 = -8.5 LUFS，TP -1.0）
# 不做这一步，极简版成片会只有 -22 dB 左右的电平，手机上听起来比标准片轻一大截
LOUD_CHAIN = ("loudnorm=I=-8.5:TP=-1.0:LRA=11,"
              "alimiter=limit=0.95:level=0,aresample=44100")


def load_env(path):
    got = {}
    if not os.path.exists(path):
        return got
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        ln = re.sub(r"^export\s+", "", ln)
        if "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        got[k.strip()] = v.strip().strip("'\"")
    return got


def probe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


# ---------------- tts ----------------

def cmd_tts(a):
    env = load_env(SECRETS)
    key = env.get("DASHSCOPE_API_KEY")
    vid = env.get("COSYVOICE_VOICE_ID")
    model = env.get("COSYVOICE_MODEL", "cosyvoice-v3.5-plus")
    rate = env.get("COSYVOICE_RATE", "1.1")
    if not key or not vid:
        sys.exit("[x] 缺 DASHSCOPE_API_KEY / COSYVOICE_VOICE_ID —— 先配 %s" % SECRETS)

    raw_dir = os.path.join(a.outdir, "vo_raw")
    trim_dir = os.path.join(a.outdir, "vo_trim")
    vo_dir = os.path.join(a.outdir, "vo")
    for d in (raw_dir, trim_dir, vo_dir):
        os.makedirs(d, exist_ok=True)
    lines = [ln.strip() for ln in open(a.texts, encoding="utf-8") if ln.strip()]
    print("配音 %d 句｜模型 %s｜语速 %s（与标准模式同参）" % (len(lines), model, rate))

    e = dict(os.environ)
    e["DASHSCOPE_API_KEY"] = key
    out = []
    tot_raw = tot_eff = 0.0
    for i, text in enumerate(lines, 1):
        sid = "s%02d" % i
        raw_base = os.path.join(raw_dir, sid)
        # 兼容旧目录：vo/ 里已有的 mp3 直接搬成 raw，不重花积分
        legacy = os.path.join(vo_dir, sid + ".mp3")
        if not os.path.exists(raw_base + ".mp3") and os.path.exists(legacy):
            shutil.copy2(legacy, raw_base + ".mp3")
        lw = os.path.join(vo_dir, sid + ".words.json")
        if not os.path.exists(raw_base + ".words.json") and os.path.exists(lw):
            shutil.copy2(lw, raw_base + ".words.json")

        if a.force or not os.path.exists(raw_base + ".mp3"):
            r = subprocess.run([sys.executable, WS, "--voice-id", vid, "--model", model,
                                "--text-file", "/dev/stdin", "--rate", rate,
                                "--out", raw_base],
                               env=e, capture_output=True, text=True,
                               input=text + "\n")
            if r.returncode != 0:
                print("  ✗ %s : %s" % (sid, (r.stderr or r.stdout)[-300:]))
                sys.exit(1)

        # ★ 裁首尾静音再排轴（见 trim_silence 注释：不裁整条片凭空慢十几秒）
        d, head, tail = trim_silence(raw_base + ".mp3")
        tw = os.path.join(trim_dir, sid + ".wav")
        write_wav(tw, d)
        eff = len(d) / float(SR)
        raw_dur = probe_dur(raw_base + ".mp3")
        words = {}
        wp = raw_base + ".words.json"
        if os.path.exists(wp):
            words = json.load(open(wp, encoding="utf-8"))
            for wd in (words.get("words") or []):    # 词级时间戳跟着裁头一起前移
                if isinstance(wd.get("begin_time"), (int, float)):
                    wd["begin_time"] = max(0, int(wd["begin_time"] - head * 1000))
                    wd["end_time"] = max(0, int(wd["end_time"] - head * 1000))
        tot_raw += raw_dur
        tot_eff += eff
        out.append({"id": sid, "text": text, "dur": round(eff, 3),
                    "raw_dur": round(raw_dur, 3), "head": round(head, 3),
                    "tail": round(tail, 3), "wav": tw,
                    "mp3": raw_base + ".mp3", "words": words})
        print("  ✓ %s %.2fs → %.2fs（裁头 %.2f / 尾 %.2f）%s" % (
            sid, raw_dur, eff, head, tail, text))

    idx = os.path.join(a.outdir, "vo_index.json")
    json.dump(out, open(idx, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n语音合计 %.2fs（原始 %.2fs，裁掉 %.2fs）→ %s" % (
        tot_eff, tot_raw, tot_raw - tot_eff, idx))


# ---------------- mix ----------------

def to_wav(src, dst, sr=SR):
    if os.path.exists(dst):
        return
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ar", str(sr),
                    "-ac", "1", "-c:a", "pcm_s16le", dst], check=True)


def read_wav(p):
    w = wave.open(p, "rb")
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if w.getnchannels() > 1:
        d = d.reshape(-1, w.getnchannels()).mean(axis=1)
    w.close()
    return d


def write_wav(p, data):
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(data, -1, 1) * 32767).astype(np.int16).tobytes())


def trim_head(d, thresh=0.015, pre=0.02):
    """裁掉 TTS 自带的句首静音（50–150ms）—— 不裁画面就比声音早到"""
    if not (np.abs(d) > thresh).any():
        return d
    idx = int(np.argmax(np.abs(d) > thresh))
    if idx <= 0:
        return d
    return d[max(0, idx - int(pre * SR)):]


def trim_silence(path, thresh=0.015, pre=0.02, post=0.06):
    """裁掉句首 + 句尾静音，返回 (数据, 头静音秒, 尾静音秒)。

    ★ 这是极简版节奏的命门：云端 TTS 每句自带 0.1–0.3s 头静音 + 0.4–0.7s 尾静音，
      16 句就是十几秒。标准模式是整段合成、句间由模型自然衔接，不裁就显得极简版
      凭空慢一大截（相同文案实测差 10.9s）。"""
    tmp = os.path.join(tempfile.gettempdir(), "_trim_in.wav")
    if os.path.exists(tmp):
        os.remove(tmp)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-ar", str(SR),
                    "-ac", "1", "-c:a", "pcm_s16le", tmp], check=True)
    d = read_wav(tmp)
    a = np.abs(d) > thresh
    if not a.any():
        return d, 0.0, 0.0
    s = int(np.argmax(a))
    e = len(d) - int(np.argmax(a[::-1]))
    s = max(0, s - int(pre * SR))
    e = min(len(d), e + int(post * SR))
    return d[s:e].copy(), s / float(SR), (len(d) - e) / float(SR)


def rms_db(d):
    r = float(np.sqrt(np.mean(np.square(d, dtype=np.float64)))) if len(d) else 0.0
    return 20.0 * math.log10(max(r, 1e-6))


def bgm_pool():
    """曲池：assets/bgm/bgm_*（同名只取一份，优先 m4a）"""
    if not os.path.isdir(BGM_DIR):
        return []
    best = {}
    for f in os.listdir(BGM_DIR):
        low = f.lower()
        if not low.startswith("bgm_") or not low.endswith((".m4a", ".wav", ".mp3")):
            continue
        stem, ext = os.path.splitext(f)
        rank = {".m4a": 0, ".mp3": 1, ".wav": 2}.get(ext.lower(), 3)
        if stem not in best or rank < best[stem][0]:
            best[stem] = (rank, os.path.join(BGM_DIR, f))
    return [v[1] for _k, v in sorted(best.items())]


def pick_bgm():
    """轮换取曲，写回 _bgm_rotate.json —— 同批多条不会撞同一首"""
    pool = bgm_pool()
    if not pool:
        return None
    st = os.path.join(BGM_DIR, "_bgm_rotate.json")
    idx = 0
    try:
        idx = int(json.load(open(st)).get("idx", 0))
    except Exception:
        idx = 0
    p = pool[idx % len(pool)]
    json.dump({"idx": (idx + 1) % len(pool)}, open(st, "w"))
    return p


def duck_gain(vo, n, sr=SR, hop=0.01, thr=0.05, ratio=5.0, attack=0.025, release=0.380):
    """口播一出声就把 BGM 压下去、句间自动回升（与标准模式 sidechaincompress 同参）。
    在 100Hz 降采样序列上做 IIR，再插值回全长 —— 比逐采样循环快两个数量级。"""
    win = max(1, int(0.02 * sr))
    env = np.sqrt(np.convolve(np.square(vo.astype(np.float64)),
                              np.ones(win) / win, mode="same"))
    h = max(1, int(hop * sr))
    idx = np.arange(0, len(env), h)
    e = env[idx]
    g = np.ones_like(e)
    m = e > thr
    g[m] = (thr / np.maximum(e[m], 1e-6)) ** (1.0 - 1.0 / ratio)
    a_c, r_c = math.exp(-hop / attack), math.exp(-hop / release)
    cur, cur_out = 1.0, np.empty_like(g)
    for i, v in enumerate(g):
        c = a_c if v < cur else r_c        # 压下去要快，回升要慢
        cur = c * cur + (1.0 - c) * v
        cur_out[i] = cur
    full = np.interp(np.arange(len(vo)), idx, cur_out)
    if len(full) < n:
        full = np.concatenate([full, np.ones(n - len(full))])
    return full[:n]


def cmd_mix(a):
    tl = json.load(open(a.timeline, encoding="utf-8"))
    shots = tl["shots"]
    total = tl["total"]

    work = os.path.dirname(os.path.abspath(a.timeline))
    vo48 = os.path.join(work, "vo48")
    sfx48 = os.path.join(work, "sfx48")
    os.makedirs(vo48, exist_ok=True)
    os.makedirs(sfx48, exist_ok=True)

    n = int(round(total * SR)) + SR // 4
    mix = np.zeros(n, dtype=np.float32)

    # 1) 口播：每句贴到自己的起点（优先用 vo_trim 里已裁掉首尾静音的 wav）
    for s in shots:
        tw = os.path.join(work, "vo_trim", s["id"] + ".wav")
        if os.path.exists(tw):
            d = read_wav(tw)
        else:
            mp3 = os.path.join(work, "vo", s["id"] + ".mp3")
            if not os.path.exists(mp3):
                mp3 = os.path.join(work, "vo_raw", s["id"] + ".mp3")
            if not os.path.exists(mp3):
                sys.exit("[x] 缺配音 %s" % mp3)
            w = os.path.join(vo48, s["id"] + ".wav")
            to_wav(mp3, w)
            d = trim_head(read_wav(w))
        st = int(round(s["start"] * SR))
        en = min(n, st + len(d))
        mix[st:en] += d[:en - st]
    votrack = mix.copy()          # 闪避侧链要用「只有口播」的那条
    print("口播 %.2fs / %d 句" % (total, len(shots)))

    # 2) 贴纸弹入音（同帧，落地点在 0.06s）
    cnt = 0
    for i, s in enumerate(shots):
        if s.get("kind") == "full":
            continue
        name = s.get("sfx") or SFX_ROTATION[i % len(SFX_ROTATION)]
        vol = float(s.get("sfx_vol") or SFX_VOL)
        if name in SFX_SEMANTIC:                 # 语义键 → 真实文件 + 该语义的默认音量
            name, svol = SFX_SEMANTIC[name]
            vol = float(s.get("sfx_vol") or svol)
        src = name if os.path.isabs(name) else os.path.join(SFX_DIR, name)
        if not os.path.exists(src):
            print("  ! 缺音效 %s" % name)
            continue
        dst = os.path.join(sfx48, os.path.basename(name))     # 值可能带子目录，落盘要拍平
        if not os.path.exists(dst):
            to_wav(src, dst)
        d = read_wav(dst) * vol
        st = int(round((s["start"] + 0.06) * SR))
        en = min(n, st + len(d))
        if en > st:
            mix[st:en] += d[:en - st]
            cnt += 1
    print("贴纸音效 %d 个" % cnt)

    # 3) BGM：曲池轮换 + 自动配平 + 闪避（与标准模式同一套判据，别各走一套）
    bgm_path = None
    if a.bgm not in (None, "", "none", "off", "false"):
        bgm_path = pick_bgm() if a.bgm in ("auto", "random") else a.bgm
    if bgm_path and os.path.exists(bgm_path):
        b = os.path.join(sfx48, "bgm.wav")
        if os.path.exists(b):
            os.remove(b)
        to_wav(bgm_path, b)
        d = read_wav(b)
        reps = int(np.ceil(n / max(1, len(d))))
        d = np.tile(d, reps)[:n]
        off = BGM_OFFSET_DB if a.bgm_db is None else a.bgm_db
        gdb = (rms_db(votrack) - off) - rms_db(d)
        if a.bgm_db is not None:
            print("  BGM 音量: 手调 %.1fdB" % a.bgm_db)
        else:
            print("  BGM 配平: 口播 %.1fdB / BGM %.1fdB → 目标 %.1fdB（%+.1fdB）" % (
                rms_db(votrack), rms_db(d), rms_db(votrack) - off, gdb))
        d = d * (10.0 ** (gdb / 20.0)) * duck_gain(votrack, n, **BGM_DUCK)
        fi, fo = int(BGM_FADE_IN * SR), int(BGM_FADE_OUT * SR)
        if fi > 0:
            d[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
        if fo > 0 and fo < n:
            d[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)
        mix += d
        print("BGM %s" % os.path.basename(bgm_path))
    elif a.bgm not in (None, "", "none", "off", "false"):
        print("  ! BGM 不可用（%s）→ 本条不加" % bgm_path)

    peak = float(np.abs(mix).max())
    if peak > 0.95:
        mix *= 0.95 / peak
    print("峰值 %.2f" % peak)

    outwav = os.path.join(work, "mix.wav")
    write_wav(outwav, mix)

    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-i", a.video, "-i", outwav,
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-af", LOUD_CHAIN,
                    "-shortest", a.out], check=True)
    print("→ %s" % a.out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tts")
    t.add_argument("--texts", required=True)
    t.add_argument("--outdir", required=True)
    t.add_argument("--force", action="store_true", help="忽略已有 mp3，重新调云端合成")
    t.set_defaults(fn=cmd_tts)

    m = sub.add_parser("mix")
    m.add_argument("--timeline", required=True)
    m.add_argument("--vo", help="保留参数，路径已由 timeline 同目录推断")
    m.add_argument("--video", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--bgm", default="auto", help="auto=曲池轮换 / none=不加 / 或指定文件")
    m.add_argument("--bgm-db", dest="bgm_db", type=float, default=None,
                   help="缺省自动配平到口播 -10dB；给了数字则手调")
    m.set_defaults(fn=cmd_mix)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
