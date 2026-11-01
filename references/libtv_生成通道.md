# LibTV 生成通道（一律 720P · C Dance 2.0 Fast / Wan 2.7）

> ## ⛔ 铁律零：**分辨率永远是 720P，不许升 1080P**
>
> **灿爹 2026-11-01 22:36 原话**：「我不管让你生成两秒的还是四秒的 C Dance 还是两秒的 Wan 2.7，
> 你都用 720P 的，这样我消耗的积分更少你知道吗？」
>
> **适用范围：本通道任何模型、任何时长、任何镜别**（含产品特写、怼脸、封面）。
> `resolution` 只写 `"720p"`；写成 `"1080P"`＝直接烧掉成倍积分，属严重错误。
>
> **为什么这条要放在最前面**：2026-11-01 给镜14 生成 2 秒素材时，我因为下文那句旧建议
> （「特写主力可考虑 1080p」）自作主张用了 1080P，被灿爹当场指出。
> **720P 放大到 1080p 的软，靠本地锐化就可以补；积分花掉补不回来。**
> 真需要更清晰的画质（产品标签、包装文字），走「本地无损」路线——
> 用原图重绘/裁切，**不要去升生成分辨率**。
>
> **单位成本纪律**：动手前先按 720P 报价；只有灿爹明确说「这一镜我要 1080P」才升，并当场重报水位。

> **灿爹 2026-10-30 23:52 拍板**：「下一次我连接 LibTV，用 LibTV 去生成的话你也用同样的操作，
> 用 C Dance 2.0 Fast 生成 4 秒的 720P 的视频，你也这样操作」。
>
> **⇒ 只要连了 LibTV 要出视频素材，默认就走下面这套参数，不再问、不再试别的模型。**
> 首次跑通＝2026-10-30 小绿人×诺特烟酰胺「镜05 熬夜刷手机」，一次过、灿爹验收「这是全片提升最大的一处」。

---

## 〇、模型名对照（别找错）

| 灿爹口头叫法 | 平台真实 modelKey | 平台显示名 | aliasName |
|---|---|---|---|
| **C Dance 2.0 Fast** | **`star-video2-fast`** | **Seedance 2.0 Fast** | `2.0 Fast` |
| （同系列标准版） | `star-video2` | Seedance 2.0 | — |
| （同系列轻量版） | `star-video2-mini` | Seedance 2.0 Mini | — |

**「C Dance」＝「Seedance」的音译口称。** 在 `search_models` 里搜 `seedance` 或 `SD2.0 fast video` 都能命中，
但**不要按中文去搜**（搜不到）。图生图/文生图用 `lib-image-2.5-s`（显示名 Lib Image 2.5 S）。

---

## 一、固定参数（照抄，勿改）

### ① 首帧图（图生视频必须有干净首帧）

```json
{"toolName":"mcp__libtv__create_node","params":{
  "projectId":"<项目 id>",
  "name":"镜05 熬夜刷手机",
  "nodeType":"image",
  "model":"lib-image-2.5-s",
  "prompt":"以 {{Image 1}} 作为主角形象参考（保持其绿色皮肤、光滑面罩式无五官头部……完全一致）。\n\n16:9横屏电影分镜。……",
  "params":{"quality":"medium","resolution":"2K","ratio":"16:9","count":1},
  "left":["<主角定妆图节点 id>"],
  "run":true,
  "idempotencyKey":"<项目>-<镜>-<日期>-01"
}}
```

- **`left` 必须挂主角定妆图节点**，否则脸/身体比例会飘。
- 出图尺寸：**2K / 16:9 ⇒ 2048×1152**。
- `count` 严格按需要给 1，不要用模型默认值。

### ② 视频（**核心，灿爹定的那四条**）

