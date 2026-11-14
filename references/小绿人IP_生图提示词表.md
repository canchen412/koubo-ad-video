# 小绿人 IP · 生图提示词表 v1.0

> **用法**：每条提示词 = **【强制前缀 P1+P2+P3+N】** ＋ **【下方创意正文】**，直接拼接。
> **适用**：Midjourney / DALL·E / Stable Diffusion / Flux / 即梦 / 可灵等任意生图工具。
> **建档**：2026-10-03 ｜ 依据 `koubo-ad-video/references/生图提示词模板.md` v2 ＋ 图库实战沉淀。

---

## 一、强制前缀（每次必带，四段）

### P1 · 画风与画幅
```text
2D Japanese anime thick-paint rendering, soft airbrushed gradients building the form,
light-to-shadow transitions are SOFT edges, NOT hard lines.
16:9 (1536x864), full-bleed artwork, no letterbox bars.
```

### P2 · IP 固定块（逐字复用，只换 POSE）
```text
CHARACTER: a muscular green-skinned male character, green skin with darker spider-web
vein texture, head FULLY COVERED by the green mask — absolutely NO hair, NO face,
NO mouth, NO nose, NO eyebrows. On the mask exactly TWO eye lenses and they are
SOLID PURE BLACK ovals (deep black glass, like two black holes), NO white sclera,
NO white outline, NO white Spider-Man style lenses. Black shorts, white wrist bands,
bare feet. Body build EXACTLY as reference image 1 — NOT chubby, NOT Q-version,
NOT skinny.
RENDERING LOCK: soft airbrushed 2D anime thick-paint EVEN UNDER DRAMATIC LIGHTING;
NO hard specular bars, NO hatching, NO black outlines around muscles, NO flat
cel-shaded color blocks, NO American superhero comic style, NO plastic CG/3D-render
look, NO glossy skin sheen.
```

### P3 · 构图与视频就绪（每次必带）
```text
COMPOSITION: subject at a golden-ratio intersection (never dead center), strong
diagonal energy flow, three depth planes (blurred foreground / sharp subject /
atmospheric background), generous clean negative space at the bottom quarter.
MOTION-READY: at least one element that can move — [见每条 CREATIVE 指定].
```

### N · 负向词（每次必带）
```text
NEGATIVE: NO text, NO watermark, NO logo, NO face, NO mouth, NO nose, NO hair,
NO extra limbs, no clutter, no busy background, no flat empty backdrop.
```

---

## 二、统一固定参数表

| 项目 | 固定值 |
|---|---|
| 画幅 | 16:9，1536×864（或 1920×1080），全出血无黑边 |
| 画风 | 2D 日系动漫厚涂（赛璐璐分色 + 柔和厚涂过渡 + 干净细线稿） |
| 体型 | 与定妆图一致，禁 Q 版 / 禁瘦 |
| 眼睛 | 恰好两只**纯黑椭圆**（深黑玻璃质感），**禁白眼球、禁白描边** |
| 面部 | **无脸、无嘴、无鼻、无眉、无发** |
| 服装 | 黑色短裤 + 白色腕带 + 赤脚 |
| 字幕留白 | 底部 1/4 净空，不得堆内容 |
| 标志光效 | 轮廓光 / 体积光束 / 逆光 / 放射爆光（每条至少一种） |
| 必备可动之物 | 蒸汽 / 飞溅 / 粒子 / 光束 / 烟雾 / 飘带 / 纸屑（每条 ≥1） |
| 物理真实性 | 道具必须被"使用"（坐→椅、靠→墙、手撑→肘有承托），脚下必须有接触阴影 |
| 通用负向 | 见 P4 段 |

---

## 三、提示词正文表

### A. 主视觉 / 封面（MV）

