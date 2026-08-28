from __future__ import annotations

import json
import secrets
import sqlite3
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from .config import Config
from .policy import PolicyError
from .rewrite_proxy import pick_free_port, start_rewrite_proxy
from .scheduler import Scheduler
from .service import LightWorkerService
from .store import TaskStore


MAX_BODY_BYTES = 1_048_576
LOCAL_HOSTS = {"127.0.0.1", "::1", "[::1]"}


def host_allowed(host_header: str) -> bool:
    """Accept only exact loopback Host values, optionally with a valid port."""
    raw = host_header.strip().lower()
    if not raw:
        return False
    if raw in LOCAL_HOSTS:
        return True
    if raw.startswith("["):
        end = raw.find("]")
        if end <= 1 or raw[: end + 1] not in LOCAL_HOSTS:
            return False
        rest = raw[end + 1 :]
        return rest == "" or (rest.startswith(":") and rest[1:].isdigit() and 1 <= int(rest[1:]) <= 65535)
    host, separator, port = raw.partition(":")
    if host not in LOCAL_HOSTS:
        return False
    if not separator:
        return True
    return port.isdigit() and 1 <= int(port) <= 65535


def _handler_factory(service: LightWorkerService, token: str, static_root: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"LightWorker/{__version__}"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write(f"[web] {self.address_string()} {fmt % args}\n")

        def _host_allowed(self) -> bool:
            return host_allowed(self.headers.get("Host", ""))

        def _common_headers(self, content_type: str, length: int) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            )

        def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self._common_headers(content_type, len(body))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send_bytes(
                status,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _error(self, status: int, message: str) -> None:
            self._json(status, {"error": message})

        def _require_local_host(self) -> bool:
            if self._host_allowed():
                return True
            self._error(HTTPStatus.FORBIDDEN, "Invalid Host header")
            return False

        def _require_token(self) -> bool:
            if secrets.compare_digest(self.headers.get("X-LightWorker-Token", ""), token):
                return True
            self._error(HTTPStatus.FORBIDDEN, "Missing or invalid local session token")
            return False

        def _read_json(self) -> dict[str, Any]:
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Invalid Content-Length") from exc
            if size <= 0 or size > MAX_BODY_BYTES:
                raise ValueError("Request body must be between 1 byte and 1 MiB")
            raw = self.rfile.read(size)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Request body must be valid UTF-8 JSON") from exc
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def do_GET(self) -> None:  # noqa: N802
            if not self._require_local_host():
                return
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/api/health":
                    self._json(
                        HTTPStatus.OK,
                        {"status": "ok", "service": "lightworker", "version": __version__},
                    )
                    return
                if path == "/api/doctor":
                    self._json(HTTPStatus.OK, service.doctor())
                    return
                if path == "/api/tasks":
                    query = parse_qs(parsed.query)
                    status = query.get("status", [None])[0] or None
                    limit = int(query.get("limit", ["200"])[0])
                    self._json(HTTPStatus.OK, service.list_tasks(status, limit))
                    return
                if path == "/api/cache-metrics":
                    query = parse_qs(parsed.query)
                    model = query.get("model", ["deepseek/deepseek-v4-flash"])[0] or None
                    gateway = query.get("gateway", [None])[0] or None
                    raw_window = query.get("window_seconds", [None])[0]
                    window = int(raw_window) if raw_window else None
                    self._json(HTTPStatus.OK, service.cache_metrics(model, gateway, window))
                    return
                if path.startswith("/api/tasks/"):
                    parts = [unquote(part) for part in path.split("/") if part]
                    if len(parts) == 3:
                        self._json(HTTPStatus.OK, service.task(parts[2]))
                        return
                    if len(parts) == 4 and parts[3] == "events":
                        query = parse_qs(parsed.query)
                        after = int(query.get("after", ["0"])[0])
                        limit = int(query.get("limit", ["500"])[0])
                        self._json(HTTPStatus.OK, service.events(parts[2], after, limit))
                        return
                if path in {"/", "/index.html"}:
                    html = (static_root / "index.html").read_text(encoding="utf-8")
                    html = html.replace("__LIGHTWORKER_TOKEN__", token).replace(
                        "__LIGHTWORKER_VERSION__", __version__
                    )
                    self._send_bytes(HTTPStatus.OK, html.encode("utf-8"), "text/html; charset=utf-8")
                    return
                static = {
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                    "/logo.svg": ("logo.svg", "image/svg+xml"),
                    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
                    "/lightworker-app-icon.png": ("lightworker-app-icon.png", "image/png"),
                }
                if path in static:
                    name, content_type = static[path]
                    self._send_bytes(HTTPStatus.OK, (static_root / name).read_bytes(), content_type)
                    return
                self._error(HTTPStatus.NOT_FOUND, "Not found")
            except KeyError as exc:
                self._error(HTTPStatus.NOT_FOUND, f"Task not found: {exc.args[0]}")
            except (ValueError, PolicyError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Server error: {exc}")

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_local_host() or not self._require_token():
                return
            path = urlparse(self.path).path
            try:
                if path == "/api/orchestrate":
                    body = self._read_json()
                    self._json(HTTPStatus.ACCEPTED, service.orchestrate(**body))
                    return
                if path == "/api/tasks":
                    self._json(HTTPStatus.ACCEPTED, service.delegate_task(self._read_json()))
                    return
                if path == "/api/tasks/purge":
                    body = self._read_json()
                    self._json(HTTPStatus.OK, service.purge_history(
                        include_cancelled=bool(body.get("include_cancelled", True))
                    ))
                    return
                if path.startswith("/api/tasks/"):
                    parts = [unquote(part) for part in path.split("/") if part]
                    if len(parts) == 4 and parts[3] == "approve":
                        body = self._read_json()
                        self._json(HTTPStatus.OK, service.approve(
                            parts[2], body.get("approval_id"), body.get("scope_digest")
                        ))
                        return
                    if len(parts) == 4 and parts[3] == "cancel":
                        self._json(HTTPStatus.OK, service.cancel(parts[2]))
                        return
                    if len(parts) == 4 and parts[3] == "retry-fallback":
                        self._json(HTTPStatus.ACCEPTED, service.retry_fallback(parts[2]))
                        return
                    if len(parts) == 4 and parts[3] == "escalate":
                        body = self._read_json()
                        self._json(HTTPStatus.ACCEPTED, service.escalate(parts[2], body.get("profile")))
                        return
                self._error(HTTPStatus.NOT_FOUND, "Not found")
            except KeyError as exc:
                if path.startswith("/api/tasks/"):
                    self._error(HTTPStatus.NOT_FOUND, f"Task not found: {exc.args[0]}")
                else:
                    self._error(HTTPStatus.BAD_REQUEST, f"Missing field: {exc.args[0]}")
            except sqlite3.IntegrityError as exc:
                self._error(HTTPStatus.BAD_REQUEST, f"Invalid task relationship: {exc}")
            except (TypeError, ValueError, PolicyError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Server error: {exc}")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Cross-origin requests are not supported")

    return Handler


def create_http_server(
    host: str,
    port: int,
    service: LightWorkerService,
    token: str,
    static_root: Path,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _handler_factory(service, token, static_root))


def run_web(cfg: Config, host: str = "127.0.0.1", port: int = 8766, open_browser: bool = True) -> None:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("LightWorker Web only binds to a loopback address")
    rewrite_proxy = None
    for name, gateway in cfg.gateways.items():
        if gateway.enabled and gateway.base_url and not gateway.supports_output_schema:
            try:
                # The proxy forwards the full request path (e.g. /v1/responses),
                # so the upstream root must not include a trailing /v1 segment.
                upstream = gateway.base_url.rstrip("/")
                if upstream.endswith("/v1"):
                    upstream = upstream[:-3]
                api_key = None
                if gateway.api_key_env:
                    api_key = __import__("os").environ.get(gateway.api_key_env)
                proxy_port = pick_free_port(8319)
                proxy_server, _ = start_rewrite_proxy(upstream, api_key, port=proxy_port)
                rewrite_proxy = proxy_server
                cfg.set_gateway_base_url(name, f"http://127.0.0.1:{proxy_port}/v1")
                print(
                    f"Rewrite proxy for gateway {name}: {upstream} -> http://127.0.0.1:{proxy_port}/v1",
                    flush=True,
                )
            except OSError as exc:
                print(f"Warning: failed to start rewrite proxy for gateway {name}: {exc}", flush=True)
    store = TaskStore(cfg.db_path)
    scheduler = Scheduler(cfg, store)
    service = LightWorkerService(cfg, store, scheduler)
    scheduler.start_background(reconcile=True, allow_passive=True)
    token = secrets.token_urlsafe(32)
    static_root = cfg.package_root / "web"
    server = create_http_server(host, port, service, token, static_root)
    display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    url = f"http://{display_host}:{server.server_address[1]}/"
    print(f"LightWorker Web: {url}", flush=True)
    print("Press Ctrl+C to stop. Mutating API calls require the per-process browser token.", flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if rewrite_proxy is not None:
            rewrite_proxy.shutdown()
            rewrite_proxy.server_close()
        scheduler.stop(wait=True)
