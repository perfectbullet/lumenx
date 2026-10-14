# LumenX @ 192.168.8.231 部署报告

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
| `rsync_231.sh` | 本地 → 231 一键代码同步 |
| `.env.231.example` | 无密钥环境变量模板 |
| `deploy/setup_231.sh` | 一次性环境安装 |
| `deploy/start_231.sh` | 启动服务 |
| `deploy/stop_231.sh` | 停止服务 |

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
./rsync_231.sh                    # 同步代码到 231
./rsync_231.sh --dry-run          # 预览不传
./rsync_231.sh --delete           # 同步并删除远端 stale 文件

# === SSH 上去操作 ===
ssh zenking@192.168.8.231
cd /data/aigc/lumenx

# === 服务管理 ===
bash deploy/start_231.sh          # 启动（自动 source conda + nvm）
bash deploy/stop_231.sh           # 停止（PID 文件 + 按项目目录限定的进程检查）

# === 查看日志 ===
tail -f logs/backend.log logs/frontend.log

# === 换 API Key ===
vi .env                            # 替换 sk-dummy-placeholder
bash deploy/stop_231.sh && bash deploy/start_231.sh  # .env 变化必须手动 restart

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

| 项 | 状态 | 说明 |
|---|---|---|
| DeepSeek API Key | ❌ 假值 | `.env` 里 `OPENAI_API_KEY` 需换真实 key |
| DashScope API Key | ❌ 假值 | `.env` 里 `DASHSCOPE_API_KEY` 需换真实 key（画图/配音/VL 必须） |
| Demucs 人声分离 | ❌ 未装 | 需要时用已下载的 wheel + pip install |
| Kling/Vidu/MuleRouter Key | ❌ 未配 | 按需启用 |
| 磁盘监控 | ⚠️ 96% | 剩 84GB，demucs+torch 装完多 ~3GB |
| 数据持久化 | ✅ JSON 文件 | 当前基线；MongoDB 迁移已纳入后续实施计划 |
| 本地模型 | 后续接入 | 当前基线主要调用云端；后续接入 ComfyUI/H3、图像和 TTS |

---

## 十一、231 上其他已有 Python 服务（端口 8000/8610）

231 上已有其他项目在跑 uvicorn，部署 lumenx 时注意端口冲突：
```
root   4399   uvicorn app.main:app              --port 8610
10001  4512   uvicorn app.main:create_app       --port 8000
zenking 4799  uvicorn app.main:app --workers 1  --port 8000
```

lumenx 独占 `17177`（后端）和 `3008`（前端），无冲突。