| 编号 | 使用场景 | 提示词正文（拼在强制前缀之后） | 镜头 / 运动建议 | 注意事项 |
|---|---|---|---|---|
| MV-01 | 片头主视觉、频道封面 | CREATIVE: low-angle hero shot, the character bursts upward out of a shattered black podium, both fists driving upward, torso twisted 20 degrees, head-mask tilted toward the light source. Explosive radiating light burst behind him, golden shards and dust spikes radiating outward, sparks blasting toward the camera. Deep black background with a single hot amber beam from above-behind. | 景别：仰拍全身。运动建议：镜头从低处快速推近（dolly-in + slight tilt up），冲击帧停在爆发瞬间；延续动效：金色碎片继续外飞、尘埃缓动。 | 16:9；底部留白 ≥1/4。强光影必查：肌肉若出现连续白色硬高光条＝画风漂移，重 roll。 |
| MV-02 | 品牌 Slogan 主 KV | CREATIVE: the character stands in profile at the exact center-left third, arms crossed, chest out, chin up, occupying only the left third; the entire right two-thirds is empty dark gradient with a single hard light shaft. Eye lenses catching one sharp cold glint. Fine dust motes drifting slowly through the shaft. | 景别：中景侧身。运动建议：极慢横移（truck right）＋呼吸式微推；右两-thirds 留白可叠标题。 | 留白区不得有任何元素；文字后期加，生成时禁 text。 |
| MV-03 | 竖版封面 / 短视频封面 | CREATIVE: extreme close-up of the eye lenses, two solid black glass ovals filling the left half of the frame, surface reflecting a tiny scene of a gym; the masked head is cropped by the top edge. Shallow depth of field, background completely dissolved into dark bokeh. A single rim light traces the mask edge. | 景别：大特写。运动建议：极慢推近至镜片（dolly-in），配合镜面高光扫过。 | 禁裁到眼睛以外；镜片**必须纯黑**，出现白色高光填充＝毁 IP。 |
| MV-04 | 联名主视觉 | CREATIVE: the character towers tiny at the bottom of frame, both hands on hips, looking up; above him an enormous floating object (partner product) looms and casts a huge shadow over him, scale contrast extreme. Volumetric god rays between them, floating particles. | 景别：极远景 + 渺小主体。运动建议：从巨物缓慢下降（tilt down）揭示小绿人，粒子持续漂浮。 | 巨物不得出现品牌文字；留白在顶部。 |
| MV-05 | 章节分隔图 | CREATIVE: the character in a half-kneel landing pose, one fist planted on the ground, cracks of light radiating outward from the contact point, ground dust kicked up behind him. Low camera at floor level, strong backlight. | 景别：贴地仰拍中景。运动建议：镜头贴地横移跟随裂纹扩散；冲击帧＝拳头触地瞬间。 | 拳头必须真触地（指节受力变形），脚下有接触阴影。 |

### B. 人物立绘与表情（PE）

> ⚠️ 小绿人**无脸**，情绪只能靠**身体语言 + 眼镜片光效**表达，**严禁写 smile / frown / 表情**。

| 编号 | 使用场景 | 提示词正文 | 镜头 / 运动建议 | 注意事项 |
|---|---|---|---|---|
| PE-01 | 自信/笃定 | CREATIVE: standing tall with chest out, one fist on his waist, weight on one leg in a relaxed power stance, mask tilted slightly down toward the camera; eye lenses half-lidded with one confident sharp highlight. Warm key light from upper left, soft fill, dark gradient background, faint dust. | 景别：中景。运动：缓慢推近至胸像；镜片高光缓慢移动。 | 禁写 facial expression；禁对称站桩。 |
| PE-02 | 惊讶/震惊 | CREATIVE: leaning back in shock, both hands raised to the sides of his head, shoulders tensed, body twisted in a dynamic startle pose, one foot lifted. Eye lenses glowing bright white with radiating shock lines. Hard single key light from below-front casting long upward shadows. | 景别：中近景。运动：镜头快速拉远（dolly-out）配合受惊节奏；冲击线闪动。 | 镜片高亮**不做白色填充**，只做外发光。 |
| PE-03 | 发力/燃 | CREATIVE: mid-action powerful pose, muscles tensed, arms bent in a flexing motion, dynamic diagonal body line, particles bursting around both fists, ground dust kicked up at the feet. Eye lenses blazing with white-hot glow. Explosive warm backlight with radiating rays. | 景别：中景仰拍。运动：镜头环绕半圈（arc shot）；粒子持续外爆。 | 强光影必查白色硬高光条。 |
| PE-04 | 疑惑/对比 | CREATIVE: scratching the side of his head with one hand, other arm spread out in a questioning gesture, head tilted, shoulders shrugged, weight on the back foot. Eye lenses with a small question-mark shaped highlight (graphic only, no text). Cool ambient with one warm practical light behind. | 景别：中景。运动：轻微推近 + 视差抖动；镜面高光一闪。 | question-mark **只能是光形**，禁生成文字符号。 |
| PE-05 | 开心/爽 | CREATIVE: both arms raised in a V-shape victory pose, mid-jump with both feet off the ground, body arched with pure energy, toes pointed, light debris falling from above. Eye lenses curved bright with sparkle highlights. Bright warm backlight, clean gradient sky-like backdrop. | 景别：全身仰拍。运动：镜头随跳跃上升（crane up）；碎屑持续下落。 | 起跳必须真离地（有地面接触阴影缺失的空中高度感）。 |

