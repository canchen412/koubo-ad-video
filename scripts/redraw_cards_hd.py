# -*- coding: utf-8 -*-
"""把已有详情卡重绘成高清版 —— 保持原版式与配色，只把字号和分辨率提上来。

原卡 334x313 / 476x299，在 1920 画面里显示 450px 宽，字太小；
这里按 2.6~2.8x 重建，成片里卡片显示 500~540px 宽时字实际放大约 2 倍，且不靠插值。

用法：
    CARD_SRC_DIR="<产品图库目录>" python3 redraw_cards_hd.py
输出：<脚本所在目录>/cards_hd/hd_*.png（四周留 24px 透明阴影边）

踩过的坑（改之前先看）：
  · 原卡照片区下沿 y=309/358 已含圆角外的黑底 → 裁到 301/342，否则卡片底边带黑边
  · 原卡照片区上压着旧标签（「7个多柠檬」等）→ clean_photo() 局部虚化压掉，半径要 26
  · 配料卡旧字擦不净 → erase_text() 按暗像素整片擦 + keep_box 保瓶身
  · 虾青素卡底色是淡粉渐变、暗阈值抓不到旧字 → 直接铺干净渐变层再重排

配套（build_ad_video 侧）：
  · 卡片配置写在 <文案>.kw.json 的 product_cards，不在 cfg_*.json
  · <workdir>/cards/cards.json 的键是卡片原图绝对路径，且 vis_w/vis_h 只是逻辑尺寸
    ≠ 渲染尺寸：有 meta 时 PNG 原尺寸直接贴，必须先把 PNG 缩到目标尺寸再存
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

D = os.environ.get(
    'CARD_SRC_DIR',
    '/Volumes/陈灿会展/广告视频/烟酰胺/诺特新款/产品图库/')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cards_hd')
os.makedirs(OUT, exist_ok=True)

FB = '/System/Library/Fonts/Hiragino Sans GB.ttc'


def font(sz, idx=2):
    return ImageFont.truetype(FB, sz, index=idx)


PINK = (229, 52, 111)
INK = (43, 43, 43)
ICON_BG = (240, 120, 155)


def rounded_shadow(w, h, r):
    """带外阴影的透明画布，返回 (canvas, draw)"""
    pad = 24
    canvas = Image.new('RGBA', (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle(
        [pad, pad + 6, pad + w, pad + h + 6], radius=r, fill=110)
    sh = sh.filter(ImageFilter.GaussianBlur(16))
    canvas.paste(Image.new('RGBA', canvas.size, (150, 40, 80, 255)), (0, 0), sh)
    body = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle([0, 0, w - 1, h - 1], radius=r,
                                           fill=(255, 255, 255, 255))
    return canvas, body, pad


def cover(im, tw, th):
    """等比填满裁切"""
    s = max(tw / im.width, th / im.height)
    nw, nh = max(1, int(im.width * s + .5)), max(1, int(im.height * s + .5))
    im = im.resize((nw, nh), Image.LANCZOS)
    x = (nw - tw) // 2
    y = (nh - th) // 2
    return im.crop((x, y, x + tw, y + th))


def center_text(d, cx, cy, txt, f, fill, stroke=0, sf=None):
    bb = d.textbbox((0, 0), txt, font=f)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    d.text((cx - w / 2 - bb[0], cy - h / 2 - bb[1]), txt, font=f, fill=fill,
           stroke_width=stroke, stroke_fill=sf or (255, 255, 255))


def fit_group(d, txts, max_w, start, lo=34, idx=2):
    """同组统一字号：取能让最长的一条塞进去的字号，保证视觉齐整"""
    sz = start
    while sz > lo:
        f = font(sz, idx)
        if all(d.textbbox((0, 0), t, font=f)[2] <= max_w for t in txts):
            return f
        sz -= 2
    return font(lo, idx)


def fit_font(d, txt, max_w, start, lo=34, idx=2):
    """从 start 往下找能塞进 max_w 的最大字号"""
    sz = start
    while sz > lo:
        f = font(sz, idx)
        bb = d.textbbox((0, 0), txt, font=f)
        if bb[2] - bb[0] <= max_w:
            return f
        sz -= 2
    return font(lo, idx)


def clean_photo(src, box, tw, th, label_y):
    """裁出照片段；原卡压在上面的旧标签区域用「局部虚化」抹掉（散景感，肉眼看不修补痕迹），
    再整块等比放大到 tw×th。"""
    seg = src.crop(box).convert('RGB')
    y0, y1 = label_y
    m = Image.new('L', seg.size, 0)
    ImageDraw.Draw(m).rectangle([0, y0, seg.width, y1], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(6))
    blur = seg.filter(ImageFilter.GaussianBlur(26))
    seg.paste(blur, (0, 0), m)
    return cover(seg, tw, th)


def mirror_photo(src, box, tw, th, seam=0.63):
    """裁出照片段，下半用垂直镜像补齐；接缝落在 seam 比例处，正好被白标签压住。"""
    seg = src.crop(box)
    h1 = int(th * seam)
    h2 = th - h1
    top = cover(seg, tw, h1)
    bot = cover(seg.transpose(Image.FLIP_TOP_BOTTOM), tw, h2)
    ph = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    ph.paste(top, (0, 0))
    ph.paste(bot, (0, h1))
    return ph


# ───────────────────────── 两格卡（维C / 维E） ─────────────────────────
def two_cell():
    W, H = 935, 876
    cv, body, pad = rounded_shadow(W, H, 40)
    bd = ImageDraw.Draw(body)
    src = Image.open(D + '烟酰胺_维C维E两格卡_card_clean.png').convert('RGBA')

    cells = [
        dict(x0=0, x1=158, num='80mg', name='维生素C',
             tag='7个多柠檬', sub='(约363g)'),
        dict(x0=168, x1=332, num='16mg α-TE', name='维生素E',
             tag='2.28斤基围虾', sub='(约1142g)'),
    ]
    seam = 10
    cw = (W - seam) // 2
    for i, c in enumerate(cells):
        ox = i * (cw + seam)
        # 照片块：只取原卡标签**上方**的干净区（y166-234），镜像后铺满，避免旧标签残影
        photo = clean_photo(src, (c['x0'], 166, c['x1'], 301), cw, H - 330, label_y=(44, 132))
        body.paste(photo, (ox, 330))
        # 顶部数字（两格统一字号）
        f_num = fit_group(bd, [x['num'] for x in cells], cw - 34, 108)
        center_text(bd, ox + cw // 2, 96, c['num'], f_num, PINK)
        # 名称
        center_text(bd, ox + cw // 2, 186, c['name'], font(62), INK)
        # 图标
        cy = 268
        bd.ellipse([ox + cw // 2 - 36, cy - 36, ox + cw // 2 + 36, cy + 36],
                   fill=ICON_BG)
        center_text(bd, ox + cw // 2, cy - 4, '≈', font(52), (255, 255, 255))
        # 底部标签（白胶囊压在照片上）
        f_tag = font(46)
        bb = bd.textbbox((0, 0), c['tag'], font=f_tag)
        tw = bb[2] - bb[0]
        px, py = tw // 2 + 26, 34
        tcy = 690
        bd.rounded_rectangle([ox + cw // 2 - px, tcy - py, ox + cw // 2 + px, tcy + py],
                             radius=28, fill=(255, 255, 255, 242))
        center_text(bd, ox + cw // 2, tcy - 2, c['tag'], f_tag, PINK)
        center_text(bd, ox + cw // 2, tcy + 70, c['sub'], font(38), (58, 58, 58))

    cv.paste(body, (pad, pad), body)
    return cv


# ───────────────────────── 三格卡（维C / 烟酰胺 / 维E） ─────────────────────────
def three_cell():
    W, H = 1120, 800
    cv, body, pad = rounded_shadow(W, H, 40)
    bd = ImageDraw.Draw(body)
    src = Image.open(D + '烟酰胺_成分卡_16mg维C维E_card_w470.png').convert('RGBA')

    cells = [
        dict(num='80mg', name='维生素C', tag='7个多柠檬', sub='(约363g)'),
        dict(num='16mg', name='烟酰胺', tag='1.39斤玉米', sub='(约695g)'),
        dict(num='16mg α-TE', name='维生素E', tag='2.28斤基围虾', sub='(约1142g)'),
    ]
    # 原图三格：卡体 x24-500，照片区 y 190-358
    gap = 8
    cw = (W - gap * 2) // 3
    seg_w = (500 - 24) / 3.0
    ph_h = H - 300
    for i, c in enumerate(cells):
        ox = i * (cw + gap)
        x0 = int(24 + i * seg_w)
        x1 = int(24 + (i + 1) * seg_w) - 3
        photo = clean_photo(src, (x0, 188, x1, 342), cw, ph_h, label_y=(30, 118))
        body.paste(photo, (ox, 300))
        f_num = fit_group(bd, [x['num'] for x in cells], cw - 26, 92)
        center_text(bd, ox + cw // 2, 88, c['num'], f_num, PINK)
        center_text(bd, ox + cw // 2, 170, c['name'], font(56), INK)
        cy = 240
        bd.ellipse([ox + cw // 2 - 30, cy - 30, ox + cw // 2 + 30, cy + 30],
                   fill=ICON_BG)
        center_text(bd, ox + cw // 2, cy - 3, '≈', font(44), (255, 255, 255))
        f_tag = font(42)
        bb = bd.textbbox((0, 0), c['tag'], font=f_tag)
        px = (bb[2] - bb[0]) // 2 + 22
        tcy = 630
        bd.rounded_rectangle([ox + cw // 2 - px, tcy - 31, ox + cw // 2 + px, tcy + 31],
                             radius=26, fill=(255, 255, 255, 242))
        center_text(bd, ox + cw // 2, tcy, c['tag'], f_tag, PINK)
        center_text(bd, ox + cw // 2, tcy + 66, c['sub'], font(36), (58, 58, 58))

    cv.paste(body, (pad, pad), body)
    return cv


# ───────────────────────── 配料卡（瓶身 + 五处成分标注） ─────────────────────────
def erase_text(src, keep_box=None, th=165):
    """把原卡上的深色文字/注解线整片模糊擦掉（底图是柔和光晕，模糊填充看不出痕迹）。
    keep_box 内的区域（瓶身）不动，避免毁掉产品标签。"""
    im = src.convert('RGB').copy()
    arr = np.asarray(im).astype(int)
    m = (arr.max(axis=2) < th).astype(np.uint8) * 255
    if keep_box:
        l, t, r, b = keep_box
        m[t:b, l:r] = 0
    mask = Image.fromarray(m, 'L').filter(ImageFilter.MaxFilter(15))
    mask = mask.filter(ImageFilter.GaussianBlur(7))
    blur = im.filter(ImageFilter.GaussianBlur(80))
    im.paste(blur, (0, 0), mask)
    return im


def fit_in_box(d, txt, bw, bh, start=120, pad=10):
    """在 bw×bh 的框里找最大字号"""
    sz = start
    while sz > 16:
        f = font(sz)
        bb = d.textbbox((0, 0), txt, font=f)
        if bb[2] - bb[0] <= bw - pad * 2 and bb[3] - bb[1] <= bh - pad:
            return f
        sz -= 2
    return font(16)


def bottle_card():
    """配料卡：擦掉原卡标注 → 重新排版七个成分标注（字号按块自适应）。"""
    S = 2.7
    W, H = int(476 * S), int(299 * S)
    cv, body, pad = rounded_shadow(W, H, 48)
    raw = Image.open(D + '烟酰胺_配料卡_全成分_card_clean.png')
    # 瓶身保护区（原卡坐标）
    clean = erase_text(raw, keep_box=(150, 78, 336, 275))
    body.paste(clean.resize((W, H), Image.LANCZOS), (0, 0))
    bd = ImageDraw.Draw(body)

    # (文本, 中心x, 中心y, 框宽, 框高) —— 原卡坐标，按 S 换算
    items = [
        ('烟酰胺', 90, 40, 128, 44),
        ('雨生红球藻', 392, 33, 150, 42),
        ('虾青素', 392, 74, 150, 42),
        ('维生素C', 52, 130, 118, 44),
        ('维生素E', 52, 247, 118, 44),
        ('葡萄籽', 396, 200, 128, 42),
        ('提取物', 396, 240, 128, 42),
    ]
    for txt, cx, cy, bw, bh in items:
        x0 = int(cx * S - bw * S / 2)
        y0 = int(cy * S - bh * S / 2)
        w, h = int(bw * S), int(bh * S)
        x0 = max(6, min(x0, W - w - 6))
        y0 = max(6, min(y0, H - h - 6))
        plate = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(plate).rounded_rectangle(
            [0, 0, w - 1, h - 1], radius=min(h // 3, 24),
            fill=(255, 255, 255, 234), outline=(238, 146, 172, 255), width=3)
        body.paste(plate, (x0, y0), plate)
        f = fit_in_box(bd, txt, w, h, start=int(h * 0.9))
        center_text(bd, x0 + w // 2, y0 + h // 2, txt, f, INK)

    cv.paste(body, (pad, pad), body)
    return cv


# ───────────────────────── 虾青素瓶身卡（40μg 大字） ─────────────────────────
def asta_card():
    """虾青素瓶身卡：左侧铺干净的粉白渐变（彻底告别原卡旧字）→ 重排大字。"""
    S = 2.7
    W, H = int(476 * S), int(283 * S)
    cv, body, pad = rounded_shadow(W, H, 48)
    raw = Image.open(D + '烟酰胺_虾青素瓶身卡_card_clean.png')
    body.paste(raw.convert('RGB').resize((W, H), Image.LANCZOS), (0, 0))

    # 左侧渐变底（羽化右缘融入原图）
    gu, fe = int(172 * S), int(18 * S)
    grad = Image.new('RGB', (W, H))
    gd = ImageDraw.Draw(grad)
    for y in range(H):
        k = y / max(1, H - 1)
        gd.line([(0, y), (W, y)],
                fill=(int(255 - 3 * k), int(252 - 16 * k), int(253 - 9 * k)))
    m = Image.new('L', (W, H), 0)
    md = ImageDraw.Draw(m)
    md.rectangle([0, 0, gu, H], fill=255)
    for i in range(fe):
        md.line([(gu + i, 0), (gu + i, H)], fill=int(255 * (1 - i / fe)))
    body.paste(grad, (0, 0), m)
    bd = ImageDraw.Draw(body)

    x0 = int(28 * S)
    # 「40」大字
    f40 = font(int(62 * S))
    bd.text((x0, int(52 * S)), '40', font=f40, fill=(40, 40, 42))
    bb = bd.textbbox((x0, int(52 * S)), '40', font=f40)
    bd.text((bb[2] + int(5 * S), bb[1] + int(6 * S)), 'μg/份',
            font=font(int(23 * S)), fill=(116, 116, 120))
    # 成分名三行
    f_sub = font(int(19 * S))
    bd.text((x0, int(132 * S)), '雨生红球藻虾青素', font=f_sub, fill=(40, 40, 42))
    bd.text((x0, int(160 * S)), '微囊粉', font=f_sub, fill=(40, 40, 42))
    bd.text((x0, int(190 * S)), '（固体饮料）', font=f_sub, fill=(40, 40, 42))

    cv.paste(body, (pad, pad), body)
    return cv


if __name__ == '__main__':
    a = two_cell()
    a.save(os.path.join(OUT, 'hd_两格卡.png'))
    print('两格卡', a.size)
    b = three_cell()
    b.save(os.path.join(OUT, 'hd_三格卡.png'))
    print('三格卡', b.size)
    c = bottle_card()
    c.save(os.path.join(OUT, 'hd_配料卡.png'))
    print('配料卡', c.size)
    e = asta_card()
    e.save(os.path.join(OUT, 'hd_虾青素卡.png'))
    print('虾青素卡', e.size)
