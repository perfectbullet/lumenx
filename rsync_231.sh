#!/bin/bash
# Sync LumenX code -> 192.168.8.231:/data/aigc/lumenx
# Usage: ./rsync_231.sh [--dry-run] [--delete]
#   --dry-run  只预览不实际传输
#   --delete   同时删除远端 stale 文件（默认不带，保护远端手动创建的文件）
set -euo pipefail

REMOTE_HOST="zenking@192.168.8.231"
REMOTE_DIR="/data/aigc/lumenx"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EXCLUDE_FILE="$(mktemp)"
trap 'rm -f "$EXCLUDE_FILE"' EXIT
cat > "$EXCLUDE_FILE" <<'EOF'
.git/
.venv/
node_modules/
**/node_modules/
.next/
frontend/.next/
dist/
build/
__pycache__/
**/__pycache__/
*.pyc
*.pyo
output/
logs/
.env
.env.local
.env.*
docs/agents/context/
docs/agents/raw/
.DS_Store
*.log
*.pid
.vscode/
.idea/
.cache/
.pytest_cache/
**/.pytest_cache/
.mypy_cache/
frontend/dist/
frontend/out/
EOF

echo "==> rsync $SCRIPT_DIR -> $REMOTE_HOST:$REMOTE_DIR"
ARGS=()
[[ "${1:-}" == "--dry-run" ]] && ARGS+=("--dry-run") && echo "    (dry-run)"
[[ "${2:-}" == "--delete" || "${1:-}" == "--delete" ]] && ARGS+=("--delete") && echo "    (delete stale files on remote)"

# ensure remote dir exists
ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"

rsync -avz "${ARGS[@]}" \
  --include='.env.example' --include='.env.*.example' \
  --exclude-from="$EXCLUDE_FILE" \
  -e "ssh" \
  "$SCRIPT_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

echo ""
echo "==> Done."
echo "    SSH in: ssh $REMOTE_HOST"
echo "    First time setup:  cd $REMOTE_DIR && bash deploy/setup_231.sh"
echo "    Start services:    cd $REMOTE_DIR && bash deploy/start_231.sh"
