from __future__ import annotations

import copy
import unittest

from codex_meter.pricing import PriceBook, split_input_tokens


class PriceBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.book = PriceBook.default()

    def test_input_buckets_are_mutually_exclusive(self) -> None:
        split = split_input_tokens(
            {
                "input_tokens": 1_000,
                "cached_input_tokens": 700,
                "cache_write_input_tokens": 100,
                "output_tokens": 50,
                "reasoning_output_tokens": 20,
            }
        )
        self.assertEqual(split["input"], 200)
        self.assertEqual(split["cached_input"], 700)
        self.assertEqual(split["cache_write"], 100)
        self.assertEqual(split["total"], 1_050)

    def test_astra_launch_date_applies_to_both_ledgers(self) -> None:
        tokens = {"input_tokens": 100_000, "output_tokens": 10_000}
        for estimator, expected in (
            (self.book.estimate_api, 1.5),
            (self.book.estimate_subscription_credits, 37.5),
        ):
            with self.subTest(estimator=estimator.__name__):
                before = estimator(
                    model="gpt-6-astra", timestamp="2026-09-02T23:59:59Z", tokens=tokens
                )
                at_launch = estimator(
                    model="gpt-6-astra", timestamp="2026-09-02T20:00:00-04:00", tokens=tokens
                )
                self.assertFalse(before.priced)
                self.assertTrue(at_launch.priced)
                self.assertAlmostEqual(at_launch.value, expected)

    def test_astra_api_cache_buckets_and_service_tiers(self) -> None:
        tokens = {
            "input_tokens": 100_000,
            "cached_input_tokens": 60_000,
            "cache_write_input_tokens": 20_000,
            "output_tokens": 10_000,
            "reasoning_output_tokens": 5_000,
        }
        for tier, multiplier in (
            ("standard", 1), ("fast", 2), ("priority", 2), ("batch", 0.5), ("flex", 0.5)
        ):
            with self.subTest(tier=tier):
                estimate = self.book.estimate_api(
                    model="gpt-6-astra", timestamp="2026-09-22T00:00:00Z",
                    tokens=tokens, service_tier=tier,
                )
                self.assertTrue(estimate.priced)
                self.assertEqual(estimate.context_band, "short")
                self.assertAlmostEqual(estimate.components["input"], 0.2 * multiplier)
                self.assertAlmostEqual(estimate.components["cached_input"], 0.06 * multiplier)
                self.assertAlmostEqual(estimate.components["cache_write"], 0.25 * multiplier)
                self.assertAlmostEqual(estimate.components["output"], 0.5 * multiplier)
                self.assertAlmostEqual(estimate.value, 1.01 * multiplier)

    def test_astra_long_context_threshold_includes_cached_input(self) -> None:
        for input_count, expected_band, expected_value in (
            (272_000, "short", 5.272), (272_001, "long", 8.044002)
        ):
            with self.subTest(input_tokens=input_count):
                estimate = self.book.estimate_api(
                    model="gpt-6-astra", timestamp="2026-09-22T00:00:00Z",
                    tokens={
                        "input_tokens": input_count,
                        "cached_input_tokens": input_count,
                        "output_tokens": 100_000,
                    },
                )
                self.assertEqual(estimate.context_band, expected_band)
                self.assertAlmostEqual(estimate.value, expected_value)

    def test_astra_long_context_multiplies_all_input_buckets(self) -> None:
        estimate = self.book.estimate_api(
            model="gpt-6-astra", timestamp="2026-09-22T00:00:00Z",
            tokens={
                "input_tokens": 300_000,
                "cached_input_tokens": 100_000,
                "cache_write_input_tokens": 100_000,
                "output_tokens": 10_000,
            },
        )
        self.assertEqual(estimate.context_band, "long")
        self.assertAlmostEqual(estimate.components["input"], 2.0)
        self.assertAlmostEqual(estimate.components["cached_input"], 0.2)
        self.assertAlmostEqual(estimate.components["cache_write"], 2.5)
        self.assertAlmostEqual(estimate.components["output"], 0.75)
        self.assertAlmostEqual(estimate.value, 5.45)

    def test_astra_subscription_does_not_inherit_api_rules(self) -> None:
        tokens = {
            "input_tokens": 300_000,
            "cached_input_tokens": 100_000,
            "cache_write_input_tokens": 100_000,
            "output_tokens": 10_000,
        }
        for tier, multiplier in (("default", 1), ("fast", 2.5), ("priority", 2.5)):
            with self.subTest(tier=tier):
                estimate = self.book.estimate_subscription_credits(
                    model="gpt-6-astra", timestamp="2026-09-22T00:00:00Z",
                    tokens=tokens, service_tier=tier,
                )
                self.assertTrue(estimate.priced)
                self.assertEqual(estimate.unit, "credits")
                # Cache writes use ordinary input credits, and the API's long
                # context and Fast multipliers must not enter this estimate.
                self.assertAlmostEqual(estimate.components["input"], 50.0 * multiplier)
                self.assertAlmostEqual(estimate.components["cached_input"], 2.5 * multiplier)
                self.assertAlmostEqual(estimate.components["output"], 12.5 * multiplier)
                self.assertAlmostEqual(estimate.value, 65.0 * multiplier)

    def test_astra_like_unverified_model_ids_remain_unpriced(self) -> None:
        for model in ("gpt-6", "gpt-6-astra-preview", "astra"):
            for estimator in (self.book.estimate_api, self.book.estimate_subscription_credits):
                with self.subTest(model=model, estimator=estimator.__name__):
                    estimate = estimator(
                        model=model, timestamp="2026-09-22T00:00:00Z",
                        tokens={"input_tokens": 100_000, "output_tokens": 10_000},
                    )
                    self.assertFalse(estimate.priced)

    def test_sol_api_cut_uses_event_date(self) -> None:
        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        before = self.book.estimate_api(
            model="gpt-5.6-sol", timestamp="2026-08-20T23:59:59Z", tokens=usage
        )
        after = self.book.estimate_api(
            model="gpt-5.6-sol", timestamp="2026-08-21T00:00:00Z", tokens=usage
        )
        # One million input tokens crosses the official 272k long-context
        # threshold: input rates are 2x and output rates are 1.5x.
        self.assertEqual(before.context_band, "long")
        self.assertAlmostEqual(before.value, 55.0)
        self.assertAlmostEqual(after.value, 38.0)

    def test_terra_and_luna_api_cuts_use_july_30(self) -> None:
        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        terra_before = self.book.estimate_api(
            model="gpt-5.6-terra", timestamp="2026-07-29T12:00:00Z", tokens=usage
        )
        terra_after = self.book.estimate_api(
            model="gpt-5.6-terra", timestamp="2026-07-30T12:00:00Z", tokens=usage
        )
        luna_before = self.book.estimate_api(
            model="gpt-5.6-luna", timestamp="2026-07-29T12:00:00Z", tokens=usage
        )
        luna_after = self.book.estimate_api(
            model="gpt-5.6-luna", timestamp="2026-07-30T12:00:00Z", tokens=usage
        )
        self.assertAlmostEqual(terra_before.value, 27.5)
        self.assertAlmostEqual(terra_after.value, 22.0)
        self.assertAlmostEqual(luna_before.value, 11.0)
        self.assertAlmostEqual(luna_after.value, 2.2)

    def test_api_cache_write_and_cached_input(self) -> None:
        estimate = self.book.estimate_api(
            model="gpt-5.6-sol",
            timestamp="2026-08-22T00:00:00Z",
            tokens={
                "input_tokens": 1_000_000,
                "cached_input_tokens": 800_000,
                "cache_write_input_tokens": 100_000,
                "output_tokens": 100_000,
            },
        )
        self.assertEqual(estimate.context_band, "long")
        self.assertAlmostEqual(estimate.value, 5.44)
        self.assertAlmostEqual(estimate.components["cache_write"], 1.0)

    def test_long_context_and_fast_tier(self) -> None:
        tokens = {"input_tokens": 300_000, "output_tokens": 100_000}
        standard = self.book.estimate_api(
            model="gpt-5.6-terra",
            timestamp="2026-08-01T00:00:00Z",
            tokens=tokens,
        )
        fast = self.book.estimate_api(
            model="gpt-5.6-terra",
            timestamp="2026-08-01T00:00:00Z",
            tokens=tokens,
            service_tier="priority",
        )
        self.assertEqual(standard.context_band, "long")
        self.assertAlmostEqual(standard.value, 3.0)
        self.assertAlmostEqual(fast.value, 6.0)

    def test_subscription_ledger_does_not_inherit_api_cut(self) -> None:
        tokens = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        before = self.book.estimate_subscription_credits(
            model="gpt-5.6-sol", timestamp="2026-08-20T23:59:59Z", tokens=tokens
        )
        after = self.book.estimate_subscription_credits(
            model="gpt-5.6-sol", timestamp="2026-08-21T00:00:00Z", tokens=tokens
        )
        fast = self.book.estimate_subscription_credits(
            model="gpt-5.6-sol",
            timestamp="2026-08-21T00:00:00Z",
            tokens=tokens,
            service_tier="priority",
        )
        self.assertAlmostEqual(before.value, 600.0)
        self.assertAlmostEqual(after.value, 600.0)
        self.assertAlmostEqual(fast.value, 1500.0)

    def test_unknown_model_is_never_guessed(self) -> None:
        estimate = self.book.estimate_api(
            model="codex-auto-review",
            timestamp="2026-08-21T00:00:00Z",
            tokens={"input_tokens": 10_000, "output_tokens": 1_000},
        )
        self.assertFalse(estimate.priced)
        self.assertEqual(estimate.value, 0)

    def test_non_official_source_is_rejected(self) -> None:
        api = copy.deepcopy(self.book.api)
        api["sources"].append({"label": "unsafe", "url": "https://sub2api.example/prices"})
        with self.assertRaises(ValueError):
            PriceBook(api, copy.deepcopy(self.book.subscription))

    def test_forbidden_source_text_outside_policy_is_rejected(self) -> None:
        api = copy.deepcopy(self.book.api)
        api["models"]["gpt-5.6-sol"][0]["note"] += " sub2api"
        with self.assertRaises(ValueError):
            PriceBook(api, copy.deepcopy(self.book.subscription))


if __name__ == "__main__":
    unittest.main()
