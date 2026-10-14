from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from codex_meter.live import build_live_snapshot
from codex_meter.pricing import PriceBook
from codex_meter.scanner import CachedScanner, scan_session_file


NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


def event(at, output=120, reasoning=80, model="gpt-6.1-sol", session="one"):
    return {"timestamp": at, "model": model, "billing_mode": "subscription",
            "session_id": session, "tokens": {"input_tokens": 600, "output_tokens": output,
                                               "reasoning_output_tokens": reasoning}}


def row(kind, **payload):
    return json.dumps({"timestamp": "2026-10-14T11:59:40Z", "type": "event_msg",
                       "payload": {"type": kind, **payload}}) + "\n"


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.book = PriceBook.default()

    def test_rolling_window_uses_output_once_excludes_boundary_and_future(self):
        scan = {"events": [event("2026-10-14T11:59:00Z", 999),
                           event("2026-10-14T11:59:01Z"),
                           event("2026-10-14T12:00:00Z", session="two"),
                           event("2026-10-14T12:00:01Z", 999)]}
        result = build_live_snapshot(scan, self.book, now=NOW)
        self.assertEqual(result["speed"]["output_tokens_per_second"], 4)
        self.assertEqual(result["speed"]["input_tokens_per_second"], 20)
        self.assertEqual(result["speed"]["active_sessions"], 2)
        self.assertFalse(result["speed"]["streaming_measured"])
        self.assertAlmostEqual(result["recent_cost"]["api_standard_equivalent_usd"], .0048)
        self.assertEqual(result["latest_event_at"], "2026-10-14T12:00:00Z")

    def test_idle_speed_is_zero_but_absent_quota_is_unknown(self):
        result = build_live_snapshot({"events": [event("2026-10-14T11:00:00Z")]}, self.book, now=NOW)
        self.assertEqual(result["speed"]["output_tokens_per_second"], 0)
        self.assertIsNone(result["quota"]["primary"])
        self.assertTrue(result["quota"]["stale"])
        self.assertIsNone(result["last_turn"])

    def test_stale_and_expired_quota_do_not_reset_to_100(self):
        scan = {"latest_rate_limit": {"timestamp": "2026-10-14T11:50:00Z", "plan_type": "pro",
                    "primary": {"used_percent": 95, "window_minutes": 300, "resets_at": NOW.timestamp()-1},
                    "secondary": {"used_percent": None, "window_minutes": 10080}}}
        quota = build_live_snapshot(scan, self.book, now=NOW)["quota"]
        self.assertTrue(quota["stale"])
        self.assertTrue(quota["primary"]["expired"])
        self.assertEqual(quota["primary"]["remaining_percent"], 5)
        self.assertIsNone(quota["secondary"]["remaining_percent"])

    def test_nonfinite_quota_is_not_available_balance(self):
        scan = {"latest_rate_limit": {"timestamp": "2026-10-14T12:00:00Z",
                                      "primary": {"used_percent": float("nan")}}}
        quota = build_live_snapshot(scan, self.book, now=NOW)["quota"]
        self.assertIsNone(quota["primary"]["remaining_percent"])

    def test_completed_turn_average_uses_whole_duration_not_ttft_subtraction(self):
        scan = {"turns": [{"timestamp":"2026-10-14T11:59:40Z", "duration_ms":20000,
                            "time_to_first_token_ms":5000, "output_tokens":2000, "model":"gpt-6.1-sol"}]}
        result = build_live_snapshot(scan, self.book, now=NOW)["last_turn"]
        self.assertEqual(result["output_tokens_per_second"], 100)
        self.assertEqual(result["time_to_first_token_ms"], 5000)

    def test_unknown_prices_remain_unpriced(self):
        result = build_live_snapshot({"events": [event("2026-10-14T11:59:40Z", model="future-model")]}, self.book, now=NOW)
        self.assertEqual(result["recent_cost"]["unpriced_api_tokens"], 720)
        self.assertEqual(result["recent_cost"]["unpriced_subscription_tokens"], 720)


class TimingAndCacheTests(unittest.TestCase):
    def test_turn_metadata_excludes_content_ids_and_duplicate_tokens(self):
        counter = {"total_token_usage":{"input_tokens":100,"output_tokens":50},
                   "last_token_usage":{"input_tokens":100,"output_tokens":50}}
        lines = (row("task_started", turn_id="PRIVATE_ID")
                 + row("token_count", info=counter) + row("token_count", info=counter)
                 + row("task_complete", turn_id="PRIVATE_ID", duration_ms=2000,
                       time_to_first_token_ms=500, last_agent_message="SECRET RESPONSE"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"rollout.jsonl"
            path.write_text(lines, encoding="utf-8")
            result = scan_session_file(path)
        self.assertEqual(result["turns"][0]["output_tokens"], 50)
        self.assertNotIn("SECRET RESPONSE", json.dumps(result))
        self.assertNotIn("PRIVATE_ID", json.dumps(result))

    def test_incomplete_cumulative_history_does_not_inflate_turn_speed(self):
        lines = (row("task_started", turn_id="a")
                 + row("token_count", info={"total_token_usage":{"output_tokens":500},
                                             "last_token_usage":{"output_tokens":20}})
                 + row("task_complete", turn_id="a", duration_ms=1000))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"rollout.jsonl"
            path.write_text(lines, encoding="utf-8")
            result = scan_session_file(path)
        self.assertEqual(result["turns"], [])

    def test_cache_reuses_unchanged_files_and_handles_append_truncate_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home/"sessions").mkdir()
            path = home/"sessions"/"one.jsonl"
            one = row("token_count", info={"total_token_usage":{"output_tokens":10}})
            path.write_text(one, encoding="utf-8")
            cache = CachedScanner(home)
            with patch("codex_meter.scanner.scan_session_file", wraps=scan_session_file) as parse:
                self.assertEqual(cache.scan()["events"][0]["tokens"]["output_tokens"], 10)
                cache.scan()
                self.assertEqual(parse.call_count, 1)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(row("token_count", info={"total_token_usage":{"output_tokens":30}}))
                self.assertEqual(sum(e["tokens"]["output_tokens"] for e in cache.scan()["events"]), 30)
                path.write_text(one, encoding="utf-8")
                self.assertEqual(sum(e["tokens"]["output_tokens"] for e in cache.scan()["events"]), 10)
                path.unlink()
                self.assertEqual(cache.scan()["events"], [])

    def test_partial_record_is_retried_and_archive_is_not_double_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home/"sessions").mkdir()
            (home/"archived_sessions").mkdir()
            filename = "rollout-00000000-0000-0000-0000-000000000001.jsonl"
            path = home/"sessions"/filename
            data = row("token_count", info={"total_token_usage":{"output_tokens":50}})
            path.write_text(data[:40], encoding="utf-8")
            cache = CachedScanner(home)
            self.assertEqual(cache.scan()["events"], [])
            with path.open("a", encoding="utf-8") as handle:
                handle.write(data[40:])
            (home/"archived_sessions"/filename).write_text(data, encoding="utf-8")
            self.assertEqual(len(cache.scan()["events"]), 1)


if __name__ == "__main__":
    unittest.main()
