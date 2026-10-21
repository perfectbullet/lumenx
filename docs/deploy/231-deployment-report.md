# LumenX @ 192.168.8.231 部署报告

**2026-10-16 更新**：后端元数据已迁移至 MongoDB `lumenxdb`；4 个项目、1 个系列和共享资产保留，前端服务未改动。环境变量及回滚点见 [MongoDB 迁移与运维说明](../agents/deliverables/2026-10-16-MongoDB迁移与运维说明.md)。下方硬件/环境表仍为原部署记录。

**2026-10-21 更新**：后端统一管理入口改为 `backend.sh`，旧脚本已归档；操作说明见 [后端管理](backend-management.md)。

**原部署记录时间**：2026-10-12 18:40；2026-10-14 整理提交，未重新执行线上验证。
**部署用户**：zenking
**部署目录**：`/data/aigc/lumenx`
**部署方式**：Conda + Node.js（dev 模式 + 热加载，适合二次开发）

---

## 一、服务状态（原部署检查记录）

| 服务 | 地址 | HTTP | PID | 进程 |
|---|---|---|---|---|
| 后端 API | http://192.168.8.231:17177/docs | **200** | — | `python -m uvicorn src.apps.comic_gen.api:app --reload` |
| 前端页面 | http://192.168.8.231:3008 | **200** | — | `next dev --port 3008` |

端口监听：
```
tcp   0.0.0.0:17177   LISTEN   python
tcp6  :::3008         LISTEN   next-server
```

---

## 二、服务器环境

| 项 | 值 |
|---|---|
| 系统 | Ubuntu 22.04 LTS |
| GPU | **RTX 5090** 32GB VRAM |
| CPU | 96 核 |
| RAM | 256GB |
| 磁盘 | 84GB 可用（96%） |
| GPU 驱动 | NVIDIA 595.84 · CUDA 13.2 |
| FFMPEG | 4.4.2（系统自带） |
| SSH | 免密登录 `ssh zenking@192.168.8.231` |
| Sudo | 需要密码 |

---

## 三、Python 环境

| 项 | 值 |
|---|---|
| Conda 环境 | `lumenx`（`~/miniconda3/envs/lumenx`） |
| Python | **3.11.17** |
| FastAPI | 0.143.0 |
| dashscope | 1.27.7 |
| openai | 3.26.1 |
| oss2 | 2.19.1 |
| uvicorn | 0.54.0 |
| requests | 2.34.2 |
| **torch** | **未安装**（预期，跳过 demucs） |
| **demucs / soundfile** | **未安装**（预期，跳过） |

> ⚠️ 系统 miniconda 默认 Python 3.12 有 urllib3/chardet 版本警告，不影响 lumenx 3.11 环境。

### 跳过 demucs 的原因

demucs 是音频人声分离功能，唯一入口在 `pipeline.py`。安装它会拉 torch+CUDA wheel（~2GB），但 LumenX 所有 AI 能力都走云端 API，不依赖本地模型。setup 脚本已跳过，需要时再单独装。

---

## 四、Node.js 环境

| 项 | 值 |
|---|---|
| 安装方式 | nvm（`~/.nvm`） |
| Node | v22.23.3 |
| npm | 12.2.0 |
| Next.js | 14.2.35 |
| 依赖数 | 653 packages |

### 踩过的坑

| 坑 | 原因 | 修复 |
|---|---|---|
| npm "Exit handler never called!" | npm 10.8 bug | setup 脚本强制 Node 22 + npm 12 |
| npm 12 拦截 SWC/esbuild postinstall | npm 安全策略 | setup 脚本自动 `npm install-scripts approve @swc/core esbuild @parcel/watcher unrs-resolver` |
| postcss/nanoid 缺失 | npm install 不完整 | 改官方 npm 源（淘宝镜像偶尔 postcss@8.5.26 不同步） |

---

## 五、.env 关键配置（231 服务器）

```env
# ---- LLM: DeepSeek (OpenAI 兼容接口) ----
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-dummy-placeholder     # ⚠️ 假值，绕过前端检查用
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

# ---- 存储策略: 纯本地, 不走 OSS ----
OSS_ENABLE=false
OSS_BUCKET_NAME=
OSS_ENDPOINT=
OSS_BASE_PATH=
ALIBABA_CLOUD_ACCESS_KEY_ID=
ALIBABA_CLOUD_ACCESS_KEY_SECRET=

# ---- API 服务 ----
API_HOST=0.0.0.0
API_PORT=17177

# ---- DashScope (前端启动检查必需) ----
DASHSCOPE_API_KEY=sk-dummy-placeholder   # ⚠️ 假值，绕过前端检查用

# ---- 可选 provider（未配置，按需启用） ----
# KLING_ACCESS_KEY=
# KLING_SECRET_KEY=
# VIDU_API_KEY=
# MULEROUTER_API_KEY=
```

