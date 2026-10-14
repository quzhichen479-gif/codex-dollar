"""Native desktop shell for the loopback-only dashboard.

Release builds include pywebview.  Source checkouts without the optional
desktop dependency fall back to the user's default browser while preserving
the same local-only server and security boundaries.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from .web import create_dashboard_server, serve_dashboard


class DesktopBridge:
    """Only window controls are exposed to the local webview."""

    def __init__(self, webview: Any, url: str):
        self._webview = webview
        self._url = url
        self._dashboard: Any = None
        self._widget: Any = None
        self._lock = threading.RLock()

    def show_dashboard(self) -> None:
        with self._lock:
            if self._dashboard is None:
                window = self._webview.create_window(
                    "Codex Dollar", self._url, width=1320, height=880,
                    min_size=(940, 640), background_color="#0b0d0d",
                    text_select=True, js_api=self,
                )
                self._dashboard = window
                window.events.closed += self._dashboard_closed
            else:
                self._dashboard.show()
                self._dashboard.restore()

    def _dashboard_closed(self) -> None:
        self._dashboard = None

    def open_widget(self) -> None:
        with self._lock:
            if self._widget is None:
                window = self._webview.create_window(
                    "Codex Dollar · 悬窗", self._url + "widget",
                    width=380, height=550, min_size=(320, 540),
                    on_top=True, background_color="#0b0d0d",
                    text_select=False, js_api=self,
                )
                self._widget = window
                window.events.closed += self._widget_closed
            else:
                self._widget.show()
                self._widget.restore()

    def _widget_closed(self) -> None:
        self._widget = None

    def toggle_pin(self) -> bool:
        with self._lock:
            if self._widget is None:
                return False
            self._widget.on_top = not self._widget.on_top
            return bool(self._widget.on_top)


def run_app(
    builder: Callable[[], dict[str, Any]],
    *,
    port: int = 0,
    live_builder: Callable[[], dict[str, Any]] | None = None,
    widget: bool = False,
) -> None:
    try:
        import webview  # type: ignore[import-not-found]
    except ImportError:
        print("未安装可选桌面壳 pywebview，已切换为本地浏览器 App 模式。")
        print("若要原生窗口：pip install -e \".[desktop]\"")
        serve_dashboard(builder, port=port, open_browser=True, live_builder=live_builder,
                        start_path="/widget" if widget else "/")
        return

    server = create_dashboard_server(builder, port=port, live_builder=live_builder)
    url = f"http://127.0.0.1:{server.server_port}/"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.35}, daemon=True)
    thread.start()
    try:
        bridge = DesktopBridge(webview, url)
        if widget:
            bridge.open_widget()
        else:
            bridge.show_dashboard()
        webview.start(private_mode=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
