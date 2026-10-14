import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from codex_meter.cli import build_parser
from codex_meter.desktop import DesktopBridge, run_app


class Event:
    def __iadd__(self, callback):
        self.callback = callback
        return self


class DesktopTests(unittest.TestCase):
    def test_widget_singleton_pin_close_reopen_and_dashboard(self):
        windows = []
        def create(title, url, **kwargs):
            window = SimpleNamespace(on_top=kwargs.get("on_top", False),
                show=Mock(), restore=Mock(), events=SimpleNamespace(closed=Event()))
            windows.append((window, url, kwargs))
            return window
        bridge = DesktopBridge(SimpleNamespace(create_window=create), "http://127.0.0.1:8765/")
        bridge.open_widget()
        self.assertTrue(windows[0][2]["on_top"])
        self.assertEqual(windows[0][1], "http://127.0.0.1:8765/widget")
        bridge.open_widget()
        self.assertEqual(len(windows), 1)
        self.assertFalse(bridge.toggle_pin())
        self.assertTrue(bridge.toggle_pin())
        windows[0][0].events.closed.callback()
        bridge.open_widget()
        self.assertEqual(len(windows), 2)
        bridge.show_dashboard()
        bridge.show_dashboard()
        self.assertEqual(len(windows), 3)
        windows[2][0].events.closed.callback()
        bridge.show_dashboard()
        self.assertEqual(len(windows), 4)

    def test_widget_command_and_browser_fallback(self):
        self.assertTrue(build_parser().parse_args(["app", "--widget"]).widget)
        builder, live = Mock(), Mock()
        with patch.dict("sys.modules", {"webview":None}), patch("codex_meter.desktop.serve_dashboard") as serve:
            run_app(builder, live_builder=live, widget=True)
        serve.assert_called_once_with(builder, port=0, open_browser=True, live_builder=live, start_path="/widget")


if __name__ == "__main__":
    unittest.main()
