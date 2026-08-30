from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_meter.scanner import classify_billing, scan_session_file


def row(timestamp: str, kind: str, payload: dict) -> str:
    return json.dumps({"timestamp": timestamp, "type": kind, "payload": payload})


class ScannerTests(unittest.TestCase):
    def test_cumulative_events_are_not_double_counted(self) -> None:
        lines = [
            row(
                "2026-08-21T00:00:00Z",
                "event_msg",
                {
                    "type": "thread_settings_applied",
                    "thread_settings": {"model": "gpt-5.6-sol", "service_tier": "priority"},
                },
            ),
            row("2026-08-21T00:00:01Z", "response_item", {"role": "user", "content": "SECRET PROMPT"}),
            row(
                "2026-08-21T00:00:02Z",
                "event_msg",
                {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                        "last_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                    },
                    "rate_limits": {
                        "plan_type": "plus",
                        "primary": {"used_percent": 25, "window_minutes": 300, "resets_at": 1_800_000_000},
                        "credits": {"balance": "4", "has_credits": True, "unlimited": False},
                        "secret_extra": "must not leave scanner",
                    },
                },
            ),
            # Duplicate cumulative snapshot: must not add the previous call again.
            row(
                "2026-08-21T00:00:03Z",
                "event_msg",
                {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                        "last_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                    },
                },
            ),
            row(
                "2026-08-21T00:00:04Z",
                "event_msg",
                {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {"input_tokens": 150, "output_tokens": 30, "total_tokens": 180},
                        "last_token_usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
                    },
                },
            ),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rollout-2026-08-21T00-00-00-00000000-0000-0000-0000-000000000001.jsonl"
            path.write_text("\n".join(lines), encoding="utf-8")
            result = scan_session_file(path)

        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(sum(e["tokens"]["input_tokens"] for e in result["events"]), 150)
        self.assertEqual(sum(e["tokens"]["output_tokens"] for e in result["events"]), 30)
        self.assertEqual(result["events"][0]["model"], "gpt-5.6-sol")
        self.assertEqual(result["events"][0]["service_tier"], "priority")
        self.assertEqual(result["events"][0]["billing_mode"], "subscription")
        self.assertEqual(len(result["rate_snapshots"]), 1)
        self.assertEqual(result["rate_snapshots"][0]["primary"]["used_percent"], 25)
        serialized = json.dumps(result)
        self.assertNotIn("SECRET PROMPT", serialized)
        self.assertNotIn("secret_extra", serialized)
        self.assertTrue(result["id"].startswith("session-"))

    def test_billing_classification_is_conservative(self) -> None:
        self.assertEqual(classify_billing("plus"), "subscription")
        self.assertEqual(classify_billing("api"), "api")
        self.assertEqual(classify_billing(None), "unknown")
        self.assertEqual(classify_billing("mystery"), "unknown")
        self.assertEqual(classify_billing("mystery", "api"), "api")


if __name__ == "__main__":
    unittest.main()