### 功能可用矩阵

| 能力 | 是否可用 | 原因 |
|---|---|---|
| 前端界面浏览 | ✅ | 假 key 绕过 EnvConfigChecker |
| LLM 文本生成（DeepSeek） | ✅ | 走 openai 接口 |
| 图像生成（通义万相 Wanx） | ❌ | 需要真实 DASHSCOPE_API_KEY |
| 配音（CosyVoice/TTS） | ❌ | 需要真实 DASHSCOPE_API_KEY |
| VL 多模态（Qwen-VL） | ❌ | 需要真实 DASHSCOPE_API_KEY |
| Kling/Vidu/MuleRouter 视频 | ❌ | 需要对应 provider key |
| 人声分离（Demucs） | ❌ | torch+demucs 未装 |
| 项目持久化 | ✅ | JSON 文件存 `/data/aigc/lumenx/output/` |
| 图片/视频存储 | ✅ | 纯本地 `output/` 目录 |

---

## 六、Wheel 包目录

```
/data/aigc/lumenx/vendor/wheels/py311_torch2.14.1_cuda13.0/
├── torch-2.14.1.whl         529MB
└── torchvision-0.29.1.whp    7.1MB
```

命名规则：`py{py版本}_torch{torch版本}_cuda{cuda版本}`

版本来源：
- torch 2.14.1 / torchvision 0.29.1 — PyPI 上有对应 cp311/linux_x86_64 wheel
- CUDA 13.0.3 — pip 装 demucs 时拉的 `cuda-toolkit==13.0.3`
- RTX 5090 驱动 CUDA 13.2 向下兼容 13.0

安装方式：
```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate lumenx
pip install --no-index vendor/wheels/py311_torch2.14.1_cuda13.0/torch-2.14.1.whl
pip install --no-index vendor/wheels/py311_torch2.14.1_cuda13.0/torchvision-0.29.1.whl
pip install demucs soundfile -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 七、部署脚本套件

| 文件 | 用途 |
|---|---|
| `scripts/sync-231.sh` | 本地 → 231 一键代码同步 |
| `.env.231.example` | 无密钥环境变量模板 |
| `scripts/archive/2026-10-21/deploy/setup_231.sh` | 一次性环境安装历史脚本 |
| `backend.sh` | 后端启动 / 停止 / 重启 / 状态 / 日志 / 配置 / 连通检查 |
| `scripts/archive/2026-10-21/` | 旧联合启停与构建脚本归档 |

### rsync 排除规则

实际 `.env` 和 `.env.*` 不同步；无密钥的 `.env.example`、`.env.*.example` 通过白名单同步。

```
.git/ .venv/ node_modules/ **/node_modules/ .next/ frontend/.next/
dist/ build/ __pycache__/ **/__pycache__/ *.pyc *.pyo
output/ logs/ .env .env.local .env.*
.DS_Store *.log *.pid .vscode/ .idea/ .cache/
.pytest_cache/ **/.pytest_cache/ .mypy_cache/
frontend/dist/ frontend/out/
```

### setup_231.sh 流程

```
[0/5] 确保 Node.js 22+（nvm 探测，不够自动升级）
[1/5] 创建 conda 环境 lumenx (python 3.11)
[2/5] ffmpeg (conda-forge，系统已有则跳过)
[3/5] pip 装依赖（清华源，跳过 demucs/soundfile）
[4/5] pip 装 openai>=1.0.0（DeepSeek 必需）
[5/5] npm install（官方源 + approve @swc/core 等 postinstall）
      创建 output/ 和 logs/ 目录
```

### start_231.sh 流程

```bash
# 显式 source conda.sh（bash 子 shell 不加载 .bashrc）
# 显式 source nvm.sh
# 已在 lumenx 环境则跳过 conda activate
# stop_231.sh 先停旧进程
# 后台起 uvicorn :17177（--reload）
# 后台起 next dev :3008
# sleep 4 + curl 验证
```

---

## 八、日常工作流

```bash
# === 代码同步 ===
cd /home/zj/aigc/lumenx
./scripts/sync-231.sh                    # 同步代码到 231
./scripts/sync-231.sh --dry-run          # 预览不传
./scripts/sync-231.sh --delete           # 同步并删除远端 stale 文件

# === SSH 上去操作 ===
ssh zenking@192.168.8.231
cd /data/aigc/lumenx

# === 服务管理 ===
./backend.sh start --reload       # 后台启动后端（开发模式）
./backend.sh stop                 # 仅停止当前项目后端

# === 查看日志 ===
./backend.sh logs -f              # 后端日志脱敏查看

