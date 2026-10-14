#!/bin/bash
# Stop only LumenX processes belonging to this deployment directory.
# Usage: cd /data/aigc/lumenx && bash deploy/stop_231.sh
set -u
PROJECT_DIR="${LUMENX_PROJECT_DIR:-/data/aigc/lumenx}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0
PROJECT_DIR="$(pwd -P)"

is_lumenx_process() {
  local pid="$1" cwd command
  [[ "$pid" =~ ^[0-9]+$ ]] && [ "$pid" != "$$" ] || return 1
  cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null)" || return 1
  [[ "$cwd" == "$PROJECT_DIR" || "$cwd" == "$PROJECT_DIR/frontend" ]] || return 1
  command="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)" || return 1
  [[ "$command" == *"uvicorn src.apps.comic_gen.api"* ||
     "$command" == *"next dev"* || "$command" == *"next-server"* ||
     "$command" == *"npm run dev"* ]]
}

stop_process_tree() {
  local pid="$1" child
  # Stop children as well as npm/uvicorn launchers so they do not outlive them.
  while IFS= read -r child; do
    [ -n "$child" ] && stop_process_tree "$child"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "Stopped LumenX process $pid" || true
  fi
}

for file in logs/backend.pid logs/frontend.pid; do
  [ -f "$file" ] || continue
  pid="$(cat "$file")"
  if is_lumenx_process "$pid"; then
    stop_process_tree "$pid"
  else
    echo "Ignoring stale or unrelated PID in $file"
  fi
  rm -f "$file"
done

# Recover missing PID files without killing other projects on the same server.
while IFS= read -r pid; do
  if is_lumenx_process "$pid"; then
    stop_process_tree "$pid"
  fi
done < <(pgrep -f 'uvicorn src.apps.comic_gen.api|next dev|next-server|npm run dev' 2>/dev/null || true)