```json
{"toolName":"mcp__libtv__create_node","params":{
  "projectId":"<项目 id>",
  "name":"镜05 熬夜刷手机 4s",
  "model":"star-video2-fast",
  "intent":"generate",
  "startFrameNode":"<上一步 image 节点 id>",
  "run":true,
  "params":{
    "ratio":"16:9",
    "resolution":"720p",
    "duration":4,
    "enableSound":"off",
    "count":1
  },
  "prompt":"以 {{Node <image节点id>}} 为首帧（角色形象严格以此为准），16:9 横屏电影级 3D 卡通渲染短片，4 秒，无人声无音乐。……",
  "idempotencyKey":"<项目>-<镜>-v4-fast-<日期>-01"
}}
```

| 参数 | 值 | 为什么 |
|---|---|---|
| `model` | `star-video2-fast` | C Dance 2.0 Fast |
| `resolution` | **`720p`** | 铁律零：永远 720P，任何模型任何时长都不升 |
| `duration` | **`4`** | 灿爹指定；**4s 刚好能裁出 2 个可用镜 + 1 个转场** |
| `ratio` | `16:9` | 成片时间线就是 16:9，免裁切 |
| `enableSound` | **`off`** | 成片音轨走云端配音+音效，素材带音轨反而要额外 `-an` |
| `startFrameNode` | 首帧 image 节点 | 锁死第一帧＝锁死角色 |

### ③ 输出实测规格（2026-10-30 实拍）

```
1280×720 / 24fps / 4.041667s / 97 帧 / h264 / 无音轨 / 2.78MB
```

⚠️ **720p 源进 1080p 成片要放大 1.5 倍，细节偏软——这是可以接受的代价，不许为此升 1080P。**
补法（都不花积分）：
1. 进片时走 `no_zoom:true` 避免二次推近（见 SKILL 闸门）；
2. 需要更锐就加一道 `unsharp=5:5:0.6` 再放大；
3. 产品包装/标签文字必须清晰时，**不要靠生成**——用产品图库原图本地重绘卡片（2026-10-30 已验证，
   见 `自建fx动效层_PIL逐帧.md`），那条路是像素级无损的。

---

## 二、调用顺序（8 步，含踩过的坑）

```bash
# 1) 先加载工具 schema（别凭记忆猜参数）
ToolSearch: ["mcp__libtv__doctor","mcp__libtv__list_projects","mcp__libtv__search_models",
             "mcp__libtv__get_model","mcp__libtv__create_node","mcp__libtv__task_status",
             "mcp__libtv__read_node","mcp__libtv__read_project","mcp__libtv__inspect_media"]

# 2) 连通性
mcp__libtv__doctor {}

# 3) 找项目（已有就复用，别每镜新建）
mcp__libtv__list_projects {}
mcp__libtv__read_project {"projectId":"<id>","view":"nodes"}   # 看已有哪些节点可当参考图

# 4) 确认模型还在（模型池是变动的，别硬编码）
mcp__libtv__search_models {"action":"search","nodeType":"video","durationSeconds":4,
                           "aspectRatio":"16:9","candidateLimit":5,"query":"seedance"}

# 5) 看 inputContract，确认 720p/4s 这组合被允许
mcp__libtv__get_model {"model":"star-video2-fast"}

# 6) 生图（run:true 直接跑）→ 轮询 → 读节点拿图 URL
mcp__libtv__create_node {...①...}
mcp__libtv__task_status {"project_id":"<id>","task_id":"<返回的 task_id>"}
mcp__libtv__read_node {"projectId":"<id>","node":"<nodeId>"}

# 7) 下载图 + 目视验收 + 给灿爹确认（这一步不能跳）
curl -sL "<read_node 返回的 image url>" -o gen/镜05_xxx.png

# 8) 生视频 → 轮询 → 读节点 → 下载 → ffprobe 验规格
mcp__libtv__create_node {...②...}
mcp__libtv__task_status {"project_id":"<id>","task_id":"<task_id>"}
mcp__libtv__read_node {"projectId":"<id>","node":"<video nodeId>"}
curl -sL "<video url>" -o gen/镜05_xxx_4s.mp4
ffprobe -v error -show_entries format=duration,size \
        -show_entries stream=width,height,avg_frame_rate,nb_frames -of default=nw=1 gen/镜05_xxx_4s.mp4
```

