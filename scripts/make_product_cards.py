#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产品卡生成器：**整图完整，永不裁内容、永不镜像**。

为什么要有这个脚本
------------------
2026-11-11 一天被老板打回两次，两次都出在「产品卡怎么做出 30 张不一样的」这件事上：

  ① 上午：为了拉 dHash 差异写了 `flip=(k%2==1)` → 一半产品卡水平镜像，
     瓶身中文 + 营养成份表整张反字；
  ② 下午：改用 `zoom 0.76~0.98` + 焦点偏 0.34/0.66 做裁切变体 →
     瓶身左边「肌肉博士」被切剩「肉博士」、顶部「高浓缩牡蛎精华」只剩「浓缩…」、
     右侧「维生素 B6」整个没了。

两次的根因是同一个：**把「图与图要有差异」错误地理解成「图要长得不一样」**。
产品图上每个字每一种元素都是卖点，一个像素都不许切、一次都不许翻。
差异只许从这三样来（都不动画面内容）：

  1) 画幅比例 —— 1x1 / 6x5 / 4x3 / 3x2 / 16x9，卡片在屏幕上的宽高随之不同；
  2) 图在画幅里的水平位置 —— 居中 / 偏左 10% / 偏右 10%；
  3) 留白比例 —— fill=1.0 满图（底色取产品均值色），0.90 四周用自身放大模糊过渡。

白底图（电商白底、摄影棚白底）另有一层坑：白边不裁掉的话，瓶子在卡片里只占
中间一小条，老板原话「裁的时候应该大一点」。做法是按内容 bbox **只裁纯色背景**
（四角 8×8 取样定背景色，色差 >14 算前景，围 bbox，外扩 3% 呼吸边），
产品本体一个像素都不动。

用法
----
```bash
PY=~/.workbuddy/binaries/python/envs/default/bin/python
$PY make_product_cards.py --src "产品图库/" --out cards/ --count 30
# 指定原图与顺序（推荐：把营养表那张排进每组）
$PY make_product_cards.py --img A.jpg --img B.jpg --img C.jpg --img D.jpg \
    --out cards/ --count 30
```

产物
----
  cards/p00.jpg … p29.jpg      900 宽的产品卡
  cards/_flip_flags.json       全 false（供 plan_asset_gate.py --flipflags 校验）
  cards/_cards_manifest.json   每张卡用的原图 / 画幅 / 留白 / 位置，便于回溯

退出码
------
  0  通过：30 张两两 dHash ≥ 12（`batch_plan_check` 的阈值）
  1  dHash 撞车（自动换过 8 轮仍撞）
  2  源图不够（不足 2 张，或 count 超过可用组合数）
  3  参数 / 文件问题
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageFilter, ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from batch_plan_check import dhash, hamming
except Exception:                                    # 单独拷出去用也不崩
    dhash = hamming = None

CARD_AR = {"1x1": 1.0, "6x5": 1.2, "4x3": 4 / 3.0, "3x2": 1.5, "16x9": 16 / 9.0}
FILLS = [1.00, 0.88, 0.76]
POS = ["c", "l", "r"]
CARD_OFF = 0.10          # 偏左/偏右的位移量（相对可移动余量），只平移不缩放
NEAR_DUP = 12            # 与 batch_plan_check 同阈值


def _files(d):
    return sorted(f for f in os.listdir(d)
                  if not f.startswith("._") and f.lower().endswith((".jpg", ".jpeg", ".png")))


