# 转场与淡入淡出清单（2026-10-28 灿爹验收）

> 背景：原流水线只有 push_left/right/up/down + flash + cut 五种，灿爹原话
> 「两个分镜之间的转场，不是向左移移镜就是向右移移镜，有没有其他好一点的转场啊」。
> 以下 21 种是 2026-10-28 做过 demo、灿爹看过并确认保留的。
> 唯一被否掉的是 **coverup（覆盖上移）** —— 别再用。

## 一、转场族（镜头之间，硬切换过去）

| 编号 | 名称 | xfade transition | 性格 | 建议用法 |
|---|---|---|---|---|
| T00 | 直线推镜 | —（现 overlay 位移） | 没亮点 | 仅兜底 |
| T01 | 叠化 fade | `fade` | 最柔、最慢 | 少用，节奏会拖 |
| T02 | 水平模糊溶 | `hblur` | **最顺，接缝几乎看不见** | **主力，占 60~70% 切点** |
| T03 | 圆形开洞 | `circleopen` | 从中心炸开 | 亮产品、揭晓时刻 |
| T04 | 径向旋转 | `radial` | 旋转漩涡，冲击最强 | 转折句（如「这坑我自己踩过」） |
| T05 | 垂直开合 | `vertopen` | 上下分开像睁眼 | 中等强度，可偶尔用 |
| T06 | 像素化 | `pixelize` | 马赛克再还原 | 偏潮流，年轻向，少用 |
| T07 | 横向切片 | `hlslice` | 显示器撕裂/错位 | 轻微故障感，偶尔用 |
| T08 | 整幅擦除 | `wipeleft` | 新画面从一侧擦过来 | 段落切换 |
| T09 | 斜切 | `diagtl` | 斜线扫过 | 比横平竖直有味道 |
| T10 | 风扫 | `hlwind` | 带拖影横扫 | ⚠️ 人物镜头会重影，慎用 |
| T11 | 去色过渡 | `fadegrays` | 先褪成灰再回色 | 章节感，开场/收尾 |

**已否决**：`coverup`（覆盖上移）—— 灿爹明确不要。

## 二、淡出族（「淡」这一类，不是推/擦/切）

### A. 镜头之间淡过去

| 编号 | 名称 | 实现 | 说明 |
|---|---|---|---|
| F1 | 黑场过渡 | 三段式：A `fade=t=out` → 纯黑 hold 0.12s → B `fade=t=in` | **必须三段式**，见坑① |
| F2 | 白场过渡 | 同上，`color=white` | `fade` 的 `color` 参数必须指定，见坑② |
| F3 | 颗粒溶解 | `xfade=dissolve` | 有颗粒感的溶解 |
| F4 | 慢叠化 | `xfade=fadeslow` | 长融，适合情绪段落 |
| F5 | 缩小淡出 | A `zoompan` z→0.74 露黑底 + `xfade=fade` | 推远收掉，适合收尾 |
| F6 | 模糊溶解 | A `gblur=sigma=16` 在转场窗口 enable + `xfade=fade` | 最看不见接缝 |
| F7 | 上飘淡出 | A overlay 上移 -170px 露黑底 + `xfade=fade` | 老电影换卷感 |

### B. 单个分镜自己的淡入淡出

| 编号 | 名称 | 实现 | 说明 |
|---|---|---|---|
| F8 | 单镜淡入 | `fade=t=in:st=0:d=0.55` | 从黑渐显，用于开场/新段落第一镜 |
| F9 | 单镜淡出 | `fade=t=out:st=T-0.62:d=0.62` | 渐隐到黑，用于收尾 |

## 三、落地踩过的坑（别再踩）

1. **xfade 的 offset 铁律**：必须 `offset <= len(A) - duration`。
   A 素材要**比转场起点长一个转场时长**：A=1.56s / offset=1.20 / dur=0.36 ⇒ 输出 2.70s。
   最初让 A 正好 1.2s、offset=1.2，输出被砍到 1.57s（drop 35 帧）。

2. **白场淡入必须写 `color=white`**：`fade=t=in` 默认从**黑**渐变，
   不写的话白场后面会突然闪一帧黑。