**硬规矩**

1. **URL 只能从 `read_node` 拿，不许猜路径。** 直链域名形如 `https://libtv-res.liblib.art/...`，`curl -sL` 即可。
2. **生视频前必须先把首帧图给灿爹看过。** 图废了视频一定废，一条视频的钱不能白烧。
3. **每次 `create_node` 都带 `idempotencyKey`**，重试才不会重复扣费。
4. 生成约 **2 分钟**（`estimatedTime: "2min"`），`task_status` 轮询别狂刷。
5. **积分**：4s/720p/Fast 实测记 **22 分/条**（区间 18–28，单价未定稿）。
   ⚠️ **2K 图片那张当时没单列记账**，下次生成前先按 `credit-guard` 报水位。

---

## 三、★一条 4s = 三条素材（这条最值钱）

**关键做法：提示词里把 4 秒明确切成「2 秒一个完整段落」。**

这次实测裁出三段，全都入了视频池：

| 时间 | 内容 | 归档名 |
|---|---|---|
| 0 – 1.4s | 贴地冲刺→怼屏，冷蓝光扫脸 | `情绪_凌晨刷手机怼屏特写_中景_AI动态.mp4` |
| 1.4 – 2.6s | 屏幕爆亮→液态化 | `转场_屏幕爆亮液态化_近景_AI动态.mp4` |
| 2.6 – 4.0s | 光液溢出→全屋失重→俯冲眼底 | `代价_光液失重全屋悬浮_全景_AI动态.mp4` |

```bash
# 裁段（-crf 18 保画质，必带 -an）
ffmpeg -y -ss 0    -t 1.4 -i 镜05_4s.mp4 -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -an A_怼屏.mp4
ffmpeg -y -ss 1.4  -t 1.19 -i 镜05_4s.mp4 -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -an 转场.mp4
ffmpeg -y -ss 2.6         -i 镜05_4s.mp4 -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -an B_失重.mp4
```

⚠️ **裁出来的段必须查是否撞脸**：B 段当时塞进句10 与镜05 同床同姿势，连着看像重播，被退回。
**一条 4s 的多个段不要放在相邻两句里用。**

---

## 四、提示词结构（这条一次过的写法，直接套）

```
以 {{Node <id>}} 为首帧（角色形象严格以此为准），16:9 横屏电影级 3D 卡通渲染短片，
4 秒，无人声无音乐。全片为一条连续运镜，由两个各自完整的段落组成，
段落之间以「<节拍事件>」的一瞬为节拍（约第 2.0 秒），不切镜、不闪白。

【A 段·0–2.0s｜<小标题>】
<起点机位 + 运镜方向 + 途经细节 + 终点落点>。
这一段的收尾是一帧稳定、干净、可独立使用的画面。

【B 段·2.0–4.0s｜<小标题>】
第 2.0 秒，<节拍事件>。<接续动作 + 运镜 + 终点>。
这一段的收尾是一帧稳定、干净、可独立使用的画面。
```

四个要点，缺一条就裁不出干净段：

1. **「以 Node xxx 为首帧，角色形象严格以此为准」** —— 不写角色会换脸。
2. **「4 秒，无人声无音乐」** —— 平台有时会自己加环境音。
3. **明确「不切镜、不闪白」** —— 否则段间给你硬切，裁出来的段头尾都是半截。
4. **每段都写「收尾是一帧稳定、干净、可独立使用的画面」** —— 这是能当独立镜用的前提。

---

## 五、常见错误

| 现象 | 原因 | 修法 |
|---|---|---|
| `search_models` 搜不到 | 用了中文「C Dance」 | 搜 `seedance` / `SD2.0 fast video` |
| 出来的视频带声音 | `enableSound` 忘了 off 或写了 `"false"` | 必须字符串 **`"off"`** |
| 首帧和定妆图不是同一个角色 | `left` 没挂定妆图，或 `startFrameNode` 挂错 | 两步都要指向正确节点 id |
| 一条 4s 裁不出第二段 | 提示词没分两段 / 没写收尾帧 | 照 §四 骨架重写 |
| 下载 404 | 猜了 URL 路径 | 一律走 `read_node` 返回的 url |
| 积分记不清 | 图片和视频混在一次 | 图、视频**分开两次**写 `credit-ledger.json` |

