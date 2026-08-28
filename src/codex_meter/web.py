"""Dependency-free local dashboard and standalone HTML renderer."""

from __future__ import annotations

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _json_for_script(report: dict[str, Any]) -> str:
    return (
        json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_standalone(report: dict[str, Any]) -> str:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="/assets/styles.css">',
        f"<style>\n{css}\n</style>",
    )
    html = html.replace(
        "<!--CODEX_METER_DATA-->",
        f"<script>window.__CODEX_METER_REPORT__={_json_for_script(report)};</script>",
    )
    html = html.replace(
        '<script src="/assets/app.js" defer></script>',
        f"<script>\n{js}\n</script>",
    )
    return html


class ReportState:
    def __init__(self, builder: Callable[[], dict[str, Any]]):
        self._builder = builder
        self._lock = threading.Lock()
        self._report = builder()

    def get(self, refresh: bool = False) -> dict[str, Any]:
        if refresh:
            with self._lock:
                self._report = self._builder()
        return self._report


def _handler_factory(state: ReportState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "CodexTokenMeter/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _headers(self, content_type: str, length: int, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'",
            )
            self.end_headers()

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self._headers(content_type, len(body), status)
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                body = (STATIC_DIR / "index.html").read_bytes()
                self._send(body, "text/html; charset=utf-8")
                return
            if parsed.path == "/assets/styles.css":
                self._send((STATIC_DIR / "styles.css").read_bytes(), "text/css; charset=utf-8")
                return
            if parsed.path == "/assets/app.js":
                self._send((STATIC_DIR / "app.js").read_bytes(), "text/javascript; charset=utf-8")
                return
            if parsed.path == "/api/report":
                query = parse_qs(parsed.query)
                try:
                    report = state.get(refresh=query.get("refresh") == ["1"])
                    body = json.dumps(report, ensure_ascii=False).encode("utf-8")
                    self._send(body, "application/json; charset=utf-8")
                except Exception as exc:  # keep dashboard alive without leaking paths/content
                    body = json.dumps(
                        {"error": "refresh_failed", "detail": type(exc).__name__},
                        ensure_ascii=False,
                    ).encode("utf-8")
                    self._send(body, "application/json; charset=utf-8", HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send(b"Not found", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)

    return Handler


def create_dashboard_server(
    builder: Callable[[], dict[str, Any]], *, port: int = 8765
) -> ThreadingHTTPServer:
    state = ReportState(builder)
    return ThreadingHTTPServer(("127.0.0.1", int(port)), _handler_factory(state))


def serve_dashboard(
    builder: Callable[[], dict[str, Any]],
    *,
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    server = create_dashboard_server(builder, port=port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Codex Token Meter: {url}")
    print("仅监听本机回环地址；按 Ctrl+C 停止。")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