### C. 动作场景（AC）

| 编号 | 使用场景 | 提示词正文 | 镜头 / 运动建议 | 注意事项 |
|---|---|---|---|---|
| AC-01 | 力量爆发 | CREATIVE: gripping a barbell with both hands, fingers wrapped fully around the bar, arms bearing the load, body arched backward in a heavy lift; chalk dust and sweat droplets frozen in the air catching the rim light. Low camera at bar height, single hard side key light, deep black gym background. | 景别：中景贴地仰拍。运动：镜头从杠铃高度上摇（tilt up）到脸；汗珠与粉尘继续飘落。 | 手指必须**握住**杠铃（禁悬空/穿模）。 |
| AC-02 | 速度冲刺 | CREATIVE: sprinting at full lean 25 degrees into the direction of travel, one foot lifted, dust kicked up behind, motion blur trails behind the limbs, speed lines trailing. Cool blue dusk with a warm sun flare low behind; three depth planes of blurred stadium lights. | 景别：全景侧面跟拍。运动：横移跟随（truck right）+ 速度线延续；尘土持续扬起。 | 禁正面平视（速度感来自侧向 + 前倾）。 |
| AC-03 | 极限撑起 | CREATIVE: hanging from a pull-up bar, both hands overhand gripping, elbows locked, body swinging forward with residual momentum, muscles fully loaded, chalk dust falling. Dramatic top-back light through a dusty gym ceiling, deep shadow below. | 景别：全身远景仰拍。运动：镜头缓慢上升跟随身体摆动；粉尘持续洒落。 | 双手必须**抓在杠上**，肩肘承重关系正确。 |
| AC-04 | 爆发对撞 | CREATIVE: split-screen contrast in ONE frame: left half cold grey desaturated with him slumped and exhausted, right half hot amber with him mid-power-pose bursting outward, the dividing line a hard vertical light seam. Sparks only on the right half. | 景别：双人中景。运动：镜头缓慢横移跨过分屏线；右侧火花持续迸发。 | 分屏两侧**画风必须一致**（同模型同 seed 家族）；禁文字。 |
| AC-05 | 静态蓄力 | CREATIVE: standing motionless in perfect meditation balance, both feet on separate pedestals, arms out, eyes lenses dim with one thin bright line, dust falling vertically through a single overhead spotlight column, everything else in deep black. | 景别：全景正面。运动：极慢推近；垂直尘埃持续下落；光柱轻微呼吸。 | 平衡姿势禁歪斜；两只脚都要有承托与接触阴影。 |
| AC-06 | 落地冲击 | CREATIVE: landing from a jump in a deep squat, both feet planted flat and bearing weight, knees deeply bent, one hand touching the floor for balance, floor cracks radiating from the landing point with dust bursting outward. Ground-level camera, hard backlight, heavy shadow falloff. | 景别：贴地中景。运动：镜头随震动轻微抖动；灰尘持续扩散。 | 落地必须"承重"（膝踝压缩、脚掌贴地）。 |

### D. 场景环境（SE）