---

## 六、现有静态图直接转视频（不重新生图）★2026-10-31 首次跑通

场景：图库里已经有一张满意的静态分镜（如科普段），只想让它动起来。
**不要重新生图**——重生成会改构图、改调色，和前后镜接不上。直接把原 PNG 传上去当首帧。

### ① 上传链路（4 步，必须在 `upload_media` 之前完成）

```
upload_ticket{file_name, file_size, projectId}      → {uploadId, path, parts[0].url}
PUT <parts[0].url>  ← 字节流                      → 200
upload_complete{path, upload_id}                    → {file_ref, url}
upload_media{name, fileRef, mediaType:"image", projectId, idempotencyKey} → {nodeId}
```

**★最大的坑：PUT 时绝对不能带 `Content-Type` 头。**

OSS 的 V1 签名把 Content-Type 算进了 `StringToSign`，而服务端签的是**空 Content-Type**。
带 `application/octet-stream` 会稳定返回 `403 SignatureDoesNotMatch`，且错误体里会直接回显
服务端重算的 `StringToSign`（`PUT\n\napplication/octet-stream\n<expires>\n<path>`）——
看到这行就知道是头的问题，不是签名过期。

- ✅ `curl -X PUT --data-binary @file -H "Content-Type:" "<url>"`
- ❌ `curl -X PUT -T file "<url>"`（curl 会自己补 `application/octet-stream`）
- ❌ Python `urlopen(Request(url, data=..., method='PUT'))` 同样会被补头

单文件 <5MB 走 `part_size` 默认的一段即可，不必分片。

### ② 生视频时 `startFrameNode` 指向 upload_media 返回的 nodeId

`create_node` 传了 `startFrameNode` 后，schema 强制 `intent:"generate"` 且 **`left` 必须为空数组**
（帧路径与参考图路径互斥）。prompt 里仍可用 `{{Node <nodeId>}}` 指代首帧。

### ③ ★接入成片的坑：全幅 vs zoompan 取景，会暗 7%

静态图走的是 `scale=2304:1296 → zoompan z=1.06~1.14` 路径，**画面被推近 6~14%，暗角被裁掉**；
换成视频后如果用 `no_zoom: true`，是全幅 1920×1080，**边缘暗部全露出来** ⇒ 同内容实测
**Y 均值 51.1 → 47.7（−6.7%）、p90 115 → 103**，肉眼就是"这一镜突然发闷发暗"。

两步修（实测收敛到 +6%，略亮可接受）：

1. **素材侧裁回同样取景**：`crop=1204:678:38:21,scale=1280:720:flags=lanczos`
2. **shot_map 加 `grade`**（该字段已在 pipeline 白名单内，无需改代码）：
   ```
   "grade": "curves=all='0/0 0.3/0.345 0.6/0.665 0.85/0.93 1/1',eq=brightness=0.012:contrast=1.04:saturation=1.12,colorbalance=rm=0.035:gm=0.006:bm=-0.032"
   ```

**定档方法**（别瞎猜，3.5 分钟一版渲不起）：从上一版成片里抽出该镜 1.9s 段，
用 ffmpeg 离线套候选 grade 串，测 Y 均值 / sd / p90，对齐"原静态图版"的实测值再重渲。

### ④ 换视频镜后 map 项要同时改三处

```json
{"src":"shots/xxx_ai.mp4", "shot":"mid", "no_zoom":true, "grade":"<上面那串>"}
```

`no_zoom` 必须给：AI 素材自带轻微推近漂移（4s 约 +6%），再叠 `zoom_in` 会二次推近 + 多一道重采样变糊。

### ⑤ 验收四件套