3. **xfade 的 `fadeblack`/`fadewhite` 不能当黑场/白场用**：
   实测纯色峰值只维持 2 帧（0.06s），肉眼等于没有，观众只觉得"闪了一下"。
   真黑场必须三段式，纯色至少 hold 0.10~0.14s。

4. **zoompan 的 `fps` 必须写在参数里**：`d=1:s=WxH:fps=30`。
   写成链上的 `...,fps=30` 会按 zoompan 默认 25fps 输出，素材被拉长 1.2 倍。

5. **`geq` 表达式别写复杂多参函数**：`hypot(a,b)`、`if(gt(a,b),x,y)` 会报
   "too many args"，反而 `min/max` 多层嵌套正常。

6. **`rgbashift` 的 rh/bh 不接受 t 表达式**，只吃静态数值，要衰减得用多段 enable。

7. **zoomin（xfade）不能用在主体占满画面的素材**：放大过头整屏只剩一片纯色。

8. **demo 千万别拿成片截段做**：成片字幕已烧进像素，两段拼转场会看到两条字幕
   重叠，那是假象。真实渲染 `build_ad_video.py:2661` 是 `[vpre]subtitles=ass`
   最后统一叠字，转场在字幕之前 —— 切点处字幕是瞬切、不参与转场。

## 四、推荐配比（别整片只用一种）

- **60~70% 切点 → T02 水平模糊溶**（句内拆镜、相邻同类镜头，保持句子完整）
- **20% 切点 → T08 / T09 / T05 轮换**（段落切换：痛点→解法、生活→产品）
- **10% 切点 → T03 / T04 / T11**（亮产品用圆开，转折用径向，开场收尾用去色）
- **淡出族不参与常规切点**，只用在三个地方：开场（F8）、收尾（F9/F5）、
  大段落转折（F1 黑场 / F2 白场）

## 五、demo 生成器（技能内置）

```bash
python ~/.workbuddy/skills/koubo-ad-video/scripts/make_transition_demos.py \
  --out ./demo --src-a 图A.jpg --src-b 图B.jpg          # 换品类只改这两个路径
python .../make_transition_demos.py --out ./demo --only fades   # 只做淡入淡出
```

产出：`T00~T12.mp4`（转场，10 号留空因 coverup 否决）、`F1~F9.mp4`（淡出）、
`转场候选_总览.mp4`、`淡入淡出候选_总览.mp4`、两张形态对比图。

**选素材铁律**：A/B 要**一暗一明、构图差异大**（本片用「健身房举铁」→「实验室 SGS」），
否则暗场转暗场、主体占满画面的那种，转场形态根本看不出来（zoomin 曾因此整屏只剩一片纯绿）。
两图尺寸不必一致，脚本会统一到 1920×1080。

---

## 已落地（2026-10-28）：`build_ad_video.py` 的 `xf` 模式

配置写 `"transition": {"mode": "fx", "dur": 0.34, "cuts": ["hblur", "radial", ...]}` 即可，
`cuts` 长度 = 镜数 − 1，每项是上面清单里的名字；写不够长时按 `default`（缺省 hblur）补齐。
`coverup` 已否决，别写。

### 它怎么解决当年 xfade 被弃用的两个坑

| 坑 | 现象 | 解法 |
|---|---|---|
| 链式累积截断 | 每处重叠吃掉 A 尾 T 秒 + B 头 T 秒 ⇒ 每处少 T，第 2~3 处 offset 超界，**画面第 7 秒整段消失**（音频还在） | **B 头部 `tpad` 冻结 T 秒**，offset 取「累积长 − T」⇒ 输出长 = (acc−T)+(T+L) = acc+L，逐级严格闭合 |
| 每处丢 ~1 帧 | 取整误差逐级累积，最终总长漂移 | 每级 xfade 后 `tpad` 兜 0.2s + `trim=end_frame=<精确帧号>` + `setpts=PTS-STARTPTS`，用**帧号**而不是秒来闭合 |

### 黑场 / 白场怎么做（xfade 原生 fadeblack 不可用）

`fadeblack` 的纯色峰值只维持 2 帧（0.06s），肉眼等于没黑。现在写成：
**极短 xfade（T=0.06）+ A 尾 `fade=t=out` + B 头 `fade=t=in`**，
A 的末段保持纯色 + B 的首段保持纯色，两段相加 ⇒ 实测停住 0.23s，亮度 13（黑）/ 中心 255（白）。

