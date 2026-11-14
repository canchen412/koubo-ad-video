# 背景库 `assets/bg_library`

24 个程序生成的动态背景，全部 numpy + PIL，**零素材、零 Remotion、0 积分**，8GB 内存友好。
2026-11-03 从 `_样片_信息卡_261101` 的四个实验室脚本收编，统一成一个库。

> ★ **默认走轮换，不再写死 `W7`**（老板 2026-11-03：「我的很多动态背景都可以用，**以后随机用上**」；
> 同一天后半句：「一次给你几条文案……**背景也不一样**」）。W7 仍是首选款之一，但一批 3 条就得是 3 张墙。

## 一、怎么用

```python
import sys; sys.path.insert(0, "~/.workbuddy/skills/koubo-ad-video/assets/bg_library")
from bg_lib import Background, random_preset

bg = Background("W7")            # 不传就走默认 W7
arr = bg.frame(t)                # np.uint8 (1080,1920,3)，一帧
```

命令行：

```bash
PY=/Users/yourname/.workbuddy/binaries/python/envs/default/bin/python
cd ~/.workbuddy/skills/koubo-ad-video/assets/bg_library

$PY render_bg.py --list                          # 看全部预设
$PY render_bg.py --preset W7 --still /tmp/w7.jpg # 出静帧
$PY render_bg.py --preset W7 --dur 12 --out /tmp/w7.mp4   # 出背景片（含颗粒）
$PY render_bg.py --all-stills                    # 重刷 preview/
```

**极简版成片里的用法**：一条片只 `Background(...)` 一次，整片复用同一个实例
（墙只放大一次，之后每帧只 crop）。**不要每帧 new 一个**，会慢 14 倍。

## 二、四组预设

### `comic_dark` 深底漫画分格墙（7 版）

| ID | 名字 | 特点 |
|---|---|---|
| W1 | 深炭·暖格线 | 基准款，最稳 |
| W2 | 深炭·主光移动 | W1 + 慢移柔光，最耐看 |
| W3 | 冷墨蓝 | 冷调，讲成分/原理/睡眠 |
| W4 | 墨线稿 | gamma 2.1 极高对比，最有漫画感，适合痛点爆发 |
| W5 | 深炭·色斑 | W1 + 环境色斑，信息量最满 |
| W6 | 暖纸压暗 | P4 暖纸墙压暗，保留纸质感 |
| **W7** | **斜贴分格** ★默认 | 每格轻微旋转 ±2~5°，像贴满墙的分镜小卡 |

### `comic_light` 浅纸漫画分格墙（5 版）

P1 暖纸米 / P2 冷灰蓝 / P3 暖橙 / P4 暖纸米·深格线 / P5 深炭。
浅底更柔和，但**绿人压不住画面**（这是转深底的直接原因）。

### `fx_dark` 深底纯动效（6 版）

D0 纯底（对照）/ DA 色斑 / DB 工程网格 / DC 光线扫 / DD 速度线 / DE 全套组合。
深底是**加法发光**，振幅 26~66。

### `fx_light` 浅底纯动效（6 版）

L0–LE 同上。浅底是**减法**，振幅只有 3~7（超过 5 就发脏）。

预览：`preview/总览_漫画分格墙.jpg`、`preview/总览_纯动效.jpg`。

## 三、跨片轮换（同批多条不撞墙）

**首选 `scripts/bg_rotate.py`**（不是 `random_preset`）—— 纯随机连抽会重复，也和前几天撞。它按
「**同批互斥 + 最久未用优先 + 平局随机**」挑，并自动记历史：

```bash
PY=/Users/yourname/.workbuddy/binaries/python/envs/default/bin/python
SK=~/.workbuddy/skills/koubo-ad-video

$PY $SK/scripts/bg_rotate.py pick --n 3 --note "肌酸批次派 3 条"   # → W2  W4  W6
$PY $SK/scripts/bg_rotate.py history -n 10                        # 最近用过什么
$PY $SK/scripts/bg_rotate.py pick --n 1 --group fx_dark           # 纯动效段
```

历史落在 `_bg_使用历史.json`（同目录，自动维护最近 60 条）。

> **plan.json 里的 `bg` 必须写显式预设**（`W2` 这种），**不许写 `"random"`** ——
> `random` 是渲染时才抽，抽完没人知道用了哪张墙、历史记不上、下一批必然撞。
> 出片前一批 plan 一起过闸：`scripts/batch_plan_check.py --plan a.json --plan b.json …`。

底层 API 仍在（想自己控制时用）：

```python
from bg_lib import random_preset
pid = random_preset("comic_dark", exclude=["W7", "W1"])   # 已用过的传进 exclude
```

## 四、改参数前必读（四条硬约束）

1. **逐格归一化**：16 张源图明暗差极大，套同一个线性映射会一块块深浅不一、看着像污渍。
   必须每格先 `norm_lum()` 把自己的灰度拉齐，再上配色。
2. **整墙只放大一次**：墙一次缩到 2880×1620 缓存，每帧只 `crop(1920×1080)`。
   逐帧 resize 慢 14 倍（510 帧 35s → 500s）。
3. **浅底上加法效果物理不可见**：浅底加 4~5 个亮度值≈2%，肉眼看不出来；网格/速度线在浅底是减法，
   深底再减等于没有。**深底一律加法，浅底一律减法，参数不能互相搬。**
4. **绿人抢色**：色斑里的墨绿会跟 IP 人物抢 → 绿 blob 的 amp ≤0.55、tint 用 `(8,24,16)`。

## 五、文件

```
bg_library/
├─ bg_lib.py        统一合成器（预设注册表 + Background + 环境光）
├─ render_bg.py     命令行（静帧 / 背景片 / 批量预览）
├─ preview/         24 张静帧 + 2 张总览
├─ _bg_使用历史.json 跨片轮换账本（bg_rotate.py 自动维护，别手改）
└─ _lab_orig/       四个实验室脚本原样留档（bg_lab / bg_dark_lab / wall_color_lab / wall_dark_lab）
```

`_lab_orig/` 是当初调参的现场，**不要再直接跑**（路径还指向临时工程），只作参数出处的证据。
