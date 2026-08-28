"""Local response-format rewriting proxy for gateways that reject json_schema.

The Codex CLI always sends ``text.format = {type: json_schema, ...}`` in the
Responses API body when run with ``--json``.  Some translated gateways
(e.g. CLIProxyAPI) reject that field with ``invalid_request_error``, and their
``json_object`` mode additionally requires the literal word "json" in the
prompt, which Codex prompts do not guarantee.  This module implements a tiny
loopback proxy that drops the ``text.format`` block and forwards everything
else verbatim, so the Codex CLI and the LightWorker event pipeline keep
working unchanged.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _rewrite_text_format(body: dict[str, Any]) -> dict[str, Any]:
    """Drop ``text.format`` when a gateway rejects json_schema.

    Some translated gateways (e.g. CLIProxyAPI) reject ``text.format =
    {type: json_schema, ...}`` outright, and their ``json_object`` mode
    additionally requires the literal word "json" to appear somewhere in the
    prompt (an OpenAI-era heuristic).  Codex prompts are JSON-instruction
    driven but do not always contain that literal, so switching to
    ``json_object`` still yields a 400.  The safest rewrite is to remove the
    ``text.format`` block entirely and forward everything else verbatim:
    the upstream then returns plain JSON-schema-free responses, and Codex's
    own prompt-level JSON contract keeps the reply parseable.
    """
    text = body.get("text")
    if not isinstance(text, dict):
        return body
    fmt = text.get("format")
    if not isinstance(fmt, dict):
        return body
    if fmt.get("type") != "json_schema":
        return body
    cloned_text = {key: value for key, value in text.items() if key != "format"}
    cloned = dict(body)
    cloned["text"] = cloned_text
    return cloned


def make_proxy_handler(upstream_base: str, api_key: str | None):
    upstream = upstream_base.rstrip("/")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "LightWorker-RewriteProxy"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _forward(self, method: str) -> None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            forwarded_body = body
            if body and self.headers.get("Content-Type", "").startswith("application/json"):
                try:
                    parsed = json.loads(body.decode("utf-8"))
                    if isinstance(parsed, dict):
                        rewritten = _rewrite_text_format(parsed)
                        if rewritten is not parsed:
                            forwarded_body = json.dumps(rewritten, ensure_ascii=False).encode("utf-8")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            url = upstream + self.path
            request = urllib.request.Request(url, data=forwarded_body, method=method)
            for name in ("Content-Type", "Accept", "Authorization", "X-Codex-Beta-Features", "Originator"):
                value = self.headers.get(name)
                if value:
                    request.add_header(name, value)
            if api_key and not self.headers.get("Authorization"):
                request.add_header("Authorization", f"Bearer {api_key}")
            try:
                with urllib.request.urlopen(request, timeout=900) as upstream_response:
                    payload = upstream_response.read()
                    self.send_response(upstream_response.status)
                    for name, value in upstream_response.headers.items():
                        if name.lower() in {"content-length", "transfer-encoding", "connection"}:
                            continue
                        self.send_header(name, value)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
            except Exception as exc:  # pragma: no cover - defensive proxy boundary
                error_payload = json.dumps(
                    {"error": {"message": f"Rewrite proxy upstream failure: {exc}", "type": "proxy_error"}}
                ).encode("utf-8")
                try:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(error_payload)))
                    self.end_headers()
                    self.wfile.write(error_payload)
                except OSError:
                    pass

        def do_GET(self) -> None:
            self._forward("GET")

        def do_POST(self) -> None:
            self._forward("POST")

    return Handler


def start_rewrite_proxy(
    upstream_base: str,
    api_key: str | None,
    host: str = "127.0.0.1",
    port: int = 8319,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Start the proxy on a loopback port and return (server, thread)."""
    server = ThreadingHTTPServer((host, port), make_proxy_handler(upstream_base, api_key))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True)
    thread.start()
    return server, thread


def pick_free_port(preferred: int = 8319) -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", preferred))
            return preferred
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]