### 三个必须知道的坑

1. **`fade=t=in` 要写 `color=white`**，默认从黑渐变，白场后会闪一帧黑。
2. **`alimiter` 会整条延后 attack 时长**（实测 attack=5 → 晚 238 采样 ≈ 5ms），必须加 `latency=1`，
   否则混完音效音画错开 5ms（拿差值法测会误判成「音效全片都有」，实际是对齐没做）。
3. **转场不影响字幕**：字幕是 `[vpre]subtitles=ass` 最后统一烧的独立层，
   排在转场之后，切点处是瞬切、不会跟着画面一起位移或叠化。

### 特效层不跟转场，也不跟淡出（已知限制，两条都栽过）

卡片 / 圆环 / 重点字是最后 overlay 的独立视频层，由 remotion 渲完后叠在**底片之后**：

1. **不参与转场**：别把 `fadeblack`/`fadewhite` 排在卡片显示的时段上（会看到「画面白了但卡片还在」）。
   排之前先查 `fx_spec_*.json` 里各卡的 `startSec/durSec`。
2. **不参与淡出**（2026-10-28 实测）：`outro_fade` 已做在 `[vsub]`（字幕烧完之后）本该没问题，
   但 fx 层还是在 pipeline 后面才叠上去 ⇒ 末帧画面全黑了，**「更优惠」红字还亮着**。
   ⇒ **片子带 fx 层（卡片/圆环/重点字）时不要用 `intro_fade`/`outro_fade`**，
   要做得把 fade 放到 pipeline 叠完 fx 之后的最后一步（还没做，别在没验证的情况下开）。



---

## 六、21 种 → 配置名对照（照这张表写 `cuts`）

| 清单编号 | 配置里写 | 落在代码里的做法 |
|---|---|---|
| T00 推镜 | `push_left`/`push_right`/`push_up`/`push_down`（仅 `mode=mix` 可用） | overlay 位移，零重叠 |
| T01~T12 | `fade` `hblur` `circleopen` `radial` `vertopen` `pixelize` `hlslice` `wipeleft` `diagtl` `hlwind` `fadegrays` `dissolve` | xfade 原生，一条 `xfade=transition=<名>` |
| T00 保底 | `smoothleft` | xfade 原生平滑左移 |
| F1 黑场 | `fadeblack` | **极短 xfade(0.06) + A 尾 fade out + B 头 fade in** |
| F2 白场 | `fadewhite` | 同上，`color=white` |
| F3 颗粒溶解 | `dissolve` | xfade 原生 |
| F4 慢叠化 | `fade`（T=0.40） | xfade 原生 |
| F5 缩小淡出 | `zoomout` | A 侧 `zoompan` z→0.74 露黑 + `xfade=fade` |
| F6 模糊溶解 | `blurdissolve` | A 侧 `gblur=sigma=16` 在转场窗口 enable + `xfade=fade` |
| F7 上飘淡出 | `driftup` | A 侧 `pad`+`crop` 上移露黑 + `xfade=fade` |
| F8 单镜淡入 | `"intro_fade": 0.55`（全局，只作用首镜） | 首镜 `fade=t=in`，已改到字幕之后 |
| F9 单镜淡出 | `"outro_fade": 0.62`（全局，只作用末镜） | 末镜 `fade=t=out`，已改到字幕之后 |

> ⚠️ **F8/F9 只在「没有重点字/卡片/圆环」的片子上可用**。fx 层在 pipeline 里最后才叠，
> 淡出管不到它（实测末帧画面全黑、「更优惠」红字还亮着）。详见下面「特效层不跟转场，也不跟淡出」。


**F5/F6/F7 三条的实现要点**（2026-10-28 移植，已用两镜小样验过）：

- 它们只动 **A 侧**，不改 xfade 时长 ⇒ 总长、字幕轴、动效轴全不受影响。
- `zoomout` 的 `zoompan` 必须写 `d=1:s=1920x1080:fps=30` 三个参数，
  `fps` 写在链上（`...,fps=30`）会让它按默认 25fps 输出、素材被拉长 1.2 倍（见坑④）。
