"""Native desktop shell for the loopback-only dashboard.

Release builds include pywebview.  Source checkouts without the optional
desktop dependency fall back to the user's default browser while preserving
the same local-only server and security boundaries.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from .web import create_dashboard_server, serve_dashboard


def run_app(
    builder: Callable[[], dict[str, Any]],
    *,
    port: int = 0,
) -> None:
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError:
        print("未安装可选桌面壳 pywebview，已切换为本地浏览器 App 模式。")
        print("若要原生窗口：pip install -e \".[desktop]\"")
        serve_dashboard(builder, port=port, open_browser=True)
        return

    server = create_dashboard_server(builder, port=port)
    url = f"http://127.0.0.1:{server.server_port}/"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.35}, daemon=True)
    thread.start()
    try:
        webview.create_window(
            "Codex Dollar",
            url,
            width=1320,
            height=880,
            min_size=(940, 640),
            background_color="#0b0d0d",
            text_select=True,
        )
        webview.start(private_mode=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
