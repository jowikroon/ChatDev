import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import runtime.sdk  # noqa: F401  (import order: breaks the check/workflow import cycle)
from server.routes import execute_sync


def test_stream_sends_heartbeats_while_workflow_is_silent(monkeypatch):
    def slow_run(**kwargs):
        time.sleep(0.5)
        return None, {"token_usage": {}, "output_dir": Path(".")}

    monkeypatch.setattr(execute_sync, "_run_workflow_with_logger", slow_run)
    monkeypatch.setattr(execute_sync, "_SSE_HEARTBEAT_SECONDS", 0.15)
    app = FastAPI()
    app.include_router(execute_sync.router)

    with TestClient(app) as client:
        resp = client.post(
            "/api/workflow/run",
            json={"yaml_file": "x.yaml", "task_prompt": "t"},
            headers={"Accept": "text/event-stream"},
        )

    body = resp.text
    assert resp.headers["x-accel-buffering"] == "no"
    assert ": ping" in body
    assert body.index(": ping") < body.index("event: completed")
    assert body.rstrip().endswith("}")