# === 换 API Key ===
vi .env                            # 替换 sk-dummy-placeholder
./backend.sh restart --reload     # .env 变化必须手动 restart

# === 重装 demucs（人声分离）===
source ~/miniconda3/etc/profile.d/conda.sh && conda activate lumenx
pip install --no-index vendor/wheels/py311_torch2.14.1_cuda13.0/torch-2.14.1.whl
pip install --no-index vendor/wheels/py311_torch2.14.1_cuda13.0/torchvision-0.29.1.whl
pip install demucs soundfile -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 九、踩过的坑（已固化到脚本）

| 坑 | 原因 | 修复 |
|---|---|---|
| `CondaError: Run 'conda init'` | bash 脚本开子 shell，不加载 `.bashrc` | 显式 `source conda.sh` + `CONDA_DEFAULT_ENV` 检查 |
| npm "Exit handler never called!" | npm 10.8 bug | setup 脚本强制 Node 22 + npm 12 |
| npm 12 拦截 SWC/esbuild postinstall | npm 安全策略 | setup 脚本自动 approve |
| postcss/nanoid 缺失 | npm install 不完整 | 改官方 npm 源 |
| PyPI 到服务器 ~150KB/s | 国内慢 | pip 用清华源，npm 用官方源 |
| triton 247MB 下载卡死 | 同上 | setup 跳过 demucs |
| torch wheel 下 1 小时 | PyPI 直连慢 | 用 `setsid wget -b` 后台下载 |
| .env 变化不触发 uvicorn --reload | uvicorn 只 watch 代码文件 | 换 key 必须手动 restart |
| 淘宝镜像 postcss@8.5.26 不同步 | 镜像延迟 | 改用 npm 官方源 |
| demucs 拉 torch+CUDA 2GB+ | requirements.txt 里默认装 | 注释掉，按需安装 |

---

## 十、待办 / 后续动作

以下Key配置、磁盘占用和软件安装状态源于原部署检查，不代表10月19日实时状态；本轮未登录服务器复测。元数据与模型证据已按10月16日记录更新。

| 项 | 状态 | 说明 |
|---|---|---|
| DeepSeek API Key | ❌ 假值 | `.env` 里 `OPENAI_API_KEY` 需换真实 key |
| DashScope API Key | ❌ 假值 | `.env` 里 `DASHSCOPE_API_KEY` 需换真实 key（画图/配音/VL 必须） |
| Demucs 人声分离 | ❌ 未装 | 需要时用已下载的 wheel + pip install |
| Kling/Vidu/MuleRouter Key | ❌ 未配 | 按需启用 |
| 磁盘监控 | ⚠️ 96% | 剩 84GB，demucs+torch 装完多 ~3GB |
| 数据持久化 | ✅ MongoDB（10月16日更新） | 业务元数据已切至lumenxdb；旧JSON是历史备份，文档编辑稿/快照仍为文件型工件 |
| 自部署模型 | 已外部实测，业务待接入 | 10月16日A/B的H3、Qwen图像、Qwen3-TTS通过短样本；当前业务adapter/monitor尚未接通 |

---

## 十一、231 上其他已有 Python 服务（端口 8000/8610）

231 上已有其他项目在跑 uvicorn，部署 lumenx 时注意端口冲突：
```
root   4399   uvicorn app.main:app              --port 8610
10001  4512   uvicorn app.main:create_app       --port 8000
zenking 4799  uvicorn app.main:app --workers 1  --port 8000
```

lumenx 独占 `17177`（后端）和 `3008`（前端），无冲突。

## 十二、10月19日晨会后的部署边界（方案，未执行）

- 当前延续231上的LumenX API、已使用的MongoDB及受管output目录；将来同仓库另起monitor，独立进程/心跳，媒体目录与配置统一维护。
- 两个公网ComfyUI实例各有独立GPU；A主要视频，B排队图片/TTS。旧archiver与新monitor必须有唯一调度权威，后续真实切换时核对未完成任务和占用。
- 本轮不安装OpenCue、Kubernetes/KEDA、MinIO/PostgreSQL、Git LFS或新增质量增强/身份模型；不修改云机、数据库、模型和服务启动方式。
- 先规范化媒体路径、校验、来源和版本引用；共享对象存储只作为后续可选适配。若采用MinIO需重新核对具体发行/维护和许可，不能把新材料当作采购/部署结论。
- 文档快照文件不等于项目级备份；运维恢复需同时包含MongoDB、document/history及实际媒体，不能只恢复任一部分；做关联一致性验证。

本周安排见[后端实施安排](../agents/deliverables/2026-10-19-本周后端实施安排.md)，新增建议取舍见[增强材料评审](../LumenX的后续增强.md#本轮评审结论2026-10-19)。
