from __future__ import annotations

import unittest

from codex_meter.monitor import build_weekly_monitor, extract_weekly_points
from codex_meter.pricing import PriceBook


RESET_ONE = 1_786_000_000
RESET_TWO = RESET_ONE + 7 * 24 * 60 * 60


def snapshot(
    timestamp: str,
    used: float,
    reset: int = RESET_ONE,
    *,
    secondary: bool = False,
    plan_type: str = "plus",
    limit_name: str = "codex",
) -> dict:
    weekly = {"used_percent": used, "window_minutes": 10080, "resets_at": reset}
    return {
        "timestamp": timestamp,
        "plan_type": plan_type,
        "limit_name": limit_name,
        "primary": {"used_percent": 50, "window_minutes": 300, "resets_at": reset - 100}
        if secondary
        else weekly,
        "secondary": weekly if secondary else None,
    }


def event(
    timestamp: str,
    *,
    billing_mode: str = "subscription",
    model: str = "gpt-5.6-luna",
    input_tokens: int = 100_000,
    output_tokens: int = 100_000,
) -> dict:
    return {
        "timestamp": timestamp,
        "model": model,
        "service_tier": "default",
        "plan_type": "plus",
        "billing_mode": billing_mode,
        "session_id": "session-test",
        "tokens": {
            "input_tokens": input_tokens,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": 0,
            "total_tokens": input_tokens + output_tokens,
        },
    }


class WeeklyMonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.book = PriceBook.default()

    def test_correlates_percent_delta_with_token_dollars(self) -> None:
        result = build_weekly_monitor(
            [
                snapshot("2026-08-01T00:00:00Z", 10),
                snapshot("2026-08-01T01:00:00Z", 20),
            ],
            [event("2026-08-01T00:30:00Z")],
            self.book,
        )
        estimate = result["current_estimate"]
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["latest"]["remaining_percent"], 80)
        self.assertEqual(estimate["observed_percent_delta"], 10)
        self.assertEqual(estimate["observed_tokens"], 200_000)
        self.assertAlmostEqual(estimate["observed_api_equivalent_usd"], 0.14)
        self.assertAlmostEqual(estimate["weekly_api_equivalent_usd"], 1.4)
        self.assertAlmostEqual(estimate["weekly_subscription_credits"], 35.0)
        self.assertEqual(estimate["weekly_token_equivalent"], 2_000_000)
        self.assertAlmostEqual(estimate["estimated_remaining_api_equivalent_usd"], 1.12)
        self.assertAlmostEqual(estimate["weekly_api_equivalent_low_usd"], 1.2727272727)
        self.assertAlmostEqual(estimate["weekly_api_equivalent_high_usd"], 1.5555555556)

    def test_api_key_events_do_not_count_against_subscription_quota(self) -> None:
        result = build_weekly_monitor(
            [
                snapshot("2026-08-01T00:00:00Z", 10),
                snapshot("2026-08-01T01:00:00Z", 20),
            ],
            [
                event("2026-08-01T00:20:00Z"),
                event(
                    "2026-08-01T00:40:00Z",
                    billing_mode="api",
                    input_tokens=1_000_000,
                    output_tokens=1_000_000,
                ),
            ],
            self.book,
        )
        self.assertEqual(result["current_estimate"]["observed_calls"], 1)
        self.assertAlmostEqual(result["current_estimate"]["observed_api_equivalent_usd"], 0.14)

    def test_current_estimate_starts_after_quota_reset(self) -> None:
        result = build_weekly_monitor(
            [
                snapshot("2026-08-01T00:00:00Z", 90, RESET_ONE),
                snapshot("2026-08-01T01:00:00Z", 95, RESET_ONE),
                snapshot("2026-08-02T00:00:00Z", 5, RESET_TWO),
                snapshot("2026-08-02T01:00:00Z", 15, RESET_TWO),
            ],
            [
                event("2026-08-01T00:30:00Z"),
                event("2026-08-02T00:30:00Z"),
            ],
            self.book,
        )
        estimate = result["current_estimate"]
        self.assertEqual(estimate["from_used_percent"], 5)
        self.assertEqual(estimate["to_used_percent"], 15)
        self.assertEqual(estimate["observed_calls"], 1)
        self.assertEqual(len(result["history"]), 2)

    def test_secondary_weekly_window_and_small_sample_warning(self) -> None:
        points = extract_weekly_points(
            [
                snapshot("2026-08-01T00:00:00Z", 0, secondary=True),
                snapshot("2026-08-01T02:00:00Z", 1, secondary=True),
            ]
        )
        self.assertEqual(points[-1]["source_window"], "secondary")
        result = build_weekly_monitor(
            [
                snapshot("2026-08-01T00:00:00Z", 0, secondary=True),
                snapshot("2026-08-01T02:00:00Z", 1, secondary=True),
            ],
            [event("2026-08-01T01:00:00Z")],
            self.book,
        )
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(result["current_estimate"]["confidence"]["level"], "low")
        self.assertIsNone(result["current_estimate"]["weekly_api_equivalent_high_usd"])

    def test_calibration_never_mixes_different_plans(self) -> None:
        result = build_weekly_monitor(
            [
                snapshot("2026-08-01T00:00:00Z", 10, RESET_ONE, plan_type="pro"),
                snapshot("2026-08-01T01:00:00Z", 20, RESET_ONE, plan_type="pro"),
                snapshot("2026-08-02T00:00:00Z", 10, RESET_TWO, plan_type="plus"),
                snapshot("2026-08-02T01:00:00Z", 20, RESET_TWO, plan_type="plus"),
            ],
            [
                event("2026-08-01T00:30:00Z", model="gpt-5.6-sol"),
                event("2026-08-02T00:30:00Z", model="gpt-5.6-luna"),
            ],
            self.book,
        )
        calibrated = result["calibrated_estimate"]
        self.assertEqual(calibrated["sample_count"], 1)
        self.assertAlmostEqual(calibrated["weekly_api_equivalent_usd"], 1.4)

    def test_no_weekly_snapshot_is_unavailable(self) -> None:
        result = build_weekly_monitor(
            [
                {
                    "timestamp": "2026-08-01T00:00:00Z",
                    "primary": {"used_percent": 10, "window_minutes": 300},
                }
            ],
            [],
            self.book,
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["current_estimate"])


if __name__ == "__main__":
    unittest.main()