| 项 | 判据 |
|---|---|
| 角色一致 | 生成第 1 帧 vs 首帧图并排看（面罩形状/肌肉切线/绿色色相/腕带） |
| 手部 | 放大裁手上半身，查多指、粘连、指节断裂 |
| 稳定性 | 逐帧差分 `max` 不得 >4（4s 均值 1.5~1.8 属正常）；亮度波动 <2 |
| 亮度 | 接进成片后与"原静态图版"同时间点比 Y 均值，偏差控制在 ±8% 内 |

---

## 三、★首帧直传生视频：三个必踩的坑（2026-11-01 实测打通）

场景：手里已经有一张好图（图库静态图 / 上一镜的帧），想直接拿它当首帧生 4s 动态，
**不重新生图**（省 100 分/张）。

### 坑 1 · OSS 分片上传：带 `Content-Type` 必报 `SignatureDoesNotMatch`

`upload_ticket` 返回带签名的 part URL 后，PUT 时必须**把 Content-Type 头删掉**：

```bash
# ✗ 报错 SignatureDoesNotMatch（签名方按空 Content-Type 算的）
curl -X PUT -H "Content-Type: image/png" --data-binary @x.png "$PART_URL"

# ✓ 正确：显式清空 Content-Type，并关掉 Expect
curl -X PUT -H "Content-Type:" -H "Expect:" --data-binary @x.png "$PART_URL"
```

成功回包是**空 body**（不是 JSON），`curl -s` 看到空就是成功。
之后 `upload_complete {path, upload_id}` → 拿 `file_ref` → `upload_media {fileRef, mediaType:"image", name, projectId}` → 得到 image 节点 id。

### 坑 2 · `create_node` 不传 `run:true` 只会建节点，不会提交生成

调完返回 `taskKind: "canvas_operation"`、`task_id: "cop_..."`，
`read_node` 里**没有 `taskInfo`** —— 这就是没跑。
`cop_` 开头的是**画布写入回执**，永远不是生成任务 ID。

正解：建好节点后用 `update_node` 补一刀

```json
{"toolName":"mcp__libtv__update_node","params":{
  "node":"<刚建的 video 节点 id>",
  "projectId":"<uuid>",
  "intent":"generate",
  "startFrameNode":"<首帧 image 节点 id>",
  "run":true,
  "idempotencyKey":"<新 key>"
}}
```

返回里 `taskKind: "generation"` + `status: "accepted"` + `generation.task_id`（纯数字开头）才是真任务。
之后 `task_status {project_id, task_id}` 轮询，`readiness` 从 `PROCESSING` → `TERMINAL_READY`、`outcome: SUCCEEDED`。

> 实测耗时：约 2 分 20 秒（21:44 提交 → 21:47 成功）。

### 坑 3 · 用了 `startFrameNode`，prompt 里就不能再写 `{{Node xxx}}`

会直接 `NODE_VALIDATION_FAILED: Media reference "{{Node i-xxx}}" is not connected to this node`。

首帧已经由 `startFrameNode` 锁死，prompt 开头改写**文字描述**即可：
「以首帧图为准（场景、机位、光线、道具位置与数量严格不变）……」。
`{{Node}}` 占位符只用于 `left`/`right` 引用边那套，两套不能混用。

### 验收：首帧是否忠实原图，一条命令量出来

```python
# 首帧 vs 原图：亮度均值差 + Pearson 结构相似
# 本次实测：亮度差 +0.8、高光占比同为 4.9%、Pearson 0.944
# ⇒ 差 <3 且 Pearson >0.90 就不必补 grade；否则按第 76 条的补偿串补
```

**结论**：这张图直传生视频，首帧等同原图，**不需要 grade**（区别于「重绘后再转」的素材）。

---

## 四、生成的 4s 素材怎么接进成片（实测 2026-11-01）

### 情况 A：素材比槽位短（最常见）

C Dance 2.0 Fast 固定 4s，出片约 4.04s；而镜槽位常是 4.2–4.5s。差 0.2–0.5s 时
**不要重生成**，用尾帧定格补足：

