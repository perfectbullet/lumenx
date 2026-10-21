# 后端管理

统一入口是项目根目录的 `backend.sh`。231 的项目目录为 `/data/aigc/lumenx`，
Python 为 `/home/zenking/miniconda3/envs/lumenx/bin/python`，端口默认 `17177`。

```bash
ssh zenking@192.168.8.231
cd /data/aigc/lumenx

./backend.sh start                 # 后台启动；已运行则只检查，不重复启动
./backend.sh restart               # 优雅停止后启动，等待 /health 成功
./backend.sh stop                  # 仅停止本项目、本端口的后端
./backend.sh status                # PID、端口、Python、健康状态、日志位置
./backend.sh logs -n 80            # 最近 80 行，脱敏输出
./backend.sh logs -f               # 持续查看日志，Ctrl+C 退出
./backend.sh env                   # 配置来源、凭据是否已设置、代理及端点
./backend.sh models                # 外部服务只读检查，不提交生成请求
./backend.sh models --provider dashscope
./backend.sh models --provider openai
```

开发环境需要代码热加载时，在启动或重启时加 `--reload`：

```bash
./backend.sh restart --reload
```

默认不启用热加载。`.env` 修改后需要重启。`env` 显示的是下次启动使用的配置，
以 `.env` 为基础、当前调用进程环境变量优先；不声称读取了运行中应用的全部内存配置。
本入口用于源码开发/服务器部署，不加载打包桌面版的 `~/.lumen-x/config.json`。

Python 选择顺序：`LUMENX_PYTHON` → 项目 `.venv/bin/python` →
`~/miniconda3/envs/lumenx/bin/python` → `python3`。不会自动安装依赖。
需要指定解释器、端口或启动等待时间时：

```bash
LUMENX_PYTHON=/path/to/python ./backend.sh start --port 17177 --timeout 60
```

生命周期命令用文件锁防止并发操作，并核对进程的工作目录、Uvicorn 应用名及端口。
PID 文件缺失时可找回已有进程；无关进程占用端口时拒绝启动；优雅停止超时不会强杀。
标准输出追加至 `logs/backend.log`，不会覆盖旧日志。服务仍是后台进程，机器重启后
需要手动启动；本脚本未安装 systemd 或开机自启。

`models` 对 DashScope / OpenAI 兼容服务调用模型列表，对 Kling 调用只读列表接口；
Vidu / MuleRouter 只探测服务根地址。缺少凭据显示 `SKIP`，401/403、限流、5xx、
网络错误返回失败。根地址的 404 仅表示 HTTP 服务可达，不代表鉴权成功。
只读检查不证明图像/视频模型的权限、余额、参数组合或实际生成可用。
日志检查隐藏当前凭据值、Bearer token、URL 查询参数及图片 data URI。

本地同步代码到 231 使用 `./scripts/sync-231.sh [--dry-run]`。
前端单独使用 `cd frontend && npm run dev`；后端命令不会停止前端。

旧脚本清单与迁移说明见 `scripts/archive/2026-10-21/README.md`。