| 编号 | 使用场景 | 提示词正文 | 镜头 / 运动建议 | 注意事项 |
|---|---|---|---|---|
| SE-01 | 暗夜健身房 | CREATIVE: a moody dark gym at night, rows of dumbbells receding into blackness, single hard shaft of light from a high window cutting through haze, the character standing small at the edge of the shaft with arms at his sides, enormous shadow stretching toward camera. Dust motes dense in the beam. | 景别：大远景（人小景大）。运动：镜头沿光柱缓慢横移；尘埃持续漂浮、光柱轻微摆动。 | 人物占比小但**必须是剪影实体**（有体积不是贴纸）。 |
| SE-02 | 蒸汽厨房 | CREATIVE: a steaming kitchen counter, thick curling steam rising from a hot cup, water droplets and splashes suspended mid-air, warm morning light through a window cutting across; the character leans on the counter with ONE forearm fully supported by the surface, the other hand holding the cup, weight settled on both feet. | 景别：中景侧面。运动：镜头缓慢推近；蒸汽持续升腾（i2v 最友好）。 | 手臂必须**压在被子上**承重（禁肘部悬空）。 |
| SE-03 | 雨夜窗边 | CREATIVE: beside a rain-streaked window at night, rain trails running down the glass, blurred neon city bokeh far outside, the character standing with one shoulder against the window frame (weight borne by the wall), looking out, warm interior lamp light on his back, cool blue light on his front. | 景别：中景。运动：镜头缓慢侧移；雨滴持续下滑、bokeh 呼吸。 | 靠墙必须**肩部真实接触**墙面。 |
| SE-04 | 金色麦田 | CREATIVE: a sunlit field at golden hour, warm backlight, tall grass and floating pollen particles; the character stands with feet sunk slightly into the grass, arms open wide, mask tilted up toward the sun, long warm rim light outlining every muscle edge. | 景别：全景。运动：镜头缓慢环绕（arc）；草与花粉持续飘动。 | 逆光镜**必查白色硬高光条**。 |

### E. 产品与联名（PD）

| 编号 | 使用场景 | 提示词正文 | 镜头 / 运动建议 | 注意事项 |
|---|---|---|---|---|
| PD-01 | 产品英雄镜 | CREATIVE: the character stands on the LEFT half of the frame, full body visible, left hand resting on a dark pedestal; on the RIGHT third a large product sits on that pedestal, clearly separated from him with a clean gap. Warm key light from upper left, strong rim light on both, glowing amber halo behind the product, deep soft shadows, dark background. | 景别：中全景（人+物同框）。运动：镜头缓慢横移从人摇到物；产品区光晕呼吸。 | ★**角色与产品必须并排、不得前后叠放**（本项目实战踩过：瓶置于脸前会挡住角色）；产品标签文字须与参考图一致。 |
| PD-02 | 产品成分解析 | CREATIVE: a high three-quarter view of a dark slate table; a large product stands at the left third, one hand of the character rests on the table edge (forearm supported), his other hand gestures open-palm toward a small pile of glowing white crystalline powder beside the product, head-mask tilted down at the powder. Volumetric side light, deep background. | 景别：中景俯拍。运动：镜头沿桌面缓慢推进；粉末颗粒持续洒落。 | 产品必须完整在画面内（0–64% 安全区）；禁手遮挡产品。 |
| PD-03 | 开箱 / 到手 | CREATIVE: a top-down view of an opened shipping box on a warm wooden table, the product standing inside it, a folded document leaning against the box edge, tissue paper shreds still suspended in the air above the box, warm window light raking across. No hands, no people. | 景别：俯拍近景。运动：镜头缓慢下降（crane down）；纸屑持续飘落。 | 俯拍时**产品不得压画面边缘**；纸屑是唯一可动之物。 |
| PD-04 | 联名对比 | CREATIVE: two objects side by side on a dark reflective surface, the character standing behind them at a distance, one hand pointing down toward the gap between them, single hard top light creating long shadows toward camera, faint fog rolling along the surface. | 景别：中景俯视。运动：镜头缓慢推近；地面雾气持续流动。 | 联名双方产品**不得出现任何可读文字/商标**（除品牌方提供的主图）。 |
| PD-05 | 产品收尾定格 | CREATIVE: the product centered slightly above the middle with light emanating outward from behind it, upward energy, the character standing small at the lower left corner in a relaxed power stance looking at it, a wide clean pedestal front face filling the bottom quarter, golden light streaks radiating upward. | 景别：产品居中特写 + 人小。运动：镜头缓慢上摇；光芒持续向上扩散。 | 底部 1/4 只放干净台面（字幕区）。 |