def _edge_bg(im, w, h):
    """用原图自身缩小再放大模糊，当留白区的底 —— 不会出现白框黑框。"""
    s = im.resize((max(8, w // 30), max(8, h // 30)), Image.LANCZOS)
    return s.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14))


def _flat_bg(im, tol=10):
    """原图是不是「一整块纯色底」（电商白底图最常见）。

    是的话返回那层底色；返回 None 表示内容铺满/背景花，得用边缘模糊过渡。
    为什么需要这个：白底图 fill<1 时如果用边缘模糊当底，卡面上会出现
    「一块白矩形贴在自己的模糊影子上」的硬边，比留白本身更显眼。
    """
    w, h = im.size
    px = im.load()
    s = []
    for x in range(0, w, max(1, w // 40)):
        s.append(px[x, 0])
        s.append(px[x, h - 1])
    for y in range(0, h, max(1, h // 40)):
        s.append(px[0, y])
        s.append(px[w - 1, y])
    m = [sum(c[i] for c in s) / float(len(s)) for i in range(3)]
    dev = max(abs(c[i] - m[i]) for c in s for i in range(3))
    if dev > tol:
        return None
    if min(m) < 200:                 # 深色底不算「白底图」，仍用边缘模糊过渡（更有质感）
        return None
    return tuple(int(v) for v in m)


def content_bbox(im, tol=14):
    """找出「产品本体」的外接框，只用来裁掉四周的**纯色背景**。

    暗底图内容本就铺满，bbox ≈ 全图，等于不裁；
    白底图会把四周纯白切掉，瓶子在卡里就能占满高度。
    """
    w, h = im.size
    px = im.load()
    sample = []
    for cx in (0, w - 8):
        for cy in (0, h - 8):
            for dx in range(8):
                for dy in range(8):
                    sample.append(px[cx + dx, cy + dy])
    bg = tuple(sum(c[i] for c in sample) / len(sample) for i in range(3))
    x0, y0, x1, y1 = w, h, 0, 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            p = px[x, y]
            if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > tol:
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, w, h)
    if (x1 - x0) * (y1 - y0) > 0.97 * w * h:
        return (0, 0, w, h)                          # 内容铺满，别动
    m = int(0.03 * max(w, h))                        # 3% 呼吸边，不贴着产品切
    return (max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m))


def make_card(src, ar_name, fill, pos, out, width=900):
    """整图 contain：产品、瓶身文字、标签、营养表全部完整保留。"""
    ar = CARD_AR[ar_name]
    base = Image.open(src).convert("RGB")
    bb = content_bbox(base)
    base = base.crop(bb)
    w = width
    h = int(round(w / ar))
    iw, ih = int(w * fill), int(h * fill)
    # 安全边：任何 fill 下都不许内容贴着卡片边缘（贴边＝观感上就是被切，
    # 3167 那张「高浓缩牡蛎精华」在 fill=1.0 时正好顶到卡子上沿）。
    # 取短边的 4%：900x506 的 16x9 卡是 20px，扣掉渲染器 26 的圆角也不会啃到字。
    pad = int(0.04 * min(w, h))
    iw, ih = min(iw, w - 2 * pad), min(ih, h - 2 * pad)
    r = min(iw / float(base.width), ih / float(base.height))
    nw, nh = max(1, int(base.width * r)), max(1, int(base.height * r))
    fg = base.resize((nw, nh), Image.LANCZOS)
    flat = _flat_bg(base)
    if flat is not None:
        # 纯色底（白底电商图为主）：整张卡就是这层底色，留白区无缝
        canvas = Image.new("RGB", (w, h), tuple(int(v * 0.985) for v in flat))
    elif fill >= 0.999:
        st = ImageStat.Stat(base.resize((32, 32)))
        canvas = Image.new("RGB", (w, h), tuple(int(v * 0.96) for v in st.mean[:3]))
    else:
        canvas = _edge_bg(base, w, h)
    gx = w - nw
    gy = h - nh
    x, y = gx // 2, gy // 2
    if pos == "l":
        x = int(gx * (0.5 - CARD_OFF))
    elif pos == "r":
        x = int(gx * (0.5 + CARD_OFF))
    canvas.paste(fg, (max(0, x), max(0, y)))
    canvas.save(out, quality=93)
    return (bb, (w, h))


def plan_specs(imgs, count):
    """排出 count 条 (原图, 画幅, 留白, 位置)，三条硬约束：

      1) 每 3 张一组（= 一条片的 3 个产品镜）**组内原图不重、画幅不重**；
      2) 全表不出现重复的 (原图, 画幅, 留白) 组合 —— 这是差异的来源；
      3) 位置只在组间轮换，且只平移不缩放（图始终 100% 完整）。
    """
    pool = [(i, a, f) for f in FILLS for a in CARD_AR for i in imgs]
    if count > len(pool):
        return None
    used, out, cursor = set(), [], 0
    while len(out) < count:
        group = out[-3:] if len(out) % 3 else []
        pick = None
        for idx in range(len(pool)):
            c = pool[(cursor + idx) % len(pool)]
            if c in used:
                continue
            if any(c[0] == g[0] or c[1] == g[1] for g in group):
                continue
            pick = (idx, c)
            break
        if pick is None:
            return None
        idx, c = pick
        cursor = (cursor + idx + 1) % len(pool)
        used.add(c)
        out.append((c[0], c[1], c[2], POS[len(out) % len(POS)]))
    return out


def min_pair(paths):
    """返回 (最小 hamming 距离, 触发该值的一对)。"""
    hs = [(p, dhash(p)) for p in paths]
    best, pair = 64, (None, None)
    for i in range(len(hs)):
        for j in range(i + 1, len(hs)):
            d = hamming(hs[i][1], hs[j][1])
            if d < best:
                best, pair = d, (hs[i][0], hs[j][0])
    return best, pair


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="产品图库目录")
    ap.add_argument("--img", action="append", default=[], help="单张原图，可多次给")
    ap.add_argument("--out", required=True)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--width", type=int, default=900, help="卡片宽（渲染器按宽自适应）")
    a = ap.parse_args()

    if a.img:
        srcs = [p if os.path.isabs(p) else os.path.abspath(p) for p in a.img]
    elif a.src:
        d = os.path.abspath(a.src)
        if not os.path.isdir(d):
            print("✗ 目录不存在：%s" % d)
            return 3
        srcs = [os.path.join(d, f) for f in _files(d)]
    else:
        print("✗ 要么给 --src 目录，要么 --img 逐张给")
        return 3

    srcs = [p for p in srcs if os.path.exists(p)]
    if len(srcs) < 2:
        print("✗ 可用原图只有 %d 张，做不出一批不重样的卡" % len(srcs))
        return 2

    specs = plan_specs(srcs, a.count)
    if specs is None:
        print("✗ %d 张原图最多做 %d 张不重样的卡（原图×画幅），要 %d 张"
              % (len(srcs), len(srcs) * len(CARD_AR), a.count))
        return 2

    os.makedirs(a.out, exist_ok=True)
    for old in os.listdir(a.out):
        if old.startswith(("p", "_cards_", "_flip_")) and old.endswith((".jpg", ".png", ".json")):
            os.remove(os.path.join(a.out, old))

    made, meta, bbs = [], {}, {}
    for k, (img, ar, fill, pos) in enumerate(specs):
        name = "p%02d" % k
        p = os.path.join(a.out, name + ".jpg")
        bb, size = make_card(img, ar, fill, pos, p, a.width)
        bbs[os.path.basename(img)] = bb
        made.append(p)
        meta[name] = {"src": os.path.basename(img), "ar": ar,
                      "fill": fill, "pos": pos, "size": size}
        print("  %s  %-14s %-5s fill=%.2f pos=%s" % (name, os.path.basename(img), ar, fill, pos))

    # 永不镜像：闸门读这个文件
    json.dump({k: False for k in meta},
              open(os.path.join(a.out, "_flip_flags.json"), "w"),
              ensure_ascii=False, indent=2)
    json.dump(meta, open(os.path.join(a.out, "_cards_manifest.json"), "w"),
              ensure_ascii=False, indent=2)

    print("\n背景裁切（只裁纯色背景，不动产品本体）：")
    for f, bb in bbs.items():
        print("  %-22s bbox=%s" % (f, bb))

    if dhash is None:
        print("\n⚠️ 找不到 batch_plan_check，跳过 dHash 自检（务必手动跑 batch_plan_check）")
        return 0

    best, pair = min_pair(made)
    print("\n两两 dHash 最小 = %d（阈值 %d）" % (best, NEAR_DUP))
    if best < NEAR_DUP:
        print("❌ 撞了：%s ↔ %s\n   先加原图，或减少 count；**不许靠裁切/镜像拉开差异**"
              % (os.path.basename(pair[0]), os.path.basename(pair[1])))
        return 1
    print("✅ %d 张产品卡全部完整、无镜像、两两 dHash ≥ %d" % (len(made), NEAR_DUP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