```bash
ffmpeg -y -i src_4s.mp4 \
  -vf "tpad=stop_mode=clone:stop_duration=0.40,fps=30" \
  -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -an out_4s4.mp4
```

- `stop_duration` 给 **槽位差 + 0.1~0.15s 余量**，别正好卡齐（边界会丢帧）。
- **务必带 `fps=30`**：生成素材常是 24fps，混进 30fps 时间线会有 1 帧级抖动。
- `-crf 18` 比成片的 21 高两档，避免二次压缩叠加。
- 定格内容要挑「适合停住」的：产品特写、表情定格、算账结果都行；
  **运动中的主体定格会像卡死**，那种要么剪槽位要么换素材。

### 情况 B：接进 shot_map 的写法

```json
{"src": "<延长版绝对路径>", "kind": "imgvid", "no_zoom": true}
```

- `kind:"imgvid"`：这是视频素材，不是静态图。
- **`no_zoom:true` 必加**：LibTV 生成的运镜自带推近/横移，再叠 `zoom_in` 会双倍推。
  只有素材本身完全静止时才允许开 zoom。

### 情况 C：素材末尾定格与字幕的对齐彩蛋

接之前值得花 1 分钟看这段素材的落点画面能不能跟当前这句字幕咬上。
本次实测：天秤镜落点是**一颗孤零零的红番茄特写**，而字幕正是
「菜和果那一栏就一直空在那儿」—— 画面和话反着说，反而成了全片最狠的一句。
这种「字幕说空、画面给唯一一个」的反讽落点，比配一张空盘图强得多。

### 验收：接完必须看的三个位置

1. **素材首帧有没有被上游吃掉**：卷播/上镜若比槽位起点长，素材开头会被盖掉若干帧。
   用 `ffprobe` 量卷播时长 vs 镜起点时间，差值 <0.1s 可接受。
2. **槽位尾部有没有黑**:定格只补到槽位长度，超出部分宁可截，不要留黑。
3. **逐镜中点帧唯一性闸门**（见 `transitions.md` 第九节）：素材换成视频后
   中点帧可能是运动中间态，容易和别的运动镜撞相关，必须重跑一次闸门。

---

## 五、★素材入库规则：池里只存原速（2026-11-01 灿爹定）

**规则**：视频素材池**只放原速、未经时长处理的素材**。慢放版/拉伸版/定格延长版**一律不入池**，
用到时按当时那句话的**口播秒数现场派生**，用完即弃。

**为什么**：同一段素材在不同文案里槽位长度不同（2.6s / 4.0s / 4.3s…），
存一个固定倍率的慢放版，换条文案就大概率对不上，还占地方、容易被误当另一条素材。
原速只存一份，倍率永远是「槽位 ÷ 素材时长」现算，不会错。

**现场派生的标准命令**（以 2s 素材填 4.000s 槽位为例）：

```bash
# 倍率 = 槽位 ÷ 素材时长（本例 4.000 ÷ 2.000 = 2.0）
# ① 拉伸 + 光流补帧到真 30fps
ffmpeg -y -i src_2s.mp4 \
  -vf "setpts=2.0*PTS,minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:vsbmc=1:me_mode=bidir" \
  -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -an slow.mp4
# ② minterpolate 会吃掉结尾 3 帧左右，用 tpad 补足到槽位 +0.1s 余量
ffmpeg -y -i slow.mp4 -vf "tpad=stop_mode=clone:stop_duration=0.16,fps=30" ... out.mp4
```

**拉伸 vs 光流的判据（实测 2026-11-01）**：

| 做法 | 结果 |
|---|---|
| `setpts=N*PTS,fps=30`（纯拉伸） | 29 对相邻帧里 **10 对完全同帧** ⇒ 有效更新率只有 15fps，慢镜会顿 |
| 上面加 `minterpolate=mci`（光流） | **0 对重复**，真 30fps |

光流只在**硬边界快速运动**时才拖毛边。这条素材全是柔边（光球、尘埃、星空），
逐格对比两版看不出差异 ⇒ **柔边素材放心用光流，硬边界（撕裂边缘快速移动、人物轮廓横移）才退回纯拉伸。**