### F. 周边延展（GR）

| 编号 | 使用场景 | 提示词正文 | 镜头 / 运动建议 | 注意事项 |
|---|---|---|---|---|
| GR-01 | 服装 /  merch | CREATIVE: a flat-lay product shot: a black athletic tank top and a pair of black shorts laid on a dark slate surface, the character standing behind them in the distance out of focus with arms crossed, single warm spotlight from above, fabric fibers catching the light, floating dust. | 景别：俯拍平铺 + 人虚化在后景。运动：镜头缓慢平移扫过平铺物；尘埃持续飘落。 | 服装**必须复刻 IP 配色**（绿肌 + 黑短裤 + 白腕带），禁改成其他配色。 |
| GR-02 | 表情包 / 贴纸 | CREATIVE: a close-up of the masked head tilted 30 degrees, one eye lens catching a bright crescent reflection, the other in shadow, a tiny sweat drop frozen beside the mask, clean bold background with a single diagonal light band. Extremely simple background. | 景别：头肩特写。运动：镜头极慢推近；汗滴持续下坠。 | 背景**必须极简**（贴纸要抠图）；禁任何文字。 |
| GR-03 | 头像 / 圆图 | CREATIVE: a centered symmetrical head-and-shoulders portrait, masked face straight to camera, both black eye lenses fully visible and identical, shoulders squared, single soft frontal key light with deep falloff, pure dark background, subtle vignette. | 景别：正面头肩。运动：仅呼吸式微动（0 积分动效即可）。 | 双眼必须**大小一致、对称**；背景纯色便于抠图。 |

### G. 社媒配图（SM）

| 编号 | 使用场景 | 提示词正文 | 镜头 / 运动建议 | 注意事项 |
|---|---|---|---|---|
| SM-01 | 知识长图头图 | CREATIVE: the character at the lower right corner in a relaxed power stance, pointing up-left with one finger; the entire upper-left two-thirds is clean dark gradient with one hard light shaft crossing it, floating particles concentrated near the shaft. Generous empty space for text overlay. | 景别：远景。运动：缓慢推近；粒子缓慢飘散。 | 文字区留空 ≥2/3；生成时禁 text。 |
| SM-02 | 九宫格切片 | CREATIVE: a vertical composition built for a 3:4 crop, the character in extreme foreshortening — one hand holding an object extremely close to the camera (huge in frame, blurred), his masked head small and sharp in the upper background, a hard light streak connecting them, dust between. | 景别：强制大透视（近大远小）。运动：镜头从近景物体缓慢后拉揭示人物（pull-back）。 | 近景物体**必须虚化**；主体人物在远景要清晰。 |
| SM-03 | 数据 / 对比图 | CREATIVE: a symmetrical split composition: left half cool grey and dim with him standing small and slouched, right half warm amber with him standing tall arms crossed; a hard vertical seam of light divides them, particles only on the right, floor fog along the bottom. | 景别：双全身对称。运动：镜头缓慢横移跨越分割线；右侧粒子持续迸发。 | 分屏两侧画风/体型/比例**必须完全一致**。 |

---

## 三之二、H 组 · 抠图专用（CUT）—— 这张图不是为了当画面，是为了抠成贴纸

> 老板 2026-11-03：「生成几张背景干净的图，小绿人图，用疑惑啊、震惊啊或者是健身的，
> 比较干净的背景，适合抠图的图片」。
>
> ⚠️ **A–G 组全部不适用**。它们是「整屏画面」规格：暗场、轮廓光、体积光束、粒子、四分之三留白 ——
> 这些恰恰是抠图的三条死因（光晕、背景残留、地面投影），拿它们抠出来的贴纸边缘发亮发毛。
> 从图库现有分镜里抠的贴纸之所以脏，根因就是这个。

