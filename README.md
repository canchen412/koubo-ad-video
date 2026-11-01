# 带货口播成片自动化技能

给 AI 助手用的**口播视频成片技能包**：输入一段产品文案，输出一条 16:9 1080P、带配音、逐字卡点字幕、音效和封面的带货口播片。

为快手/抖音的科普型带货口播设计：3 秒钩子 → 痛点 → 产品方案 → 卖点 → 信任 → 价格福利 → CTA。

> 这是技能定义（SKILL.md + 脚本 + 文档），不含字体、BGM、音效等二进制素材 —— 见下方「素材自备」。

## 它解决什么

单条口播片的重复劳动都在这些地方：分镜怎么切、图配得对不对、配音停顿自不自然、字幕卡没卡准、音效会不会撞、封面取哪一帧。全手工做一天两条，出错还得返工。

这个技能把这些固化成一条可复跑的流水线，加一批**硬闸门**：不满足条件直接报错中止，不靠人眼盯。

## 流水线

| 阶段 | 做什么 | 关键脚本 |
|---|---|---|
| P0 前置 | 内存水位预检、素材核验、扫视频池 | `preflight.py`、`video_first_scan.py` |
| P1 配音 | 云端 TTS 逐句合成 + 逐字时间戳对齐 | `tts_split_cloud.py`、`align_vo.py` |
| P2 分镜 | 按句切镜，镜数由配音时长配额决定 | `shot_plan.py` |
| P3 确认 | 出《分镜联络图》一次性交确认 | `storyboard_sheet.py` |
| P4 渲染 | 生图 → 写 config → 翻转守卫 → 合成 → 质检 | `pipeline_run.py`、`build_ad_video.py`、`flip_guard.py` |
| P5 交付 | 归档、回存图库、出标题与话题标签 | — |

一键跑完整链：

```bash
python3 scripts/pipeline_run.py --config <工程目录>/config.json
```

## 目录结构

```
SKILL.md                  技能主文件（触发条件、硬规则、参数约定）
INDEX-跨账号.md           组件索引：动效分工 / 渲染命令 / 铁律
references/               27 篇专题文档
  流程速查表.md             P0–P5 全流程与坑位索引
  出片后自检清单.md          28 条自检项 + 4 道闸门（唯一权威清单）
  三段结构规范.md            开头 / 科普 / 产品段的写法约束
  libtv_生成通道.md          AI 视频素材生成参数与成本口径
  remotion_动效层.md        3D 透视 / 点击涟漪等高级动效
  自建fx动效层_PIL逐帧.md     逐帧动效实现（含数字卡的尺寸配方）
  fx动效库.md / transitions.md / 字幕重点字动效模板.md / ...
scripts/                  150 个 Python 脚本
  pipeline_run.py          七步流水线主入口
  build_ad_video.py        渲染器（字幕、重点字、音效、混音、封面）
  video_first_scan.py      扫视频池，按文案粗筛候选
  check_batch_dedup.py     批量出片跨片去重闸门
  shot_uniqueness_check.py 相邻镜唯一性校验
assets/                   remotion 组件源码 + 配置模板（素材不入库）
```

## 几条硬闸门

这套东西的价值一半在文档，一半在这些"不许绕过"的检查上。

- **视频优先**：拿到文案先扫视频池，0 个视频镜时 `pipeline_run.py` 直接报错，不是警告。确实无视频才显式加 `--allow-no-video`。
- **批量去重**：一次出 ≥2 条时跑 `check_batch_dedup.py`，开头首镜、首句、画面距离都不许撞，同一张图禁止跨片复用，红了不许发。
- **相邻镜唯一**：`shot_uniqueness_check.py` 卡相邻镜的构图重复，避免平台判重复。
- **翻转守卫**：含文字或符号的图禁止镜像，渲染前 `flip_guard.py` 拦。
- **镜数配额**：图片镜下限 1.0s／门槛 1.2s，视频镜 1.2s／1.5s，单句封顶 4 镜；`shot_plan.py --config` 自检不过不出片。
- **配音质量**：逐句合成 + 裁真静音拼接，句间约 370ms 自然停顿；整段合成后再切音频补停顿这种做法，必然切在字尾上，已被明确禁止。

## 依赖

```bash
# 系统
ffmpeg            # 音视频合成，必须
python3           # 3.9+
macOS             # 部分脚本用 Vision 框架做本地抠图和 OCR

# Python
pip install pillow numpy
```

Remotion 动效层额外需要 Node.js（可选，只用 ffmpeg 路线可跳过）。

## 素材自备

仓库**不含**以下目录，需按自己的资源补齐。字体和 BGM 涉及授权，请使用你有权使用的版本。

```
assets/fonts/     字体 4 款：中文黑体（字幕正文）、手写体、标题体、重点字字体
assets/bgm/       背景音乐，命名 bgm_<曲名>.wav，脚本按曲池随机并避上一首
assets/sfx/       重点字音效约 12 款，按语义分配（点题/能量/数据/价格/警告/收尾…）
assets/cover/     默认封面图，3:4 竖幅
```

`assets/config.example.json` 里有全部参数和中文注释，可作起点。

素材根目录路径写在各品类配置 `scripts/brand_<品类>.json` 里，需改成自己机器的位置。

## 安装为技能

```bash
git clone https://github.com/canchen412/koubo-ad-video.git \
  ~/.workbuddy/skills/koubo-ad-video
```

补齐上面「素材自备」的目录后即可使用。复制 `assets/config.example.json` 为工程配置，改路径和产品信息。

## 声明

- 代码与文档可自由参考、修改。
- 不含任何第三方字体、音乐、音效文件。
- SKILL.md 里的工作流沉淀自实际投放经验，参数针对特定品类与账号调过，换品类需要重新标定。
