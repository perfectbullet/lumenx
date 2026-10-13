#!/bin/bash
# One-time setup on 192.168.8.231
# Run ONCE after first rsync: cd /data/aigc/lumenx && bash deploy/setup_231.sh
set -euo pipefail

PROJECT_DIR="/data/aigc/lumenx"
ENV_NAME="lumenx"
cd "$PROJECT_DIR"

echo "=========================================="
echo " LumenX @ 231 — One-time setup"
echo "=========================================="

# --- nvm (Node.js) ---
echo ""
echo "==> [0/5] Ensure Node.js 22+ (nvm)"
if ! command -v npm &>/dev/null; then
  for p in "$HOME/.nvm/nvm.sh"; do
    if [ -f "$p" ]; then
      export NVM_DIR="$HOME/.nvm"
      . "$p"
      echo "    Found nvm at: $NVM_DIR"
      break
    fi
  done
fi
if ! command -v npm &>/dev/null; then
  echo "    ERROR: npm not found. Please install nvm first."
  exit 1
fi
# 确保 Node 22+ (npm 10.8 有 "Exit handler never called!" bug, npm 12 需 Node 22+)
CURRENT_NODE=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$CURRENT_NODE" -lt 22 ]; then
  echo "    Node $(node -v) too old, upgrading to Node 22..."
  export NVM_DIR="$HOME/.nvm"
  . "$NVM_DIR/nvm.sh"
  nvm install 22
  nvm use 22
  nvm alias default 22
  npm install -g npm@latest 2>/dev/null || true
fi
echo "    Node: $(node -v)  npm: $(npm --version)"

# --- conda ---
echo ""
echo "==> [1/5] Init conda"
# conda activate 需要 shell 函数；PATH 中有 conda 可执行文件不代表已初始化。
if ! declare -F conda &>/dev/null; then
  # 尝试常见 conda 安装路径
  conda_exe="${CONDA_EXE:-}"
  for p in "${conda_exe%/bin/conda}" "$HOME/miniconda3" "$HOME/anaconda3" "/opt/conda" "/usr/local/miniconda3" "/usr/local/anaconda3"; do
    if [ -f "$p/etc/profile.d/conda.sh" ]; then
      source "$p/etc/profile.d/conda.sh"
      echo "    Found conda at: $p"
      break
    fi
  done
fi
if ! declare -F conda &>/dev/null; then
  echo "ERROR: conda shell initialization failed. Source your installation's etc/profile.d/conda.sh first." >&2
  exit 1
fi

# --- create env ---
echo ""
echo "==> [2/5] Create conda env '$ENV_NAME' (python 3.11)"
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "    exists, skip"
else
  conda create -n "$ENV_NAME" python=3.11 -y
fi
conda activate "$ENV_NAME"
echo "    Activated: $(which python)"

# --- ffmpeg ---
echo ""
echo "==> [3/5] Install ffmpeg (conda-forge)"
if ! command -v ffmpeg &>/dev/null; then
  conda install -c conda-forge ffmpeg -y
else
  echo "    ffmpeg already available: $(ffmpeg -version | head -1)"
fi

# --- python deps ---
echo ""
echo "==> [4/5] Install Python deps (with Tsinghua mirror, skip demucs)"
PIP_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"
pip install --upgrade pip -i "$PIP_INDEX"
# demucs 拉 torch+CUDA 太重 (~2GB), 先跳过让核心跑起来
# 生成不含 demucs/soundfile 的临时 requirements
grep -vE '^demucs|^soundfile' requirements.txt > /tmp/requirements.core.txt
pip install -r /tmp/requirements.core.txt -i "$PIP_INDEX"
rm -f /tmp/requirements.core.txt
# DeepSeek 走 openai 兼容接口, 必须装 openai 包
pip install "openai>=1.0.0" -i "$PIP_INDEX"
echo "    NOTE: demucs (人声分离) 未装, 需要时: pip install demucs soundfile -i $PIP_INDEX"

# --- frontend ---
echo ""
echo "==> [5/5] Install frontend deps (official npm source)"
if command -v npm &>/dev/null; then
  (cd frontend && npm install)
  # npm 12+ 默认拦截 install scripts, Next.js 依赖 SWC/esbuild 必须批准
  (cd frontend && npm install-scripts approve @swc/core esbuild @parcel/watcher unrs-resolver 2>/dev/null) || true
  (cd frontend && npm rebuild)
else
  echo "WARNING: npm not found. Please install Node.js 22+ and re-run."
fi

# --- output dirs ---
echo ""
echo "==> Create output dirs"
mkdir -p output/{assets/characters,assets/scenes,assets/props,audio,export,storyboard,video,uploads,video_inputs}
mkdir -p logs

echo ""
echo "=========================================="
echo " Setup complete!"
echo "=========================================="
echo ""
echo " Next steps:"
echo "   1) cp .env.231 .env && vim .env    # 填 OPENAI_API_KEY (和可选 DASHSCOPE_API_KEY)"
echo "   2) bash deploy/start_231.sh       # 启动后端 + 前端"
echo "   3) 浏览器访问 http://192.168.8.231:3008"
echo ""
echo " 日志: tail -f $PROJECT_DIR/logs/backend.log $PROJECT_DIR/logs/frontend.log"