### 八条硬规格

| # | 规格 | 为什么 |
|---|---|---|
| 1 | **纯浅灰无缝底 `#F2F3F2`**，无场景/无道具/无地面线/无地平线 | 浅底 × 深绿身体 = 色差最大，`keying.py` 一步到位；暗底会把肌肉暗部一起吃进背景 |
| 2 | **禁投影** | 投影是半透明灰，抠完人物脚下会留一圈脏边 |
| 3 | **禁轮廓光 / 逆光 / 体积光 / 粒子 / 尘埃 / 蒸汽** | 光和粒子会烧到背景，抠不干净；贴纸的层次感靠渲染器加压图阴影做，不靠原图 |
| 4 | **平光**：正面柔和均匀光，禁强高光和硬阴影 | 硬高光在缩放后会出现「闪条」 |
| 5 | **全身完整**，四周留 8% 空边，正面或 3/4 侧，无透视变形 | 贴纸要「平」地贴在墙上，大透视会跟漫画墙打架 |
| 6 | **四肢离开躯干**（腋下、腿间透出背景），手指张开 | 不分离也能按色抠，但分离能让 unmix 去溢更准、边缘更利 |
| 7 | 双脚平放落地 | 「踮脚」在贴纸里会像悬浮 |
| 8 | 竖版 **1024×1536** | 抠完统一缩到高 1032，跟库里其他贴纸同规格 |

### 提示词模板（照抄，只换 POSE 段）

```text
2D Japanese anime thick-paint character illustration, soft airbrushed gradients,
light-to-shadow transitions are SOFT edges, NOT hard lines. Vertical portrait framing.

CHARACTER: a muscular green-skinned male character, BRIGHT saturated vivid green skin
(clear mid-tone, not dark, not muddy, not shadowed), with darker spider-web vein texture.
Head FULLY COVERED by the green mask, same head shape as reference image 1 (smooth
egg-shaped mask, NO hair, NO ear) — absolutely NO face, NO mouth, NO nose, NO eyebrows.
On the mask exactly TWO eye lenses, SOLID PURE BLACK ovals, NO white sclera, NO white
outline, NO Spider-Man style lenses. Black shorts, white wrist bands, bare feet.
Body build EXACTLY as reference image 1 — NOT chubby, NOT Q-version, NOT skinny.
RENDERING LOCK: soft airbrushed 2D anime thick-paint; NO hard specular bars, NO hatching,
NO black outlines around muscles, NO flat cel-shaded color blocks, NO superhero comic style,
NO plastic CG/3D look.
SKIN TEXTURE LOCK: only soft irregular organic vein strokes — NO regular square grid,
NO mesh, NO wireframe, NO checker pattern, NO netline screentone.

POSE: <这里放飞姿态，只写身体语言，写清"读起来像哪句话"，
       并强调 the feeling must come from posture only, never from a face>

CUTOUT-READY SPEC (critical): isolated on a completely plain flat light neutral gray
seamless background (#F2F3F2), absolutely empty — NO scene, NO props, NO floor line,
NO horizon line, NO cast shadow on the background, NO glow, NO particles, NO dust,
NO steam, NO vignette. Even flat soft frontal lighting only, NO rim light, NO backlight,
NO volumetric light, NO strong specular highlights. Full body head-to-toe entirely inside
the frame with 8% empty margin on all four sides, three-quarter front view, no perspective
distortion, nothing cropped. Arms clearly separated from the torso with visible open gaps
at the armpits, legs apart with background visible between them, all fingers spread apart
and separately readable, feet flat on the ground.

NEGATIVE: NO text, NO watermark, NO logo, NO face, NO mouth, NO nose, NO eyebrows, NO hair,
NO white sclera, NO white eye outline, NO white-filled eyes, NO Q-version, no chibi,
NO chubby body, NO skinny body, NO busy background, NO dark background, NO gym equipment,
NO extra limbs, NO merged fingers, NO cropped feet.
```

