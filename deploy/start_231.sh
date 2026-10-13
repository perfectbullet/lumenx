#!/bin/bash
# Start LumenX on 231 (dev mode, --reload hot-reload for both backend & frontend)
# Usage: cd /data/aigc/lumenx && bash deploy/start_231.sh
set -euo pipefail

PROJECT_DIR="/data/aigc/lumenx"
ENV_NAME="lumenx"
cd "$PROJECT_DIR"

# init nvm (for npm/next)
if ! command -v npm &>/dev/null; then
  for p in "$HOME/.nvm/nvm.sh"; do
    if [ -f "$p" ]; then
      export NVM_DIR="$HOME/.nvm"
      . "$p"; break
    fi
  done
fi

# conda activate 需要 shell 函数；PATH 中有 conda 可执行文件不代表已初始化。
if [ "${CONDA_DEFAULT_ENV:-}" != "$ENV_NAME" ]; then
  if ! declare -F conda &>/dev/null; then
    conda_exe="${CONDA_EXE:-}"
    for p in "${conda_exe%/bin/conda}" "$HOME/miniconda3" "$HOME/anaconda3" "/opt/conda" "/usr/local/miniconda3" "/usr/local/anaconda3"; do
      if [ -f "$p/etc/profile.d/conda.sh" ]; then
        source "$p/etc/profile.d/conda.sh"
        break
      fi
    done
  fi
  if ! declare -F conda &>/dev/null; then
    echo "ERROR: conda shell initialization failed. Source your installation's etc/profile.d/conda.sh first." >&2
    exit 1
  fi
  conda activate "$ENV_NAME"
else
  echo "==> Already in $ENV_NAME, skip conda activate"
fi
mkdir -p logs

echo "==> Stop any existing processes first"
bash deploy/stop_231.sh 2>/dev/null || true

echo "==> Start backend (uvicorn :17177, --reload)"
nohup python -m uvicorn src.apps.comic_gen.api:app \
  --reload --host 0.0.0.0 --port 17177 \
  > logs/backend.log 2>&1 &
echo $! > logs/backend.pid

echo "==> Start frontend (next dev :3008)"
cd frontend
nohup npm run dev > "$PROJECT_DIR/logs/frontend.log" 2>&1 &
echo $! > "$PROJECT_DIR/logs/frontend.pid"
cd "$PROJECT_DIR"

# 等几秒让服务起来再验证
sleep 4

BACKEND_OK=false
FRONTEND_OK=false

if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:17177/docs | grep -qE "200|307"; then
  BACKEND_OK=true
fi
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3008 | grep -qE "200|307"; then
  FRONTEND_OK=true
fi

echo ""
echo "=========================================="
echo " LumenX @ 231 Status"
echo "=========================================="
echo " Backend  : http://192.168.8.231:17177/docs   pid=$(cat logs/backend.pid)   [$BACKEND_OK]"
echo " Frontend : http://192.168.8.231:3008          pid=$(cat logs/frontend.pid)   [$FRONTEND_OK]"
echo " Logs     : tail -f $PROJECT_DIR/logs/backend.log $PROJECT_DIR/logs/frontend.log"
echo "=========================================="

if [ "$BACKEND_OK" = false ]; then
  echo "WARNING: Backend not responding. Check logs: tail -50 logs/backend.log"
fi
if [ "$FRONTEND_OK" = false ]; then
  echo "WARNING: Frontend not responding. Check logs: tail -50 logs/frontend.log"
fi
