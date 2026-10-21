# 2026-10-21 脚本归档

保留历史脚本便于查阅；日常运维使用根目录 `backend.sh`。
归档脚本不再作为推荐运维入口，不保证从本目录直接运行。

| 原路径 | 归档位置（相对本目录） | 原因 / 替代 |
|---|---|---|
| `start_backend.sh` | `start_backend.sh` | 由 `backend.sh start --reload` 替代 |
| `start_frontend.sh` | `start_frontend.sh` | 由 `cd frontend && npm run dev` 替代；统一开发仍用 `npm run dev` |
| `deploy/start_231.sh` | `deploy/start_231.sh` | 旧的前后端联合重启；后端改用 `backend.sh` |
| `deploy/stop_231.sh` | `deploy/stop_231.sh` | 包含宽泛 pkill；改为核验项目和端口的进程管理 |
| `deploy/setup_231.sh` | `deploy/setup_231.sh` | 231 一次性安装的历史记录，现有环境已安装 |
| `build_mac.sh` | `build_mac.sh` | 旧 PyInstaller Mac 构建，保留按需调用；主路径为 Tauri |
| `create_icon.sh` | `create_icon.sh` | 无当前调用引用的手工图标转换脚本 |

仍在使用的脚本不归档：

- `build_tauri_mac.sh` 与其调用的 `build_sidecar.sh`：当前 Tauri 构建链。
- `build_windows.ps1`：现有 Windows 构建工作流仍引用。
- `git_push.sh`：Git hook 和协作流程仍引用。
- `scripts/dev-setup.js` / `scripts/start-backend.js`：`npm run dev` 仍调用。
- 原 `rsync_231.sh` 迁到 `scripts/sync-231.sh`：仍承担代码同步，已修正项目根目录定位。

旧 Mac 构建如确有需要，在项目根目录执行：

```bash
bash scripts/archive/2026-10-21/build_mac.sh
```

该历史构建脚本现显式默认使用清华 PyPI 镜像。工作流镜像已更新路径并通过 parity 检查。
231 上归档保留的是远端已有原文件，不覆盖为本地的不同版本。
代码同步排除 `scripts/archive/`，避免以后同步覆盖服务器保留的原始归档。