调用时挂 `image1 = 一张现有干净贴纸`（`input_fidelity: high`）保体型与画风，
尺寸 `1024x1536`。**头型本来就该是尖蛋形**（像螳螂），别照「圆头像人类」去纠 —— 那是 IP 本身。

### 后处理三步（一步都不能省）

```bash
CUT="/Volumes/素材库/广告视频/分镜图库/小绿人/_抠图库"

# ① 抠图（纯色底引擎，输出统一高 1032、脚底对齐）
python3 "$CUT/_tools/keying.py" --src 新图.png --dst clean.png

# ② 剥白毛边（浅底会给轮廓留一圈浅浅的灰白，深色墙上一眼就能看出）
python3 "$CUT/_tools/edge_clean.py" --src clean.png --dst clean_净边.png

# ③ ★调色对齐（最容易漏的一步）——新生成的图偏暗偏黄，和老库贴纸并排像换了个人
python3 "$CUT/_tools/tone_match.py" --src clean_净边.png --dst 角色_xxx_全身_净边.png \
    --ref "$CUT/角色/展示_半蹲发力浅色_全身_净边.png"
```

**为什么必须 ③**：实测老库贴纸皮肤均值 `RGB(47,133,66)`（G−R＝86，纯亮绿），
新生成的是 `RGB(78,104,67)`（G−R＝26，偏黄发灰）。并排放就是「两个人」。
`tone_match.py` 只对绿色像素做通道比例映射（k 约 `0.65 / 1.35 / 1.05`），
黑短裤、白腕带、黑镜片不动，mask 羽化 5px 过渡。

> 水印不用管：ImageGen 会在右下角打「AI生成」，但它落在纯色背景区，
> `keying.py` 按底色抠的时候自然就排除掉了。

### 验收（5 条，逐条过）

1. 深色底（`#1A1A1E`）上放大 3 倍看边缘：**不许有一圈浅色毛边**
2. 和老贴纸并排：肤色亮度差 ≤ 15（`tone_match.py --stat` 可查）
3. 十指齐全、脚趾齐全，没有合并/缺损
4. 头型与老贴纸一致（尖蛋形），两只镜片纯黑
5. 双脚平放，不是踮脚/悬空

---

## 四、通用负面词（每条必带，可追加）

```text
NO text, NO watermark, NO logo, NO signature,
NO face, NO mouth, NO nose, NO eyebrows, NO hair,
NO white sclera, NO white eye outline, NO spider-man style lenses, NO white-filled eyes,
NO Q-version, no chibi, no chubby body, no skinny body,
NO hard specular highlight bars, NO black outlines around muscles, NO hatching,
NO flat cel-shaded blocks, NO American superhero comic style, NO netline screentone,
NO plastic CG look, NO 3D render, NO glossy skin sheen,
NO clutter, no busy background, no floating random objects,
NO product label garbled text, NO cropped-off product, NO logo on product
```

---

## 五、生成后自检（8 条，逐条问）

1. **脸**——出现嘴/鼻/眉/发 ⇒ 立刻重 roll（毁 IP，最严重）
2. **眼**——两只镜片是否**纯黑椭圆**且大小一致？出现白填充/白描边 ⇒ 重 roll
3. **站桩**——像证件照吗？双脚下垂、重心居中 ⇒ 重 roll
4. **物理**——画面里的椅子/桌子/杠铃真被"使用"了吗？有没有穿模/悬空/脚下无接触阴影 ⇒ 重 roll
5. **画风漂移**——肌肉上出现**连续白色硬高光条**、**闭合黑描边**、或**规则方网格/渔网纹** ⇒ 画风已漂向美漫/3D/wireframe，追加 RENDERING LOCK + SKIN TEXTURE LOCK 重 roll
6. **可动之物**——数一下有几处会动的东西？转视频的图必须 ≥1 处
7. **留白**——底部 1/4 是否干净可放字幕？主体是否在黄金分割而非死中心？
8. **记忆点**——这张有能截图记住的点吗？没有 ⇒ 换一种脑洞手法（尺寸反差 / 物理超越 / 时间切片 / 极端对比）

