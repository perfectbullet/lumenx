# westd ComfyUI：语音、图像、视频替代方案评估

检查日期：2026-10-14（北京时间）。依据 ComfyOps 的 `docs/部署运维/westd_AutoDL_ComfyUI_CS-H3检查与修复_20261013.md`，通过 SSH 对当前 westd 实例做只读检查。本轮未提交 GPU 生成任务，未修改服务器、节点、模型或调度注册表。

## 1. 结论

**这台实例具备同时承载语音、图像、视频生成的资源基础，可用于减少 LumenX 对云端生成 API 的依赖。建议第一批评测：Qwen3-TTS 配音 + Qwen-Image-2.1 生图/编辑 + 已验收 H3 视频；Krea2 用于角色多视图，Wan2.2/LTX2.3 作为第二批视频候选。**

这里的“替代”指业务能力适配，不是原云模型的等价复刻。准确对白、情绪、角色一致性、画质、时长和吞吐仍需固定样本验证。实例在公网 AutoDL，属于自部署云算力；不满足纯局域网离线部署要求。

| 业务能力 | 当前 LumenX 路径 | 本实例替代候选 | 当前证据状态 |
|---|---|---|---|
| 固定音色/情绪配音 | DashScope CosyVoice 或 Qwen3-TTS | 本地 Qwen3-TTS 1.7B CustomVoice | 权重、tokenizer、节点存在；插件依赖导入成功；未生成验收 |
| 音色设计/角色克隆 | 云 voice design/enrollment | Qwen3-TTS VoiceDesign / Base | 两个 UI 工作流及完整模型目录存在；需导出 API、实测 |
| 单人/多人声音克隆 | 云 TTS | 本地 Fish S2-Pro | s2-pro/fp8/w4a16 权重及 codec 存在，已有 API 工作流；运行/适用许可需确认 |
| 角色/场景/道具图 | Wan 图片 / 部分 GPT-Image 路径 | Qwen-Image-2.1；另有 Qwen-Image-2512 | 选定 API 工作流节点已注册；主要模型路径可解析；未生成验收 |
| 参考图编辑/分镜首帧 | 云图片编辑 | Qwen-Image-2.1 编辑；Qwen-Image-Edit-2511；Flux.2 Klein | 权重/节点/工作流存在；按任务类型选一条基线 |
| 角色三/四视图 | 图片生成/人工整理 | Krea2 四视图工作流 | API-T10 节点及四宫格 LoRA 模型路径可解析；效果未验收 |
| 参考图生视频与原声 | 云 R2V provider | MiniMax-H3 Ref2VA / CSH3 | 用户提供报告已有真实生成、音视频解码及归档验收；本轮只检查资源 |
| 首帧生视频 | 云 I2V provider | Wan2.2 I2V | 高低噪声双模型、VAE、T5、LoRA及 API 工作流存在；未生成验收 |
| 图像 + 配音驱动视频 | 视频 provider 特定模式 | LTX2.3 音频条件工作流 | API-H31 有 LoadImage/LoadAudio/SaveVideo；权重可解析，未验证对白/口型 |

## 2. 实际检查了什么

实例：`ssh -p 39227 root@connect.westd.seetacloud.com`；ComfyUI `/root/ComfyUI`，内部 API `http://127.0.0.1:6006`。报告更新记录的公网地址为 `https://u1114350-7918256b389a.westd.seetacloud.com:8443`，本轮 SSH 查询内部 API，不重复宣称公网链路已由本轮测试。

读取 `/object_info`、`/queue`、`/system_stats`，扫描模型文件与 UI/API 工作流，并检查选定工作流节点及模型加载器选项。本轮队列观测为空；GPU 为 RTX 5090，API 报告约 32 GiB 显存。

扫描得到 1457 条权重文件路径、1539 个可识别工作流 JSON（包括用户工作流、插件示例及测试材料），不是 1457 个独立可用模型或 1539 条可直接上线流水线。路径可能是公共盘软链接、别名或不同量化版本。文件大小与路径存在不证明权重内容完整。

选定 12 个工作流（10 个 API + 2 个 TTS UI）的顶层节点均已注册。此检查不等同 API 参数全面校验、插件执行成功或子工作流全链验收。`/history?max_items=50` 本次返回空记录，不能由此认定模型从未运行；也无法提供新的语音/图片/其他视频成功任务证据。

