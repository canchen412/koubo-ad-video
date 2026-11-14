# koubo-ad-video · 带货口播成片自动化 Skill

一套跑在 [WorkBuddy](https://www.workbuddy.cn) 里的 **Agent Skill**：给一段带货口播文案，自动完成分镜规划 → 配音 → 卷播片头 → 底片合成 → 字幕动效 → 音效 → 质检 → 出片，输出 16:9 1080P 成片＋标题＋话题标签。

不是「一键生成视频的 SaaS」，而是把一条带货短视频的生产流程（含 170+ 个校验闸门和踩过的坑）写成可执行的规则与脚本，交给 Agent 按规则跑。

---

## 一、它解决什么

写一条带货口播视频，真正耗时的不是剪，是**判断**：这句话该配几镜、这镜用 2 秒还是 4 秒、这张图会不会和上一条撞、这个产品图上的功效词要不要先 P 掉、封面这一帧有没有人物、重点字配哪个音效、这批两张片开头像不像。

这套 Skill 把这些判断固化成两类东西：

| 类型 | 形态 | 作用 |
|---|---|---|
| **规则** | `SKILL.md`（1.3MB）＋ `references/` 43 篇 | 什么情况该怎么判、哪些是硬红线 |
| **闸门** | `scripts/` 171 个脚本 | 带退出码的自动检查，exit 1 就不许往下走 |

设计原则只有一条：**规则写进文档 ≠ 会被执行，每条硬规则都要配一个带退出码的闸门。**

---

## 二、流水线

```
文案
 ├─ 0  素材扫描      video_first_scan.py    图库里有没有现成视频镜（视频优先，无匹配再配图）
 ├─ 1  分镜规划      shot_plan.py           按配音实测时长定镜数（图片镜可快切、视频镜不跟）
 ├─ 2  配音          cosyvoice_batch.py     逐句合成 + 裁真静音拼接（不是整段切）
 ├─ 3  时间轴对齐    align_vo.py            whisper + 拼音强制逐字对齐
 ├─ 4  片头          build_banner*.py       卷播 / 标准黑板 / 无片头
 ├─ 5  底片合成      build_ad_video.py      字幕、重点字、音效、运镜、BGM 闪避
 ├─ 6  封面          add_cover_frame.py     3:4 竖幅贴到 16:9 首帧（平台裁切正好命中）
 └─ 7  质检          check_*.py / deliver_check.py   34 项自检，FAIL 不许交付
```

一条命令串完全程：`scripts/pipeline_run.py`。

---

## 三、目录

```
koubo-ad-video/
├── SKILL.md                 主规则书（Agent 的入口，含变更日志与铁律）
├── INDEX-跨账号.md          组件索引：动效分工 / spec 示例 / 渲染命令
├── references/              43 篇细则（分镜、动效、配音、封面、字幕、素材安全…）
├── scripts/                 171 个脚本 + brand_TEMPLATE.json
└── assets/
    ├── remotion_templates/  Remotion 动效组件（tsx 源码，卷播 3D / 点击涟漪 / 数据可视化）
    ├── rem3d_src/           动效组件 canonical 源码
    ├── caption_fx/          字幕效果候选 demo（html，可直接在浏览器看）
    ├── textfx/ sfx*/        音效与文字特效的映射表
    └── toks.json            逐字时间轴示例
```

---

## 四、环境要求

- macOS（部分脚本用了 Vision 框架做抠图，需 `pyobjc-framework-Vision`）
- Python 3.11+（开发环境 3.13）
- **ffmpeg / ffprobe**（必装，85 个脚本调用）
- Python 包：`numpy` `Pillow` `opencv-python` `scipy` `soundfile` `psutil`
- 可选：`openai-whisper` + `torch`（逐字对齐；不用可走估算时间轴）
- 可选：阿里百炼 CosyVoice API Key（云端配音，`DASHSCOPE_API_KEY`）

```bash
pip install numpy Pillow opencv-python scipy soundfile psutil
brew install ffmpeg
```

---

## 五、安装

```bash
git clone https://github.com/<your-account>/koubo-ad-video.git \
  ~/.workbuddy/skills/koubo-ad-video
```

WorkBuddy 会自动识别 `~/.workbuddy/skills/` 下的用户级 Skill，对话里说「小绿人」「剪口播视频」「发文案出片」即可触发。

---

## 六、素材盘约定

脚本里的路径都指向同一个素材根目录。本仓库统一写作 `/Volumes/素材库/广告视频/`，请按这个结构准备（或全局替换成你自己的路径）：

```
/Volumes/素材库/广告视频/
├── 分镜图库/<IP名>/<品类>/<品牌>/图片/     分镜底图（按「大类_具体画面_景别」命名）
├── 分镜图库/<IP名>/<品类>/<品牌>/视频素材/  现成视频镜
└── 产品图库/<品牌>/<产品>/                 产品详情图、包装图
```

命名规范与检索逻辑见 `references/` 与 `scripts/index_product_library.py`。素材库建好索引后可一句话定位产品图：

```bash
python3 scripts/index_product_library.py --rebuild
python3 scripts/index_product_library.py --match "品牌 产品名"
```

---

## 七、品类配置

每个品类/款型一份 `scripts/brand_<品类>.json`，驱动整条流水线。仓库只提供模板：

```bash
cp scripts/brand_TEMPLATE.json scripts/brand_myproduct.json
# 改 brand / product / workspace / shots / cover_frame 等字段
```

字段含义见模板内 `_README` 与 `SKILL.md`「品类配置」节。

---

## 八、未包含的内容

为了让仓库保持纯文本、可读、无版权风险，**以下二进制素材没有上传**，需自备：

| 缺失 | 说明 |
|---|---|
| `assets/fonts/` | 字幕与重点字字体（约 60MB）。代码默认字体名可在 config 里用 `kw_font` / `sub_font` 覆盖 |
| `assets/bgm/` | BGM 曲池（约 33MB，版权归原作者）。放 `assets/bgm/bgm_*.wav` 即可被自动随机选用 |
| `assets/sfx/` `assets/sfx_爆款叙事音效/` | 音效采样。映射表已保留，补齐音频文件即生效 |
| `assets/voice/` | 音色克隆参考音频 |
| `assets/cover/` | 默认封面图 |
| `assets/bg_library/` | 动态背景预设（视频文件） |
| `scripts/brand_*.json` | 各品类作业配置（含真实工程路径），改用模板新建 |
| `assets/product_library_index.json` | 本机素材库索引，跑一次 `index_product_library.py --rebuild` 即可重建 |

补齐后脚本即可完整运行；缺哪个，对应的闸门会明确报「文件不存在」。

---

## 九、关于本仓库的脱敏

本仓库是从真实生产环境导出的公开版本，已做身份级脱敏：

- 真实姓名 / 昵称 → `老板` / `作者`
- 本机绝对路径 → `/Users/yourname/…`
- 素材盘路径 → `/Volumes/素材库/…`
- 本地作业配置、素材索引、缓存、备份文件 → 未上传
- 密钥类字符串 → 仓库内只有占位示例（如 `sk-...`），无任何真实 API Key、账号或 Cookie

仍保留的内容：**品牌名与产品名**（均为公开在售商品，用于说明 SKU 判定与素材归属逻辑）、**IP 形象名**、**部分参考价与素材清单**（教学示例需要上下文）。若你要二次公开，建议再按需隐去品牌信息。

---

## 十、免责与授权

- 代码与文档以 MIT 协议提供，可自由学习、修改、二次分发。
- 仓库内出现的品牌名、商标、产品包装描述归各自权利人所有，仅作技术示例，不构成任何背书或商业合作。
- 其中的口播文案片段、封面取景与平台发布策略为经验总结，**发布前请自行核对平台规则与广告法要求**（功效宣称、绝对化用语、赠品表述等）。

---

## 十一、几条值得单独拎出来的硬规则

这些是踩坑换来的，写在 `SKILL.md` 顶部当铁律：

1. **AI 生成素材一律 720P**，任何通道、任何时长都不升 1080P——积分花掉补不回来。
2. **默认 2 秒镜**，镜长靠变速适配（0.65–1.55x），不靠生成时卡点。
3. **配音逐句合成再拼接**，绝不整段合成后切音频补停顿（必切在字尾，听感「每句最后一两个字卡一下」）。
4. **封面只取有 IP 人物的分镜底图**，纯产品瓶图不合格。
5. **多条成片必须过跨片去重闸门**：开头首镜、首句、画面距离、背景全不许撞。
6. **素材未过水印扫描不进图库**：平台水印会漂移，抽 3 帧必漏，判定一律 ≥4 帧。
7. **产品图上的功效词必须先净化**（裁掉或 P 掉），整张是功效图就换图。