---

## 五之二、两个「必加段」补丁（2026-10-17 肌酸 v2 实锤，出图两版才过）

### SKIN TEXTURE LOCK（防皮肤方网格 / wireframe 漂移）
强逆光 + 广角的图，模型极易把「肌肉纹理」画成**规则方网格**（看起来像 3D 线框），整张图废。直接在 P1 画风之后插一段：

```
SKIN TEXTURE LOCK: the green skin carries only soft irregular organic vein strokes painted with an
airbrush — absolutely NO regular square grid, NO mesh, NO wireframe lattice, NO checker pattern,
NO netting, NO thin white or black contour lines tracing the muscles. Muscle edges must fade with
soft shading only.
```

负向词里再把 `regular grid pattern on skin / wireframe / mesh / netline screentone / checker texture / contour lines` 列一遍，双保险。

### EMPTY BOTTOM QUARTER（底部四分之一净空，硬约束）
只写「留白」不够——粉末、袋子、脚会照样压进字幕区。必须写成硬约束，并在负向词里禁一遍：

```
The bottom quarter of the frame is a dark, sharply out-of-focus empty floor — clean, uncluttered,
reserved for captions. No powder, no bag and no feet enter the bottom quarter of the frame.
```
```
NEGATIVE: ... NO objects or powder in the bottom quarter of the frame ...
```

---

## 六、跨工具参数建议


| 工具 | 建议参数 |
|---|---|
| Midjourney | `--ar 16:9 --style raw --stylize 250 --no text,watermark,face,white eyes`，角色垫图用 `--cref` + `--cw 100` |
| DALL·E | 直接用完整拼接串；角色一致性靠"逐字复用 P2" |
| SD / Flux | 尺寸 1536×864，CFG 6–7.5，steps 28–35，风格权重 0.85，垫定妆图 + 固定 seed |
| 即梦 / 可灵 | 画幅选 16:9，参考图上传定妆图，负面词照抄 P4 |

---

**⚠️ 与出片流程的关系**：本表是**素材生产工具**，产出的图入库后请按 `koubo-ad-video` 的三段式命名（`大类_具体画面_景别`）归档；进 config 前务必先过 `flip_guard.py`（含符号的图禁镜像）与「拼图核对」（文件名不可信）。

---

## 七、比喻镜 · 双重主体硬规则（2026-11-12 老板定，起草图必守）

> 原话：「他不能这一个图片就只是给合页在上油。肯定要有小绿人在旁边啊，哪怕他不作为主体，他在旁边也要用手指着。」

用「一个东西解释另一个东西」的镜头（合页=关节、管道=血脂、齿轮=代谢、电池=能量、水管=漏损、沙漏=时间、拼图=缺的那块、炉子=代谢率、砖墙=氨基酸、骨架=骨胶原），**不许只拍道具**，必须按下面五条写：

1. **A 侧是他**：他对应的身体部位（膝盖／腰腹／胸口／手背／背部／关节）占画幅 30–40%，皮肤、骨点、旧疤、青筋要看得清。
2. **B 侧是比喻物**：占画幅 30–40%。
3. **他本人在两者之间**，全身或半身入镜，**必须有一根手指明确指向 B 侧**（或触摸 B 侧），身体朝向 B、镜片朝 B。不许背对、不许当路人。
4. **必须写出一处「呼应」**：膝盖弯曲轴对准合页转轴／腰侧皮褶厚度对准管道里油脂层／背部凹陷形状对准拼图缺口／腹肌排列对准砖缝。**这条是整张图的说服力，写不出来等于没写。**
5. **同一束光**，暗部一致；不许一边亮一边死黑。

出图验收三项：① 那根「指过去」的手指在不在（不在就重跑，别修）；② 呼应线在不在（膝盖和合页高度必须对齐）；③ A 侧有没有被虚化或裁掉（裁掉就成了道具照）。

负向词必须补一句：`NO prop-only shot, NO character turned away or standing aside, NO missing pointing finger`。
