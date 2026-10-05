from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_meter.pricing import PriceBook
from codex_meter.report import build_report
from codex_meter.scanner import scan_codex


class ReportTests(unittest.TestCase):
    def test_new_models_and_ultrafast_flow_from_logs_to_report(self) -> None:
        lines = []
        for model, tier in (("gpt-6.1-sol", "default"), ("gpt-6-sol", "default"),
                            ("gpt-6-luna", "default"), ("gpt-6-astra", "ultrafast")):
            lines.append(json.dumps({"timestamp": "2026-10-05T00:00:00Z", "type": "turn_context",
                                     "payload": {"model": model, "service_tier": tier}}))
            lines.append(json.dumps({"timestamp": "2026-10-05T00:00:01Z", "type": "event_msg",
                "payload": {"type": "token_count", "rate_limits": {"plan_type": "pro"},
                            "info": {"last_token_usage": {"input_tokens": 100_000, "output_tokens": 10_000}}}}))
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / "sessions").mkdir()
            (home / "sessions" / "models.jsonl").write_text("\n".join(lines), encoding="utf-8")
            scan = scan_codex(home)
        report = build_report(scan, PriceBook.default(), plan_override="pro_500")
        self.assertEqual(report["summary"]["calls"], 4)
        self.assertAlmostEqual(report["summary"]["api_standard_equivalent_usd"], 2.115)
        self.assertAlmostEqual(report["summary"]["subscription_credits_estimate"], 240.375)
        self.assertEqual(report["summary"]["fast_calls"], 1)
        self.assertEqual(report["summary"]["api_price_coverage"], 1)
        self.assertEqual(report["summary"]["subscription_price_coverage"], 1)
        self.assertEqual(report["current"]["plan_reference"]["monthly_usd"], 500)

    def test_unpriced_api_tier_is_visible_despite_standard_equivalent_coverage(self) -> None:
        report = build_report({"events": [{"session_id": "session-test", "model": "gpt-6.1-sol",
            "timestamp": "2026-10-05T00:00:00Z", "service_tier": "ultrafast", "billing_mode": "api",
            "tokens": {"input_tokens": 100, "total_tokens": 100}}]}, PriceBook.default())
        self.assertEqual(report["summary"]["api_price_coverage"], 1)
        self.assertEqual(report["summary"]["api_estimated_charge_usd"], 0)
        self.assertEqual(report["summary"]["unpriced_api_charge_tokens"], 100)
        self.assertEqual(report["summary"]["unpriced_subscription_call_tokens"], 0)
        self.assertTrue(any("未计入费用合计" in note for note in report["caveats"]))

    def test_astra_log_to_report_uses_both_ledgers_without_counting_reasoning_twice(self) -> None:
        def row(kind: str, payload: dict) -> str:
            return json.dumps({"timestamp": "2026-09-22T00:00:00Z", "type": kind, "payload": payload})

        lines = [
            row("turn_context", {"model": "gpt-6-astra", "effort": "ultra"}),
            row("response_item", {"role": "user", "content": "PRIVATE_PROMPT_SENTINEL"}),
            row("event_msg", {
                "type": "token_count",
                "info": {"last_token_usage": {
                    "input_tokens": 100_000, "cached_input_tokens": 40_000,
                    "cache_write_input_tokens": 10_000, "output_tokens": 1_000,
                    "reasoning_output_tokens": 500, "total_tokens": 101_000,
                }},
                "rate_limits": {"plan_type": "plus", "primary": {
                    "used_percent": 12, "window_minutes": 300, "resets_at": 1_800_000_000,
                }},
            }),
        ]
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / "sessions").mkdir()
            (home / "sessions" / "astra.jsonl").write_text("\n".join(lines), encoding="utf-8")
            report = build_report(scan_codex(home), PriceBook.default())
        summary = report["summary"]
        self.assertEqual(summary["calls"], 1)
        self.assertEqual(summary["tokens"]["total_tokens"], 101_000)
        self.assertAlmostEqual(summary["api_standard_equivalent_usd"], 0.715)
        self.assertEqual(summary["api_estimated_charge_usd"], 0)
        self.assertGreater(summary["subscription_credits_estimate"], 0)
        self.assertEqual(summary["api_price_coverage"], 1)
        self.assertEqual(summary["subscription_price_coverage"], 1)
        self.assertEqual(report["unknown_pricing"], {"api": {}, "subscription": {}})
        self.assertNotIn("PRIVATE_PROMPT_SENTINEL", json.dumps(report))

    def test_report_separates_actual_modes_and_flags_unknowns(self) -> None:
        scan = {
            "files_discovered": 2,
            "latest_rate_limit": {
                "timestamp": "2026-08-22T00:00:00Z",
                "plan_type": "plus",
                "primary": {"used_percent": 20, "window_minutes": 300, "resets_at": 1_800_000_000},
                "secondary": None,
                "credits": {"balance": "0"},
            },
            "events": [
                {
                    "timestamp": "2026-08-22T00:00:00Z",
                    "model": "gpt-5.6-sol",
                    "service_tier": "default",
                    "plan_type": "plus",
                    "billing_mode": "subscription",
                    "session_id": "session-one",
                    "tokens": {
                        "input_tokens": 1_000_000,
                        "cached_input_tokens": 0,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 1_000_000,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 2_000_000,
                    },
                },
                {
                    "timestamp": "2026-08-22T01:00:00Z",
                    "model": "codex-auto-review",
                    "service_tier": "default",
                    "plan_type": "plus",
                    "billing_mode": "subscription",
                    "session_id": "session-two",
                    "tokens": {
                        "input_tokens": 100,
                        "cached_input_tokens": 0,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 10,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 110,
                    },
                },
            ],
            "plan_type_counts": {"plus": 2},
            "malformed_relevant_lines": 0,
            "failures": [],
            "privacy": {"network_used": False},
        }
        report = build_report(scan, PriceBook.default())
        self.assertAlmostEqual(report["summary"]["api_standard_equivalent_usd"], 38.0)
        self.assertAlmostEqual(report["summary"]["subscription_credits_estimate"], 600.0)
        self.assertEqual(report["summary"]["unpriced_api_tokens"], 110)
        self.assertEqual(report["current"]["rate_limit"]["primary"]["remaining_percent"], 80.0)
        self.assertEqual(report["current"]["plan_reference"]["monthly_usd"], 20.0)
        self.assertEqual(report["weekly_monitor"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