- `driftup` 的 `crop` 用动态 `y` 表达式时**不要写 `:eval=frame`** —— ffmpeg 9.0 的 crop
  没有 `eval` 选项，会报 `Option not found`。crop 的 y 表达式默认就是逐帧求值。
- 三者与 `fadeblack`/`fadewhite` 互斥（黑场要求 A 尾静止），同一个切点别叠加。
- 单镜 `F8/F9` 与黑/白场天然不冲突：首镜没有前一个切点、末镜没有下一个切点。


---

## 七、实战配比：「更柔和的转场」怎么落（2026-10-30 小绿人诺特烟酰胺 v3）

灿爹原话：**「转场用更加柔和的转场，我记得我改过一次」**。
上一版仍在 `mode:"mix"` + `push_left/push_up` 交替 —— 那是 overlay 位移，观感永远是「整幅推过去」。
「改过一次」= 2026-10-28 姜黄素那条换成 `mode:"fx"`（xfade 叠画）。

**改法：`mode` 一律 `fx`，`cuts` 按性格分配，`pulse:0`。**

```json
"transition": {"mode":"fx","dur":0.34,"pulse":0,"start_fade":0,
  "cuts":["hblur","hblur","radial","wipeleft","dissolve","fadegrays",
          "circleopen","diagtl","vertopen","hblur", "..."]}
```

本片 23 个切点定稿分布（柔和优先）：

| 手法 | 数量 | 放在哪 |
|---|---|---|
| `hblur` 水平模糊溶 | 14（61%） | 句内拆镜、相邻同类镜 —— 主力，接缝最看不见 |
| `fadegrays` 去色 | 2 | 痛点→解法（「学费交大了」→「图一个帅」）、收尾 |
| `wipeleft` 整幅擦 | 2 | 段落切换（进「照镜子」、转回「跟我一样练得狠」） |
| `radial` 径向 | 1 | 情绪加重（碳水没亏 → 微量元素欠账） |
| `dissolve` 颗粒 | 1 | 崩坏特写（颗粒感正好贴「建模受损」） |
| `circleopen` 圆开 | 1 | 产品揭晓（仰角双举瓶光爆） |
| `diagtl` / `vertopen` | 各 1 | 复配成分、CTA 揭晓 |

**三条纪律**

1. **不要整片只用一种**（灿爹否过「不是左移就是右移」），也**不要每个切点都换花样**——
   变来变去会晕。`hblur` 占 6 成是「柔和」的地基，其余只在情绪拐点上换。
2. **别排黑白场**：`fadeblack`/`fadewhite` 是 0.22s 纯色停留，片子里带卡片/重点字时
   会出现「画面黑了卡片还亮着」（特效层不跟转场）。要段落感用 `fadegrays` / `wipeleft`。
3. **`pulse` 与 `start_fade` 同时写 0**：`pulse` 管 mix 模式的切点提亮（白闪来源），
   `start_fade` 管正片开头黑起（镜1 是明亮素材时会把封面→黑→亮吃成 V 型）。

**验收数据（本片）**：`filter_debug.txt` 里 `xfade=transition=` 计数 = 切点数×2；
转场窗口 = `offset`–`offset+T`（**正片内时间**，成片要 +0.5s 封面）；
全片 >18 亮度跳变 1 处（且是变暗）、峰值 158（白闪门槛 230+）；相邻镜相似度最高 0.76。

---

## 八、同素材续接的接缝（2026-10-30 灿爹拍板「视频时长够就不用强行切」）

**场景**：同一段视频要覆盖相邻两镜/两句，且不想让画面切开。做法是预裁 A/B 两段（B 的源起点 = A 覆盖的素材量），接缝处转场设成 1 帧。

```json
"transition": {"mode":"fx","dur":0.34,"pulse":0,"start_fade":0,
  "cuts":[{"kind":"hblur","dur":0.0334}, "hblur", {"kind":"hblur","dur":0.0334}, "radial", "..."]}
```

**为什么不用 `"cut"`**：`cut`/`none`/`hard` 只在 `XF_MODE=="mix"` 分支实现（build_ad_video.py 1702 行，overlay 覆盖式）；`fx` 模式走 xfade，会把 `cut` 原样传给 `xfade=transition=cut` ⇒ ffmpeg 报错。**fx 片子里要硬切就用 1 帧 `hblur`**（0.0334 = 1/30 s），素材连续时混合的是相邻两帧，肉眼等同硬切，且不影响累积帧号。

