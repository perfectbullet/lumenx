#!/usr/bin/env python3
"""Linux/macOS backend operations; no generation requests or dependency installs."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
APP = "src.apps.comic_gen.api:app"
sys.path.insert(0, str(ROOT))


def environment():
    from dotenv import dotenv_values
    values = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    values.update(os.environ)  # Same precedence as backend load_dotenv(override=False).
    bypass = values.get("NO_PROXY", values.get("no_proxy", ""))
    bypass = ",".join(dict.fromkeys(filter(None, bypass.split(",") + [
        ".aliyuncs.com", "localhost", "127.0.0.1", "::1",
    ])))
    values.update(NO_PROXY=bypass, no_proxy=bypass, PYTHONUNBUFFERED="1")
    return values


def redact(text, env):
    for key, value in env.items():
        if re.search(r"KEY|SECRET|TOKEN|PASSWORD|MONGO.*URI", key, re.I) and value:
            text = text.replace(value, "<redacted>")
    text = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?<redacted>", text)
    text = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1<redacted>@", text)
    text = re.sub(r"(?i)(Bearer|Token)\s+[\w.\-]+", r"\1 <redacted>", text)
    text = re.sub(r"data:[^;\s]+;base64,[\w+/=]+", "<data-uri>", text)
    return text


def inspect_process(pid):
    """Read command + cwd without exposing environment or matching other apps."""
    try:
        proc = Path(f"/proc/{pid}")
        if proc.exists():
            if (proc / "stat").read_text().split(")", 1)[1].split()[0] == "Z":
                return None
            args = (proc / "cmdline").read_bytes().decode().split("\0")
            cwd = (proc / "cwd").resolve()
        else:
            args = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True).split()
            result = subprocess.check_output(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], text=True)
            cwd = Path(next(s[1:] for s in result.splitlines() if s.startswith("n")))
        return args, cwd
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
        return None


class Backend:
    def __init__(self, port=17177, timeout=45):
        self.port, self.timeout = port, timeout
        self.logs = ROOT / "logs"
        self.pidfile = self.logs / "backend.pid"
        self.logfile = self.logs / "backend.log"
        self.env = environment()

    def owns(self, pid):
        result = inspect_process(pid)
        if not result:
            return False
        args, cwd = result
        return (cwd == ROOT and APP in args and "uvicorn" in args
                and "--port" in args and args[args.index("--port") + 1] == str(self.port))

    def pid(self):
        if self.pidfile.exists():
            try:
                pid = int(self.pidfile.read_text().strip())
                if self.owns(pid):
                    return pid
            except ValueError:
                pass
        # Recover an existing backend when a PID file is stale/missing.
        if Path("/proc").exists():
            candidates = [int(p.name) for p in Path("/proc").iterdir() if p.name.isdigit()]
        else:
            candidates = [int(p) for p in subprocess.check_output(["ps", "-axo", "pid="], text=True).split()]
        matches = [pid for pid in candidates if self.owns(pid)]
        if len(matches) > 1:
            raise RuntimeError("Multiple matching backends found; inspect processes before stopping anything")
        return matches[0] if matches else None

    def healthy(self):
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{self.port}/health", timeout=2) as response:
                return response.status == 200 and json.load(response).get("ok") is True
        except (OSError, ValueError):
            return False

    def listening(self):
        with socket.socket() as sock:
            sock.settimeout(1)
            return sock.connect_ex(("127.0.0.1", self.port)) == 0

    def status(self):
        pid, health = self.pid(), self.healthy()
        print(f"Backend: {'RUNNING' if pid and health else 'UNHEALTHY' if pid else 'STOPPED'}")
        print(f"Project: {ROOT}\nPython: {sys.executable}\nPID: {pid or '-'}\nPort: {self.port}")
        print(f"Health: {'OK' if health else 'FAIL'}\nLog: {self.logfile}")
        return 0 if pid and health else 1

    def start(self, reload=False):
        pid = self.pid()
        if pid:
            print(f"Already running (PID {pid}); no duplicate process started.")
            return self.status()
        if self.listening():
            raise RuntimeError(f"Port {self.port} belongs to another process; refusing to start")
        self.logs.mkdir(exist_ok=True)
        cmd = [sys.executable, "-m", "uvicorn", APP, "--host", "0.0.0.0", "--port", str(self.port)]
        if reload:
            cmd.append("--reload")
        with self.logfile.open("ab") as log:
            log.write(f"\n=== backend start {time.strftime('%Y-%m-%d %H:%M:%S %z')} ===\n".encode())
            child = subprocess.Popen(cmd, cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log, start_new_session=True)
        self.pidfile.write_text(str(child.pid) + "\n")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"Backend exited ({child.returncode}); run ./backend.sh logs")
            if self.healthy():
                return self.status()
            time.sleep(0.5)
        raise RuntimeError("Startup health check timed out; process retained for diagnosis; run status/logs")

    def stop(self):
        pid = self.pid()
        if not pid:
            print("Already stopped; no process signalled.")
            return 0
        print(f"Stopping backend PID {pid} (graceful SIGTERM)…", flush=True)
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if not self.owns(pid) and not self.listening():
                self.pidfile.unlink(missing_ok=True)
                print("Stopped.")
                return 0
            time.sleep(0.5)
        raise RuntimeError("Graceful stop timed out; no SIGKILL sent. Check active jobs and logs")

    def show_env(self):
        print(f"Config: {ROOT / '.env'} (file values + process overrides; secrets never printed)")
        print(f"Python: {sys.executable}\nNO_PROXY: {redact(self.env['NO_PROXY'], self.env)}")
        keys = ["DASHSCOPE_API_KEY", "OPENAI_API_KEY", "KLING_ACCESS_KEY", "KLING_SECRET_KEY", "VIDU_API_KEY",
                "MULEROUTER_API_KEY", "MULERUN_TOKEN", "ALIBABA_CLOUD_ACCESS_KEY_ID",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "OSS_BUCKET_NAME", "OSS_ENDPOINT",
                "MONGODB_URI", "LUMENX_MONGODB_URI", "HTTP_PROXY", "HTTPS_PROXY"]
        for key in keys:
            print(f"{key}: {'SET' if self.env.get(key, '').strip() else 'UNSET'}")
        for key in sorted(k for k in self.env if k.endswith("_BASE_URL") or k in ("LUMENX_STORAGE_BACKEND", "MONGODB_DATABASE", "LLM_PROVIDER", "OPENAI_MODEL", "OSS_ENABLE")):
            print(f"{key}: {redact(self.env[key], self.env)}")
        print("Restart after editing .env; this checks the next start, not in-memory hot changes.")
        return 0

    def show_logs(self, count, follow=False):
        if not self.logfile.exists():
            raise RuntimeError("No backend log yet")
        from collections import deque
        with self.logfile.open(errors="replace") as log:
            for line in deque(log, maxlen=count):
                print(redact(line.rstrip(), self.env)[:2000])
            while follow:
                line = log.readline()
                if line:
                    print(redact(line.rstrip(), self.env)[:2000], flush=True)
                else:
                    time.sleep(0.3)
        return 0

    def models(self, provider):
        from src.utils.endpoints import PROVIDER_DEFAULTS
        defaults = {**PROVIDER_DEFAULTS, "OPENAI": "https://api.openai.com/v1"}
        targets = list(defaults) if provider == "all" else [provider.upper()]
        failures = 0
        print("Read-only GET probes; no generation/billing. HTTP reachability is not model capability validation.")
        # Use the same effective proxy/environment settings as the launched backend.
        import requests
        with requests.Session() as session:
            session.trust_env = False
            from requests.utils import should_bypass_proxies
            for name in targets:
                base = self.env.get(name + "_BASE_URL") or defaults[name]
                headers = {}
                if name == "DASHSCOPE":
                    key = self.env.get("DASHSCOPE_API_KEY")
                    url = base.rstrip("/") + "/compatible-mode/v1/models"
                elif name == "OPENAI":
                    key = self.env.get("OPENAI_API_KEY")
                    url = base.rstrip("/") + "/models"
                elif name == "KLING":
                    key = self.env.get("KLING_ACCESS_KEY")
                    secret = self.env.get("KLING_SECRET_KEY")
                    if key and secret:
                        import jwt
                        key = jwt.encode({"iss": key, "exp": int(time.time()) + 120, "nbf": int(time.time()) - 5}, secret, algorithm="HS256")
                    else:
                        key = None
                    url = base.rstrip("/") + "/videos/text2video?pageNum=1&pageSize=1"
                else:
                    key = self.env.get(name + "_API_KEY")
                    url = base.rstrip("/")
                if not key:
                    print(f"{name}: SKIP — credentials not configured")
                    continue
                headers["Authorization"] = ("Token " if name == "VIDU" else "Bearer ") + key
                proxies = {} if should_bypass_proxies(url, no_proxy=self.env["NO_PROXY"]) else {
                    scheme: self.env.get(scheme + "_proxy") or self.env.get(scheme.upper() + "_PROXY", "")
                    for scheme in ("http", "https", "all")
                }
                try:
                    # Redirects disabled to keep credentials at the configured origin.
                    with session.get(url, headers=headers, timeout=(5, 10), allow_redirects=False,
                                     stream=True, proxies=proxies) as response:
                        code = response.status_code
                        result, failed = classify_http(code, name in ("DASHSCOPE", "KLING", "OPENAI"))
                        failures += failed
                        print(f"{name}: HTTP {code} — {result}")
                except requests.RequestException as exc:
                    failures += 1
                    print(f"{name}: FAIL — {type(exc).__name__} (network/TLS/proxy)")
        cli = shutil.which("mulerun", path=self.env.get("PATH"))
        if provider in ("all", "mulerouter") and cli:
            try:
                result = subprocess.run([cli, "login", "status"], env=self.env, capture_output=True, timeout=10)
                print(f"MuleRun CLI: {'LOGGED IN' if result.returncode == 0 else 'NOT LOGGED IN'}")
            except subprocess.TimeoutExpired:
                failures += 1
                print("MuleRun CLI: TIMEOUT")
        return 1 if failures else 0


def classify_http(code, auth_probe):
    if code in (401, 403):
        return "reachable; authentication/permission rejected", 1
    if code == 429:
        return "reachable; rate/quota limited", 1
    if code >= 500:
        return "reachable; provider server error", 1
    if 200 <= code < 300 and auth_probe:
        return "read-only authenticated endpoint OK; generation permissions not tested", 0
    return "reachable; authentication and generation permissions NOT verified", 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "restart", "status", "logs", "env", "models"])
    parser.add_argument("--port", type=int, default=17177)
    parser.add_argument("--timeout", type=int, default=45, help="Start/stop deadline in seconds")
    parser.add_argument("--reload", action="store_true", help="Enable dev auto-reload on start/restart (default off)")
    parser.add_argument("-n", "--lines", type=int, default=50)
    parser.add_argument("-f", "--follow", action="store_true")
    parser.add_argument("--provider", choices=["all", "dashscope", "openai", "kling", "vidu", "mulerouter"], default="all")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.timeout < 1 or args.lines < 1:
        parser.error("Invalid port, timeout or line count")
    backend = Backend(args.port, args.timeout)
    try:
        if args.command in ("start", "stop", "restart"):
            backend.logs.mkdir(exist_ok=True)
            with (backend.logs / "backendctl.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError("Another backend operation is running")
                if args.command == "restart":
                    backend.stop()
                    return backend.start(args.reload)
                return backend.start(args.reload) if args.command == "start" else backend.stop()
        if args.command == "env":
            return backend.show_env()
        if args.command == "models":
            return backend.models(args.provider)
        if args.command == "logs":
            return backend.show_logs(args.lines, args.follow)
        return backend.status()
    except (RuntimeError, OSError) as exc:
        print("ERROR: " + redact(str(exc), backend.env), file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