**验一遍再交付**（别只信肉眼）：

```python
# 抽 1s 的 30 帧，算相邻帧灰度差，差 <0.02 视为重复帧
# 纯拉伸应出现 ~10/29 对重复；光流应为 0
```

---

## 七、Wan 系列：要 2 秒只能用 Wan 2.7（2026-11-01 实测打通）

灿爹说「用 WAN 生成两秒」时，**别按名字去猜型号**，按下面的实测结论走：

| 型号 | modelKey | 可用时长 | 图生视频 | 能不能用 |
|---|---|---|---|---|
| Wan 3.0 Prime | `wanx3.0-prime` | — | **✗ 无通路** | 别试 |
| Wan 2.7 | `wanx2.7-video` | **2–10s 连续** | ✓ | **2 秒的唯一选择** |
| Wan 2.6 | `wanx2.6-*` | 仅 5 / 10s | ✓ | 2 秒用不了 |
| Wan 2.2 | `wanxiang-v2-*` | 仅 5s | ✓ | 2 秒用不了 |

⚠️ **Wan 3.0 Prime 的坑**：`get_model` 的 schema 里写着 `frameInputSchemas`（有「首帧」字段），
但后端**实际不开放 图生视频**。提交后秒失败，`read_project` 看不到原因，
必须用 `update_node` 打 `run:true` 才逼出真实错误：

```
当前模型没有可覆盖全部媒体输入的自动模式（图片 1、视频 0、音频 0）
```

**⇒ 以后看到这个错误不要反复重试、不要改 prompt，直接放弃该模型。**

### 正确参数（2 秒 · 720P）

```json
{"toolName":"mcp__libtv__generate_video","params":{
  "projectId":"<id>",
  "model":"wanx2.7-video",
  "intent":"generate",
  "startFrameNode":"<upload_media 返回的节点 id>",
  "run":true,
  "params":{
    "count":1,
    "duration":2,
    "ratio_auto":"auto",
    "resolution":"720p"
  },
  "prompt":"以首帧为准，画面主体、服装、场景、光线全部保持不变，只做以下运动。……",
  "idempotencyKey":"<项目>-<镜>-wan27-<日期>-01"
}}
```

- **`resolution` 固定 `"720p"`**（铁律零）⇒ 输出 **1280×720 / 30fps**，进 1080p 成片放大 1.5 倍。
- **`ratio_auto:"auto"`** 才认首帧比例；写死 `"16:9"` 会在首帧不是 16:9 时报同一个「无自动模式」错。
- **首帧必须自己先裁成成片画幅再上传**：Wan 不做「覆盖全部媒体输入的自动模式」，
  3:2 的原图配 16:9 直接失败。裁法跟 fakecam 口径一致（z 铺满、焦点归一化坐标），
  裁完 resize 到 1920×1080 再传。
- 2 秒素材 = 60 帧；槽位若有 2.06s（62 帧），**用转场重叠吃掉差额，不要靠放慢**（放慢会发飘）。

### 进片时必须补偿的两件事

1. **Wan 不锁首帧构图**：实测主体比原图小 **3.8%**（不是凭感觉的 15%），
   用恒定 `zoom 1.04` 或 `1.04→1.06` 缓推补回来；写「镜头固定不动」它只做到七成，
   背景仍有极轻微横移，靠轻微推近掩盖。
2. **两个接缝都要重建**：前镜进来的转场混合区里混的是「旧静图版」，直接保留会闪回。
   做法见下节。

### ★替换单个镜头而不改变总帧数（本次实战）

```bash
# 先逐帧差分定位三个边界（别靠秒数反推，误差 1 帧就闪）
# 差分升高区 = 转场，稳定低值区 = 纯镜头
# 本次：镜13→14 转场 f802..f809，纯镜14 f810..f862，镜14→15 转场 f863..f872，纯镜15 f873..
```

替换段的帧序（71 帧为例，覆盖 f810..f880）：