本地只读证据保存在 `docs/agents/context/westd-model-inventory-20261014/`，包含 inventory、selected-workflows、dependency-check、tts-and-runtime-details、plugin-import-details、qwen-import-check、summary JSON。原始数据包含完整工作流，不作为精简交付材料提交 Git。

## 3. 语音：Qwen3-TTS 优先，Fish 作为对照

### 3.1 已有本地 Qwen3-TTS

模型目录 `/root/ComfyUI/models/Qwen3-TTS-Models/` 下存在：

- `Qwen3-TTS-12Hz-1.7B-CustomVoice`：主权重约 3.83 GB，speech tokenizer 约 0.68 GB。
- `Qwen3-TTS-12Hz-1.7B-VoiceDesign`：主权重约 3.83 GB，speech tokenizer 约 0.68 GB。
- `Qwen3-TTS-12Hz-1.7B-Base`：主权重约 3.86 GB，speech tokenizer 约 0.68 GB。

官方能力分工：CustomVoice 提供预设音色和指令控制，VoiceDesign 根据文字设计声音，Base 根据参考音频克隆。不要假设 Base 与 CustomVoice 接受同样的情绪参数。[Qwen3-TTS 官方说明](https://github.com/QwenLM/Qwen3-TTS)

服务已注册 `TDQwen3TTSModelLoader`、`TDQwen3TTSCustomVoice`、`TDQwen3TTSVoiceDesign`、`TDQwen3TTSVoiceClone`、`TDQwen3TTSMultiDialog` 等节点。模型加载器按本地目录读取，`auto_download` 默认 false。插件自带 `Qwen3-TTS/qwen_tts` Python 包，本轮按插件路径导入成功；在普通 Python 路径下找不到该包不能误判为插件缺依赖。[插件来源](https://github.com/AICoderTudou/ComfyUI-TD-Qwen3TTS)

已有 UI 工作流位于 `/root/ComfyUI/user/default/workflows/N声音生成-音乐生成-声音克隆/`：

- `N06-Qwen3TTS音频创造.json`：VoiceDesign → SaveAudio。
- `N06-Qwen3TTS音频克隆.json`：Base + LoadAudio（可经 Whisper 提取参考文字）→ SaveAudio。

建议第一条用 CustomVoice 做一段指定台词配音，最少依赖；再验收 VoiceDesign 和 Base。设计声音产生的是音频，可保存为角色参考再克隆后续台词；不是自动获得一个与云端 clone ID 等价的永久 voice_id。

### 3.2 Fish S2-Pro 也已具备本地权重

`/root/ComfyUI/models/fishaudioS2/` 下有 `s2-pro`、`s2-pro-fp8`、`s2-pro-w4a16`，权重、配置、tokenizer 与 `codec.pth` 均存在。原始 s2-pro 两片权重合计约 9.12 GB，codec 约 1.87 GB；这是文件大小，不是运行显存估计。

本地节点是 `FishS2TTS`、`FishS2VoiceCloneTTS`、`FishS2MultiSpeakerTTS`。已经有 API 文件：

`/root/zealman-app/workflows/API-N2-单人声音克隆FishAudioS2pro.json`

它使用本地 `model_path=s2-pro`，LoadAudio 读取参考音频，Whisper 提取参考文字，SaveAudio 保存输出。可在测试副本提供已知参考文字，减少对 ASR 的依赖。

另有 `FishAudioTextToSpeech`、`FishAudioInstantVoiceClone` 等节点携带 `api_key_comfy_org/auth_token_comfy_org`，是另一类云 API 集成，不能把它们当成本地 S2 推理。

建议 Fish 作为音色/情感对照而非一期默认：Qwen 与现有 TTS 功能映射更直接；Fish 的代码和 S2-Pro 权重许可需按具体版本确认。官方说明 S2-Pro 权重采用 Research License，不应仅因公开可下载就当作无条件商用替代。[Fish 官方仓库](https://github.com/fishaudio/fish-speech)

## 4. 图像：选一条生图与一条编辑基线

### 4.1 Qwen-Image-2.1：最适合先评测统一生图/编辑

已核对两份 API 文件，路径前缀均为 `/root/zealman-app/workflows/`：

| 文件 | 实际用途 | 关键依赖 |
|---|---|---|
| `API-B18-Qwenimage2.1.json` | 无参考图文本条件生成，适合角色/场景/道具图试验 | `qwen/qwen_image_2.1_int8_convrot.safetensors`（约 7.26 GB）、`qwen3vl_8b_int8_convrot.safetensors`、`qwen_image_2.1_vae_bf16.safetensors` |
| `API-B20-Qwen-Image-2.1-Turbo高速编辑版.json` | LoadImage + TextEncodeQwenImage21 参考图编辑 | 本模板实际使用 BF16 扩散模型与 BF16 文本编码器；不要由文件名“Turbo”推断低显存/高速度 |

两份的主要 loader 输入均在服务下拉选项中，且可解析到模型文件。本轮未测生成质量和显存；B20 组合的文件体量较大，是否在 32 GiB 下稳定运行取决于卸载/量化和采样配置。先测 B18，再调整编辑基线，不直接承诺 2K 并发。

Qwen-Image-2.1 官方提供图像生成/编辑模型及部署资料；本机量化文件和插件是具体实现，需要单独实测，不能从官方能力推断该量化版效果。[官方仓库](https://github.com/QwenLM/Qwen-Image-2.1)

还有 Qwen-Image-2512、Qwen-Image-Edit-2511 和 Nunchaku 量化资源。`API-A01-文生图-Qwen2512高清放大.json` 叠加了 Lightning、写实 LoRA 和 SeedVR2 放大，依赖更复杂；SeedVR2 模型本轮未从通用路径解析到，不据此断定缺失，但建议先从测试基线移除放大链。写实 LoRA 也不一定适合漫剧美术风格。

### 4.2 Krea2：角色参考素材与多视图候选

`API-T10-Krea2做剧图像4视图.json` 使用：

- `krea/krea2_turbo_int8_convrot.safetensors`。
- `qwen3vl_4b_fp8_scaled.safetensors` + `qwen_image_vae.safetensors`。
- `krea2/krea2_4panel.safetensors` LoRA。

这些模型路径均可解析；节点已注册。它适合评测角色外观参考图到四视图的业务，而非自动解决全部角色一致性。结果若是四宫格，需裁切成独立角色参考图并记录顺序，再提供给视频模型；四宫格图不能任意当四张独立参考输入。

另有 `API-T4-Krea2-int8-角色设定三视图.json`，同时包含额外 LLM、混合权重和风格 LoRA，先不选为最小基线。

### 4.3 Flux.2 Klein：多参考编辑与分镜备选

`API-D14-分镜-Flux克莱因9B多角度多场景.json` 的基础加载为 `flux/flux-2-klein-9b-fp8.safetensors` + `qwen_3_8b_fp8mixed.safetensors` + `flux2-vae.safetensors`。模板还带 llama_cpp 的提示词辅助；其 GGUF 在 `models/LLM/` 实际存在，通用 folder_paths 无结果并不等于缺文件。

业务上可以沿用已配置 DeepSeek 提供提示词，把候选基线简化为图片生成/编辑，避免每次还在同一 GPU 加载另一个文本模型。不同 FLUX.2 权重的许可并不完全一致，需要核对选定 9B 版本和第三方量化来源。[FLUX.2 官方仓库](https://github.com/black-forest-labs/flux2)

本期不同时接 Qwen、Krea、Flux 全家桶。先一条统一图像路径，角色多视图有明确效果优势时再加 Krea。

## 5. 视频：H3 主线，Wan/LTX 作为差异化候选

### 5.1 H3：已有真实生成依据

原检查报告验证过 CSH3 的 Ref2VA 工作流，包含真实参考图任务、归档、显存清理及完整音视频解码。本实例因此最有证据的生产候选仍是 H3。报告中 2MP 真实任务普通 20 步约 806 秒；不能根据工作流宣传名称或另一套 Turbo6 参数承诺固定生成速度。

H3 原生音频可用于原声路径，不等于独立 TTS 的精确台词/固定音色接口。

### 5.2 Wan2.2：首帧图生视频备选

`API-G01-图生视频-Wan2.2万相基础版.json` 使用高/低噪声两个 14B FP8 模型、LightX2V LoRA、Wan VAE 与 UMT5；节点及主要权重可解析。输出使用 `VHS_VideoCombine`，`save_output=true`，结果需要按 ComfyUI History 的实际输出字段发现。

它能替代“首帧 → 动态片段”的业务，不可视为云 `wan2.7` 的本地同版本复刻；此模板也不是完整音画联合生成，配音需外接 TTS/混音。双模型和插件优化下的实际显存与耗时待测。[Wan2.2 官方资料](https://github.com/Wan-Video/Wan2.2)

### 5.3 LTX2.3：图像 + 音频条件值得专项测试

`API-H17-文图生视频-LTX2.3全面优化版.json` 有模型、音频 VAE、文本编码器、蒸馏 LoRA、放大器与保存链。`API-H31-ltx2.3声音-图像生成视频.json` 进一步有 LoadAudio、LTXVAudioVAEEncode、LoadImage 与 SaveVideo。

这些主要模型可解析，适合评估“TTS 指定对白 + 首帧 → 片段”。但音频条件存在不代表口型完全准确，也不能据名称承诺特定中文对白效果。需要实际测音频保持、嘴部同步、人物一致性和帧数/时长。[LTX 官方实现](https://github.com/Lightricks/LTX-2)、[ComfyUI 插件](https://github.com/Lightricks/ComfyUI-LTXVideo)

## 6. LumenX 接入还缺哪些工作

仍沿用一个 LumenX 仓库、一个 MongoDB、独立 API + monitor 的计划。新增 `audio.qwen3tts`、`image.qwen`、`video.h3` 等内部 profile，由 monitor 选择固定模板；不要允许调用方直接提交任意节点图作为正常业务接口。

| 接入项 | 必须做的工作 |
|---|---|
| 输入规格 | 文字、图像、音频分开验证；每模板建立稳定业务字段到节点 input 的映射，不依赖猜测节点 ID |
| Qwen TTS 模板 | 将 UI 工作流导出/整理为 API 格式；加文本/语言/参考音频字段，关闭隐式自动下载 |
| 输出归档 | 当前 archiver `output_files()` 只遍历 `videos/images/gifs`，**缺少独立音频输出**；需按 SaveAudio 的实际 History 字段补发现、下载与文件类型校验 |
| 音色管理 | 把云 voice ID 映射为本地 `voice_profile`；设计/克隆保存参考音频、参考文字、模型版本与结果，不复用云 enrollment ID |
| 图像回填 | 角色/场景/道具及分镜各自回填；多视图裁切后创建明确 asset ID 与顺序 |
| 节点能力 | 已有 scheduler 偏 CSH3 模板/profile；扩为模态和工作流能力白名单，不让只支持 H3 的节点领取 TTS/图片任务 |
| GPU 互斥 | 同一个 ComfyUI 实例上的 TTS/图像/H3 共用一张卡，统一占用与清理；不要注册成三个独立 URL 后误算成三个算力节点 |
| 文件完成判断 | 图片真可解码、音频有有效时长、视频音轨符合声明；有 Save 节点不等于已有结果 |
| 依赖与版本 | 保持已验收 H3 环境；只在确认缺包时补依赖，pip/Docker 使用清华镜像，不整套升级 |

这不是只改模型名。代码接入按 `.codex/workflows/lumenx-model-onboarding.md` 的 runtime/catalog/输入输出/回归流程执行；本轮仅评估，未修改 catalog 或运行时。

## 7. 用最少工作确认能否替代

推荐在独立测试任务、统一调度入口和受控时间窗口执行：

1. **Qwen CustomVoice：**3 段中文台词（平静/愤怒/悲伤），生成独立音频；核对漏字、多字、情绪、时长和实际 History 音频字段。
2. **Qwen Base：**同一角色参考音频生成 3 句不同台词，听音色稳定性；与现有云 TTS 比较。
3. **Qwen 图像：**固定角色/场景/道具描述各 1 张，再用角色+场景参考测试编辑；记录身份/服装保留、尺寸、耗时、失败率。
4. **Krea 四视图：**1 个角色做多视图，检查是否真的同人，裁切后在 H3 使用。
5. **H3 / Wan / LTX：**同样首帧与动作条件做短片；H3 测原声，Wan 测动作，LTX 额外测指定音频驱动；按各自能力分别验收。
6. **连续切换：**语音 → 图片 → 视频 → 再语音，观察 OOM、模型卸载、清理确认和任务恢复。必须经过现有或隔离后的调度入口，不能绕过 monitor 干扰在线任务。

需要的是真实产物对照，不是全面压测。模型文件已在共享盘减少下载工作，但评测与后端集成仍要投入时间；建议先验证 Qwen TTS 与图像各一条，保留 H3 主线，不把六七种 provider 一起塞进三周任务。

主推组合是 **DeepSeek 文本 + 本地 Qwen 图像 + 本地 Qwen3-TTS + 已部署 H3 视频 + FFmpeg 合成**。这是推荐的验证顺序，尚未成为 LumenX 当前可运行的全链路。westd 自部署云端依然需要外网；如果将来要求校内离线，要把选定权重、插件和工作流迁到内网算力后重新验收。
