
from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import lightworker
from lightworker.web_server import create_http_server, host_allowed


class FakeService:
    class Config:
        cache_warm_window_seconds = 300

    cfg = Config()

    def doctor(self):
        return {"allowed_models": ["gpt-5.6-sol"], "gateways": [{"name": "opencodex", "enabled": True, "reachable": True, "credential_configured": True, "response_mode": "native", "default": True}]}

    def list_tasks(self, status=None, limit=200):
        return {"tasks": [], "status": status, "limit": limit}

    def orchestrate(self, **body):
        return {"root_task_id": "task-test", "status": "queued", **body}

    def retry_fallback(self, task_id):
        return {"task_id": "task-retry", "status": "queued", "retry_of": task_id, "gateway": "cliproxyapi"}

    def escalate(self, task_id, profile=None):
        return {"task_id": "task-deep", "status": "queued", "escalation_of": task_id, "profile": profile or "deep_worker"}

    def cache_metrics(self, model=None, gateway=None, window_seconds=None):
        return {"model": model, "gateway": gateway, "window_seconds": window_seconds, "warm": {"samples": 0, "cache_hit_rate": None}, "cohorts": [], "target": {"status": "insufficient_samples"}}


def request_json(url: str, method: str = "GET", token: str | None = None, body=None):
    headers = {"Host": "127.0.0.1"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-LightWorker-Token"] = token
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_web_health_static_and_mutation_token():
    static_root = Path(lightworker.__file__).resolve().parent / "web"
    server = create_http_server("127.0.0.1", 0, FakeService(), "test-token", static_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, payload = request_json(f"{base}/api/health")
        assert status == 200
        assert payload == {"status": "ok", "service": "lightworker"}

        status, payload = request_json(f"{base}/api/cache-metrics?model=deepseek%2Fdeepseek-v4-flash&window_seconds=60")
        assert status == 200
        assert payload["window_seconds"] == 60

        with urlopen(f"{base}/", timeout=2) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "LightWorker" in html
            assert "test-token" in html
            assert "/favicon.svg" in html
            assert "/lightworker-app-icon.png" in html
            assert 'type="button" class="icon-button" id="close-task-dialog"' in html
            assert 'id="single-gateway"' in html
            assert 'id="single-profile"' in html
            assert 'id="detail-route"' in html

        with urlopen(f"{base}/logo.svg", timeout=2) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "image/svg+xml"
            assert b"LightWorker" in response.read()

        with urlopen(f"{base}/lightworker-app-icon.png", timeout=2) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "image/png"
            assert response.read(8) == b"\x89PNG\r\n\x1a\n"

        try:
            request_json(
                f"{base}/api/orchestrate",
                method="POST",
                body={"objective": "test", "workspace": "G:\\workspace"},
            )
        except HTTPError as exc:
            assert exc.code == 403
        else:  # pragma: no cover - protects the security boundary
            raise AssertionError("Mutation without a token should be rejected")

        status, payload = request_json(
            f"{base}/api/orchestrate",
            method="POST",
            token="test-token",
            body={"objective": "test", "workspace": "G:\\workspace"},
        )
        assert status == 202
        assert payload["root_task_id"] == "task-test"

        status, payload = request_json(
            f"{base}/api/tasks/task-old/retry-fallback",
            method="POST",
            token="test-token",
            body={},
        )
        assert status == 202
        assert payload["retry_of"] == "task-old"

        status, payload = request_json(
            f"{base}/api/tasks/task-old/escalate",
            method="POST",
            token="test-token",
            body={},
        )
        assert status == 202
        assert payload["profile"] == "deep_worker"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_host_validation_rejects_ambiguous_or_non_loopback_values() -> None:
    assert host_allowed("127.0.0.1:8766")
    assert host_allowed("[::1]:8766")
    assert not host_allowed("localhost:8766")
    assert not host_allowed("127.0.0.1.example:8766")
    assert not host_allowed("127.0.0.1:99999")