| 段 | 帧数 | 内容 |
|---|---|---|
| 头部 ramp | 6 | 新画面 alpha 0.18→0.95 + 高斯模糊 4→0 递减，吃掉内容硬切 |
| 纯新画面 | 57 | Wan 60 帧均匀铺开（慢 5%，无感） |
| 尾部 hblur | 8 | 与**镜15 第 0..7 帧**交叉溶解 + `sigma=12*sin(pi*t)` 钟形模糊 |

⛔ **最容易错的一处**：尾部混合的 B 侧必须取「tail 首帧之后的那 8 帧」，
即混合结束时正好等于 tail 第一帧。取反了会让镜15 倒回去重播一次。

组装用 `concat` 滤镜（帧精确，比 concat demuxer 稳）：

```bash
ffmpeg -i 旧成片.mp4 -framerate 30 -i seg/s_%03d.png -filter_complex \
 "[0:v]split=2[s1][s2];\
  [s1]trim=start_frame=0:end_frame=810,setpts=PTS-STARTPTS[a];\
  [1:v]trim=end_frame=71,setpts=PTS-STARTPTS[b];\
  [s2]trim=start_frame=881,setpts=PTS-STARTPTS[c];\
  [a][b][c]concat=n=3:v=1:a=0[v]" \
 -map "[v]" -map 0:a -c:v libx264 -crf 18 -preset slow -c:a copy 新成片.mp4
```

**注意图片序列输入的流索引是 `1:v`，不是 `2:v`**（踩过）。

### 验收三条（缺一不可）

```python
# ① 总帧数、时长必须一模一样（本次 948 / 31.6s）
# ② 与旧版逐帧对比：变化帧数 == seg 长度，区间恰好 = 替换区间，其余 0 变化
# ③ 两个接缝的帧差分峰值要落在「正常转场」区间：
#    全片中位 2.5、原片转场峰值 7.6~21 —— 本次头 8.7 / 尾 11.6，合格
```

### ★Wan 2.7 的漂移特征：首帧准、运动漂（2026-11-01 实测，灿爹判定"可以用"）

**别用首帧相关度验收 Wan**。本次实测首帧 Pearson **0.998**（几乎完全一致），
看起来完美，但**运动一路在漂**：

| 现象 | 具体表现 | 危害 |
|---|---|---|
| 暗部被吃掉 | 星空/空洞后半段**几乎全黑**，光点消失 | 镜尾变死黑，接下一镜像断层 |
| 体型走形 | 小绿人从「柔和圆润」走向**硬朗健美**（肌肉切线变硬、肩变宽） | 同一角色前后不是一个人 |
| 末尾推过头 | 最后 0.3s 推近过量，**切掉头顶** | 定格帧不能用，尾帧延长会把切头留住 |
| 背景糊黑 | 器械架等次要元素糊成一团黑块 | 修不了，只能认 |

**⇒ 验收口径**（Wan 专用，和 C Dance 不同）：

1. **首帧 Pearson 只证明"起点对"，不证明"过程对"**。必须抽 **0% / 25% / 50% / 75% / 100%** 五帧拼版看。
2. 判据：主体轮廓在 5 帧里**保持同一比例**（差 <5%）、暗部亮度不低于首帧的 **60%**。
   越过这条但内容还能用 → 交灿爹看一眼定夺，**不要自己判废**（本次他判"可以用"）。
3. **末尾推过头就把尾帧切掉**：`trim=end_frame=N-9` 再 `tpad` 补，比保留切头顶的定格强。
4. **漂移素材不做慢放放大**：慢放会把漂移过程拉长，暗部吃掉的问题更明显。
   要用就按原速铺满，差额靠转场重叠吃（见上节「用转场重叠吃掉差额」）。

**成本口径**：2 秒 720P 一条约 12 分（估算，以账本明细为准）。**漂移是概率问题，不是参数问题**，
重跑一次可能漂得更狠 ⇒ 先用五帧拼版判断，够用就收，别为了完美连跑三条。
