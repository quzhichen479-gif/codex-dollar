from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from codex_meter.pricing import PriceBook
from codex_meter.report import build_report
from codex_meter.web import ReportState, create_dashboard_server, render_standalone
from codex_meter.live import build_live_snapshot


class WebTests(unittest.TestCase):
    def test_live_snapshot_is_small_cached_and_served_with_widget(self) -> None:
        report = build_report({"events":[]}, PriceBook.default())
        calls = []
        def live():
            calls.append(1)
            return build_live_snapshot({"events":[]}, PriceBook.default())
        server = create_dashboard_server(lambda:report, live_builder=live, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            for _ in range(2):
                with urlopen(base + "/api/live", timeout=5) as response:
                    data = json.load(response)
                    self.assertFalse(data["speed"]["streaming_measured"])
                    self.assertNotIn("sessions", data)
            self.assertEqual(len(calls), 1)
            for path, kind in (("/widget", "text/html"), ("/assets/widget.js", "text/javascript"), ("/assets/widget.css", "text/css")):
                with urlopen(base + path, timeout=5) as response:
                    self.assertIn(kind, response.headers["Content-Type"])
                    self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            with self.assertRaises(HTTPError):
                urlopen(base + "/assets/../../scanner.py", timeout=5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_standalone_inlines_app_after_document_and_escapes_report(self) -> None:
        report = build_report({"events": []}, PriceBook.default())
        report["caveats"].append('</script><script>alert("unsafe")</script>')
        html = render_standalone(report)
        self.assertNotIn('src="/assets/', html)
        self.assertNotIn('href="/assets/', html)
        self.assertNotIn('</script><script>alert("unsafe")</script>', html)
        self.assertIn('<\\/script>', html)
        self.assertLess(html.index("</main>"), html.index("async function load("))
        self.assertLess(html.index("async function load("), html.index("</body>"))
        self.assertNotIn("CODEX_BENCHMARKS", html)
        self.assertNotIn('id="benchmarks"', html)
        self.assertIn("gpt-6.1-sol", html)

    def test_loopback_serves_dashboard_and_removes_question_bank(self) -> None:
        report = build_report({"events": []}, PriceBook.default())
        report["caveats"].append("PRIVATE_REPORT_SENTINEL")
        server = create_dashboard_server(lambda: report, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/assets/app.js", timeout=5) as response:
                text = response.read().decode("utf-8")
                self.assertIn("javascript", response.headers["Content-Type"])
                self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
                self.assertIn("connect-src 'self'", response.headers["Content-Security-Policy"])
                self.assertNotIn("CODEX_BENCHMARKS", text)
                self.assertNotIn("PRIVATE_REPORT_SENTINEL", text)
            with urlopen(base + "/api/report", timeout=5) as response:
                self.assertEqual(json.load(response)["summary"]["calls"], 0)
            for path in ("/assets/../web.py", "/assets/benchmarks.js"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path, timeout=5)
                self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