**段 B 起点公式**：`shot_bounds[k+1][0] - shot_bounds[k][0]`（镜 k 的显示时长，含句间停顿），
不是 `bounds[k][1]-bounds[k][0]`——后者少算停顿，接缝会提前 0.3~0.5s 跳帧。

**验收**：接缝前后各 1.4s 抽帧算相邻帧灰度差，接缝处不得出现 > 中位数×2.5 的尖峰。
261029 v5 实测 2.37s 接缝：42 帧 Δ 中位 11.4、最大 16.3；6.72s 接缝中位 6.2，唯一峰 21.2 落在 7.00s（素材自身推镜 + 字幕换句，非接缝）。

---

## 九、★mix 模式「cuts 为空 / 全是 cut·flash」会静默冻帧（2026-11-01 修）

**现象（诺特烟酰胺 v1，11 镜，`{"dur":0.28,"mode":"mix","cuts":[],"pulse":0}`）**：
渲染 exit=0、总时长正好 35.67s、字幕逐句正常推进、QC 三项全 PASS ——
**但画面从镜 3 起整段冻在镜 2 那一帧**，一路冻到片尾。

**为什么查不出来**：
- `filter_debug.txt` 里 `tpad=start_mode=clone:start_duration=` 与
  `overlay=...enable='gte(t,...)'` 的数值**完全对得上**（起点 2.641 / 使能 2.664…），
  从滤镜图看一点错没有，只有抽帧才看得见。
- QC 只抽 4 帧（2×2），第 2 帧以后本来就已经在冻的那段里，四格全像是同一张图也不报警。

**根因**：mix 分支给每个切点都发一条
`[acc][vN]overlay=x=0:y=0:eval=frame:enable='gte(t,cum-0.10)'`。
硬切/闪光切时第二路 `x=0,y=0` 是**整幅覆盖**，叠加 `eof_action=repeat` 后
从第二处起整条 overlay 链静默失效（第二路不再出图）。

**修法（已进 build_ad_video.py，别再退回）**：
mix 模式下先判断 `_plan` 里有没有 `push*`。
- **有 push** → 原 overlay 位移链（这段才是 overlay 真正的用途）。
- **没有 push（全是 cut / flash）** → 直接 `concat=n=N:v=1:a=0`，
  闪光脉冲照旧由 `CUT_KIND → eq=brightness` 那条链打上。
  concat 的时长严格等于 Σ镜长，字幕轴零影响。

**硬切/闪光切到底该用哪个模式**：

| 想要的观感 | 写法 |
|---|---|
| 干净的硬切 | `{"mode":"mix","cuts":["cut","cut",...],"pulse":0}`（走 concat） |
| 硬切 + 白闪 | `{"mode":"mix","cuts":[],"dur":0.28}`（全 flash；⚠️ 灿爹明确嫌闪眼睛，别默认用） |
| 真正的叠画转场 | `{"mode":"fx","dur":0.34,"pulse":0,"cuts":[...]}`（首选，见第七节） |

**fx 模式下写 `"cut"` 是安全的**（✓ 2026-11-01 实测）：`FX_PRESETS["cut"]=(None,0,0,0)`，
`_ty or "fade"` 会退化成 **1 帧 fade**，等同硬切且不影响累积帧号 ——
第八节「fx 里不能写 cut，会报错」那句已过时，不必再手写 `{"kind":"hblur","dur":0.0334}`。

**验收闸门（交付前的硬动作）**：成片按 `shot_bounds` 每镜取中点帧（**成片记得 +0.5s 封面**），
压缩到 64×36 灰度、去均值归一化后算**空间相关**：全片任意两镜 < 0.90 才算 11 张互不相同。
⚠️ 别用**直方图**相关当判据 —— 实测两个完全不同的暗场镜头（卷播尾帧 vs 杠铃弯举）
直方图相关 = 1.00，会把正常片判成冻帧。参照值：本片最像的一对 镜4 vs 镜8 = 0.63。
只抽 4 帧的 QC 靠不住。
