#!/usr/bin/env python3
"""Command-line client for a ChatDev 2.0 server, made for OpenClaw.

Standard library only (Python 3.9+), so it runs on a bare Windows install.

  python chatdev.py health
  python chatdev.py workflows
  python chatdev.py describe ChatDev_v1.yaml
  python chatdev.py run ChatDev_v1.yaml "Build a todo app" [--var KEY=VALUE] [--out DIR]
  python chatdev.py download <session_id> [--out DIR]

Settings come from environment variables, falling back to a KEY=VALUE file
(default: ~/.openclaw/chatdev.env, override with CHATDEV_ENV_FILE):

  CHATDEV_URL            default https://chatdev.hansvanleeuwen.com
  CHATDEV_CLIENT_ID      Cloudflare service token id (portal-gate)
  CHATDEV_CLIENT_SECRET  Cloudflare service token secret
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_URL = "https://chatdev.hansvanleeuwen.com"
ENV_FILE = Path(os.environ.get("CHATDEV_ENV_FILE", Path.home() / ".openclaw" / "chatdev.env"))


def load_settings(env_file: Path = ENV_FILE) -> dict:
    values = {}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("CHATDEV_URL", "CHATDEV_CLIENT_ID", "CHATDEV_CLIENT_SECRET"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    values.setdefault("CHATDEV_URL", DEFAULT_URL)
    values["CHATDEV_URL"] = values["CHATDEV_URL"].rstrip("/")
    return values


class ChatDevError(RuntimeError):
    pass


class Client:
    def __init__(self, settings: dict):
        self.base = settings["CHATDEV_URL"]
        self.headers = {"User-Agent": "openclaw-chatdev/1.0"}
        if settings.get("CHATDEV_CLIENT_ID") and settings.get("CHATDEV_CLIENT_SECRET"):
            self.headers["CF-Access-Client-Id"] = settings["CHATDEV_CLIENT_ID"]
            self.headers["CF-Access-Client-Secret"] = settings["CHATDEV_CLIENT_SECRET"]

    def _open(self, method: str, path: str, body=None, accept="application/json", timeout=60):
        data = None
        headers = dict(self.headers, Accept=accept)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            if exc.code in (401, 403):
                raise ChatDevError(
                    f"ChatDev refused access ({exc.code}). Check CHATDEV_CLIENT_ID/SECRET in {ENV_FILE}."
                ) from None
            raise ChatDevError(f"ChatDev {method} {path} failed ({exc.code}): {detail}") from None
        except urllib.error.URLError as exc:
            raise ChatDevError(f"Cannot reach {self.base}: {exc.reason}") from None

    def json(self, method: str, path: str, body=None):
        with self._open(method, path, body) as resp:
            text = resp.read().decode("utf-8")
        try:
            return json.loads(text)
        except ValueError:
            # The portal gate answers a missing/invalid token with a redirect page.
            raise ChatDevError(f"Unexpected non-JSON reply from {path}: {text[:200]}") from None

    def run(self, workflow: str, task: str, variables: dict, session_id: str, on_log):
        """Runs a workflow over SSE so long model calls survive proxy timeouts."""
        body = {"yaml_file": workflow, "task_prompt": task, "session_name": f"session_{session_id}"}
        if variables:
            body["variables"] = variables
        result = None
        with self._open("POST", "/api/workflow/run", body, accept="text/event-stream", timeout=300) as resp:
            event, data = None, []
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith(":"):
                    continue  # heartbeat
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].strip())
                elif line == "" and event:
                    payload = json.loads("\n".join(data)) if data else {}
                    if event == "log":
                        on_log(payload)
                    elif event == "completed":
                        result = payload
                    elif event == "error":
                        raise ChatDevError(payload.get("message", "workflow failed"))
                    event, data = None, []
        if result is None:
            raise ChatDevError("Stream ended without a result; the run may still finish on the server.")
        return result

    def download(self, session_id: str, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"chatdev_{session_id}.zip"
        partial = target.with_suffix(".zip.part")
        with self._open("GET", f"/api/sessions/{session_id}/download", accept="application/zip", timeout=300) as resp:
            first = resp.read(1 << 16)
            # A zip starts with "PK"; anything else (e.g. a login page after a redirect) is not a result.
            if not first.startswith(b"PK"):
                raise ChatDevError(f"Download of {session_id} returned no zip: {first[:120]!r}")
            with open(partial, "wb") as fh:
                chunk = first
                while chunk:
                    fh.write(chunk)
                    chunk = resp.read(1 << 16)
        # A dropped connection can end the body early without an error; only a complete zip counts.
        if not zipfile.is_zipfile(partial):
            partial.unlink()
            raise ChatDevError(f"Download of {session_id} was incomplete; try `download {session_id}` again.")
        os.replace(partial, target)
        return target


def parse_vars(items):
    variables = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"--var expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        variables[key] = value
    return variables


def main(argv=None) -> int:
    # Windows consoles and captured pipes may default to cp1252; model output can hold any character.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Use the ChatDev server from OpenClaw.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("workflows")
    p_desc = sub.add_parser("describe")
    p_desc.add_argument("workflow")
    p_run = sub.add_parser("run")
    p_run.add_argument("workflow")
    p_run.add_argument("task")
    p_run.add_argument("--var", action="append", help="workflow variable KEY=VALUE")
    p_run.add_argument("--out", help="also download the result zip to this folder")
    p_run.add_argument("--quiet", action="store_true", help="hide progress lines")
    p_dl = sub.add_parser("download")
    p_dl.add_argument("session_id")
    p_dl.add_argument("--out", default=".")
    args = parser.parse_args(argv)

    client = Client(load_settings())
    try:
        if args.cmd == "health":
            print(json.dumps(client.json("GET", "/health")))
        elif args.cmd == "workflows":
            for name in sorted(client.json("GET", "/api/workflows").get("workflows", [])):
                print(name)
        elif args.cmd == "describe":
            print(client.json("GET", f"/api/workflows/{args.workflow}/desc").get("description", ""))
        elif args.cmd == "run":
            session_id = f"oc{time.strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2)}"
            # Printed first, so a dropped stream can still be recovered with `download`.
            print(f"session_id: {session_id}", flush=True)
            started = time.time()

            def on_log(entry):
                if not args.quiet:
                    node = entry.get("node_id") or ""
                    msg = str(entry.get("message", ""))[:160]
                    print(f"[{int(time.time() - started):>4}s] {node} {msg}".rstrip(), file=sys.stderr)

            result = client.run(args.workflow, args.task, parse_vars(args.var), session_id, on_log)
            print(f"token_usage: {json.dumps(result.get('token_usage'))}")
            print("final_message:")
            print(result.get("final_message", ""))
            if args.out:
                print(f"zip: {client.download(session_id, Path(args.out))}")
        elif args.cmd == "download":
            print(client.download(args.session_id, Path(args.out)))
    except ChatDevError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
