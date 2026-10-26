"""Self-contained tests for the OpenClaw ChatDev client and installer.

Run: python integrations/openclaw/chatdev/tests/test_client.py
Spins up a fake ChatDev server (with the portal-gate token check) on localhost.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The fake server is local; keep any corporate/agent proxy out of the way.
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
sys.path.insert(0, str(HERE.parent / "scripts"))
import chatdev  # noqa: E402

TOKEN = {"cf-access-client-id": "id-1", "cf-access-client-secret": "secret-1"}
RUNS = []


class FakeChatDev(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _authorized(self):
        if all(self.headers.get(k) == v for k, v in TOKEN.items()):
            return True
        self.send_response(401)
        self.end_headers()
        self.wfile.write(b"Unauthorized")
        return False

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/health":
            return self._json({"status": "healthy"})
        if self.path == "/api/workflows":
            return self._json({"workflows": ["demo_simple.yaml", "ChatDev_v1.yaml"]})
        if self.path == "/api/workflows/ChatDev_v1.yaml/desc":
            return self._json({"description": "Software company"})
        if self.path == "/api/sessions/cut/download":
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b"PK\x03\x04truncated")
            self.close_connection = True
            return
        if self.path == "/api/sessions/login/download":
            return self._json({"html": "<p>login</p>"})
        if self.path.startswith("/api/sessions/") and self.path.endswith("/download"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("main.py", "print('hi')\n")
            body = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json({"detail": "not found"}, 404)

    def do_POST(self):
        if not self._authorized():
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        RUNS.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if body["yaml_file"] == "emoji.yaml":
            events = [("completed", {"status": "completed", "final_message": "Built a game \U0001F3AE",
                                     "token_usage": {}, "output_dir": "/x"})]
        elif body["yaml_file"] == "broken.yaml":
            events = [("error", {"message": "Failed to run workflow: 429 insufficient_quota"})]
        else:
            events = [("started", {}), ("log", {"node_id": "CEO", "message": "planning"}),
                      ("completed", {"status": "completed", "final_message": "Built a todo app.",
                                     "token_usage": {"total": 42}, "output_dir": "/x"})]
        self.wfile.write(b": ping\n\n")
        for name, data in events:
            self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeChatDev)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def call(self, *argv, settings=None):
        settings = settings or {"CHATDEV_URL": self.url, "CHATDEV_CLIENT_ID": "id-1", "CHATDEV_CLIENT_SECRET": "secret-1"}
        out, err = io.StringIO(), io.StringIO()
        original = chatdev.load_settings
        chatdev.load_settings = lambda: settings
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = chatdev.main(list(argv))
        finally:
            chatdev.load_settings = original
        return code, out.getvalue(), err.getvalue()

    def test_health_and_workflows(self):
        self.assertEqual(self.call("health")[1].strip(), '{"status": "healthy"}')
        self.assertEqual(self.call("workflows")[1].split(), ["ChatDev_v1.yaml", "demo_simple.yaml"])
        self.assertEqual(self.call("describe", "ChatDev_v1.yaml")[1].strip(), "Software company")

    def test_run_streams_and_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.call("run", "ChatDev_v1.yaml", "todo app", "--var", "A=1", "--out", tmp)
            self.assertEqual(code, 0, err)
            self.assertIn("final_message:\nBuilt a todo app.", out)
            self.assertIn("CEO planning", err)
            sent = RUNS[-1]
            self.assertTrue(sent["session_name"].startswith("session_oc"))
            self.assertEqual(sent["variables"], {"A": "1"})
            session_id = out.split("session_id: ")[1].split()[0]
            self.assertEqual(sent["session_name"], f"session_{session_id}")
            self.assertTrue(zipfile.is_zipfile(Path(tmp) / f"chatdev_{session_id}.zip"))

    def test_errors_are_clear(self):
        code, _, err = self.call("run", "broken.yaml", "x")
        self.assertEqual(code, 1)
        self.assertIn("insufficient_quota", err)
        code, _, err = self.call("health", settings={"CHATDEV_URL": self.url})
        self.assertEqual(code, 1)
        self.assertIn("refused access (401)", err)
        code, _, err = self.call("health", settings={"CHATDEV_URL": "http://127.0.0.1:1"})
        self.assertIn("Cannot reach", err)

    def test_download_rejects_non_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.call("download", "login", "--out", tmp)
            self.assertEqual(code, 1)
            self.assertIn("returned no zip", err)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_download_rejects_truncated_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.call("download", "cut", "--out", tmp)
            self.assertEqual(code, 1)
            self.assertTrue("incomplete" in err or "failed" in err or "IncompleteRead" in err, err)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_unicode_output_survives_legacy_console(self):
        # A cp1252 pipe (Windows default when an agent captures output) must not crash on emoji.
        env = dict(os.environ, PYTHONIOENCODING="cp1252", CHATDEV_URL=self.url, CHATDEV_CLIENT_ID="id-1",
                   CHATDEV_CLIENT_SECRET="secret-1", CHATDEV_ENV_FILE=os.devnull)
        r = subprocess.run([sys.executable, str(HERE.parent / "scripts" / "chatdev.py"), "run", "emoji.yaml", "x"],
                           env=env, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Built a game \U0001F3AE".encode("utf-8"), r.stdout)

    def test_session_id_printed_even_when_run_fails(self):
        code, out, _ = self.call("run", "broken.yaml", "x")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("session_id: oc"))

    def test_settings_file_and_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "chatdev.env"
            env_file.write_text('# c\nCHATDEV_CLIENT_ID="a"\nCHATDEV_CLIENT_SECRET=b\n', encoding="utf-8")
            os.environ["CHATDEV_URL"] = "https://example.test/"
            try:
                s = chatdev.load_settings(env_file)
            finally:
                del os.environ["CHATDEV_URL"]
            self.assertEqual((s["CHATDEV_CLIENT_ID"], s["CHATDEV_CLIENT_SECRET"], s["CHATDEV_URL"]),
                             ("a", "b", "https://example.test"))

    def test_installer_reads_vault_and_installs_skill(self):
        with tempfile.TemporaryDirectory() as home:
            vault_env = Path(home) / "Documents" / "SecondBrainVault" / "_skill" / "adapters" / ".env"
            vault_env.parent.mkdir(parents=True)
            vault_env.write_text(
                f"CF_ACCESS_CLAUDE_CLIENT_ID=id-1\nCF_ACCESS_CLAUDE_CLIENT_SECRET=secret-1\nCHATDEV_URL={self.url}\n",
                encoding="utf-8")
            (Path(home) / ".openclaw").mkdir()
            env = dict(os.environ, HOME=home, USERPROFILE=home, CHATDEV_CLIENT_DIR=str(Path(home) / "AI" / "chatdev-client"))
            r = subprocess.run([sys.executable, str(HERE.parent / "install.py")], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("INSTALL OK", r.stdout)
            self.assertNotIn("secret-1", r.stdout + r.stderr)
            skill = (Path(home) / ".openclaw" / "workspace" / "skills" / "chatdev" / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("{{", skill)
            self.assertIn(str(Path(home) / "AI" / "chatdev-client" / "scripts" / "chatdev.py"), skill)
            self.assertIn("CHATDEV_CLIENT_SECRET=secret-1", (Path(home) / ".openclaw" / "chatdev.env").read_text())
            # Running the installed copy's own installer keeps the client in place.
            installed = Path(home) / "AI" / "chatdev-client"
            r = subprocess.run([sys.executable, str(installed / "install.py")], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((installed / "scripts" / "chatdev.py").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
