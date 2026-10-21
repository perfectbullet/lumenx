"""Exercise actual start/stop supervision using an isolated local HTTP server."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("backendctl", Path(__file__).parents[1] / "scripts/backendctl.py")
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)

SERVER = """
import http.server, sys
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok": true}')
    def log_message(self, *args): pass
http.server.HTTPServer(('127.0.0.1', int(sys.argv[-1])), Handler).serve_forever()
"""


class BackendControlTests(unittest.TestCase):
    def test_http_classification_does_not_claim_auth_for_404(self):
        message, failed = ctl.classify_http(404, True)
        self.assertIn("NOT verified", message)
        self.assertEqual(failed, 0)
        self.assertEqual(ctl.classify_http(401, True)[1], 1)
        self.assertEqual(ctl.classify_http(503, False)[1], 1)

    def test_logs_hide_credentials_signed_urls_and_data(self):
        text = "secret-value https://x/path?token=private https://user:password@x/path Bearer abc data:image/png;base64,AAAA"
        masked = ctl.redact(text, {"DASHSCOPE_API_KEY": "secret-value"})
        for value in ("secret-value", "private", "user:password", "Bearer abc", "AAAA"):
            self.assertNotIn(value, masked)

    def test_missing_config_and_process_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ctl, "ROOT", Path(directory)):
            Path(directory, ".env").write_text("DASHSCOPE_API_KEY=file-key\nNO_PROXY=example.org\n")
            with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "process-key"}, clear=True):
                env = ctl.environment()
            self.assertEqual(env["DASHSCOPE_API_KEY"], "process-key")
            self.assertIn("example.org", env["NO_PROXY"])
            self.assertIn(".aliyuncs.com", env["NO_PROXY"])

    def test_lifecycle_idempotence_stale_pid_and_foreign_port(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ctl, "ROOT", Path(directory)):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            backend = ctl.Backend(port, timeout=5)
            backend.logs.mkdir()
            # Stale/reused PID points at the test runner: must never be signalled.
            backend.pidfile.write_text(str(os.getpid()))
            self.assertIsNone(backend.pid())
            real_popen = subprocess.Popen
            children = []

            def spawn(command, **kwargs):
                child = real_popen([sys.executable, "-c", SERVER, "uvicorn", ctl.APP, "--port", str(port)], **kwargs)
                children.append(child)
                return child

            try:
                with patch.object(ctl.subprocess, "Popen", side_effect=spawn), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(backend.start(), 0)
                    pid = backend.pid()
                    self.assertNotEqual(pid, os.getpid())
                    self.assertEqual(backend.start(), 0)
                    self.assertEqual(backend.pid(), pid)
                    self.assertEqual(len(children), 1)
                    self.assertEqual(backend.stop(), 0)
                    self.assertFalse(backend.pidfile.exists())
                    self.assertEqual(backend.stop(), 0)
                    # Port owned by a non-backend process must block start.
                    with socket.socket() as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind(("127.0.0.1", port)); sock.listen()
                        with self.assertRaisesRegex(RuntimeError, "another process"):
                            backend.start()
            finally:
                for child in children:
                    if child.poll() is None:
                        child.terminate()
                    child.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
