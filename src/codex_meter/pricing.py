"""Pricing ledgers and estimators.

API dollars and ChatGPT/Codex subscription credits intentionally live in
different files and use different calculation paths.  This is a product
boundary, not just a presentation choice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def parse_datetime(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif not value:
        parsed = datetime.now(timezone.utc)
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def split_input_tokens(tokens: Mapping[str, Any]) -> dict[str, int]:
    """Split the inclusive input total into mutually exclusive buckets.

    Codex's token_count event follows the Usage API convention: input_tokens
    includes cached and cache-write tokens.  Clamping protects the estimate
    from malformed or older log records.
    """

    input_total = _as_nonnegative_int(tokens.get("input_tokens"))
    cached = min(input_total, _as_nonnegative_int(tokens.get("cached_input_tokens")))
    remaining = input_total - cached
    cache_write = min(
        remaining, _as_nonnegative_int(tokens.get("cache_write_input_tokens"))
    )
    uncached = max(0, remaining - cache_write)
    output = _as_nonnegative_int(tokens.get("output_tokens"))
    reasoning = min(output, _as_nonnegative_int(tokens.get("reasoning_output_tokens")))
    return {
        "input": uncached,
        "cached_input": cached,
        "cache_write": cache_write,
        "output": output,
        "reasoning_output": reasoning,
        "input_total": input_total,
        "total": input_total + output,
    }


@dataclass(frozen=True)
class Estimate:
    priced: bool
    value: float
    unit: str
    model: str
    canonical_model: str | None
    components: dict[str, float]
    rate: dict[str, float] | None
    effective_from: str | None
    context_band: str
    service_tier: str
    multiplier: float
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "priced": self.priced,
            "value": self.value,
            "unit": self.unit,
            "model": self.model,
            "canonical_model": self.canonical_model,
            "components": self.components,
            "rate": self.rate,
            "effective_from": self.effective_from,
            "context_band": self.context_band,
            "service_tier": self.service_tier,
            "multiplier": self.multiplier,
            "reason": self.reason,
        }


class PriceBook:
    def __init__(self, api_table: dict[str, Any], subscription_table: dict[str, Any]):
        self.api = api_table
        self.subscription = subscription_table
        self.validate()

    @classmethod
    def default(cls) -> "PriceBook":
        data_dir = Path(__file__).resolve().parent / "data"
        with (data_dir / "api_prices.json").open(encoding="utf-8") as handle:
            api = json.load(handle)
        with (data_dir / "subscription_credits.json").open(encoding="utf-8") as handle:
            subscription = json.load(handle)
        return cls(api, subscription)

    @staticmethod
    def _canonical(table: Mapping[str, Any], model: str) -> str:
        aliases = table.get("aliases", {})
        seen: set[str] = set()
        current = str(model or "unknown").strip().lower()
        while current in aliases and current not in seen:
            seen.add(current)
            current = str(aliases[current]).strip().lower()
        return current

    @staticmethod
    def _period_for(periods: list[dict[str, Any]], when: datetime) -> dict[str, Any] | None:
        selected = None
        for period in periods:
            start = parse_datetime(period.get("effective_from"))
            end_value = period.get("effective_to")
            end = parse_datetime(end_value) if end_value else None
            if start <= when and (end is None or when < end):
                selected = period
        return selected

    def estimate_api(
        self,
        *,
        model: str,
        timestamp: str | datetime,
        tokens: Mapping[str, Any],
        service_tier: str = "standard",
    ) -> Estimate:
        when = parse_datetime(timestamp)
        canonical = self._canonical(self.api, model)
        periods = self.api.get("models", {}).get(canonical)
        if not periods:
            return self._unpriced(model, canonical, "USD", service_tier, "No official API rate in the bundled ledger.")
        period = self._period_for(periods, when)
        if period is None:
            return self._unpriced(
                model,
                canonical,
                "USD",
                service_tier,
                "The usage timestamp is outside the official API price periods in the ledger.",
            )

        split = split_input_tokens(tokens)
        rates = {key: float(value) for key, value in period["rates"].items()}
        rules = self.api["rules"]
        is_long = bool(period.get("long_context_pricing")) and split["input_total"] > int(
            rules["long_context_threshold_input_tokens"]
        )
        if is_long:
            input_multiplier = float(rules["long_context_input_multiplier"])
            output_multiplier = float(rules["long_context_output_multiplier"])
            for key in ("input", "cached_input", "cache_write"):
                rates[key] *= input_multiplier
            rates["output"] *= output_multiplier

        normalized_tier = str(service_tier or "default").strip().lower()
        if "service_tiers" in period and normalized_tier not in period["service_tiers"]:
            return self._unpriced(
                model, canonical, "USD", normalized_tier,
                "This processing tier has no verified official rate for this model.",
            )
        tier_multipliers = rules["service_tier_multipliers"]
        special_tier = rules.get("model_service_tiers", {}).get(canonical, {}).get(normalized_tier)
        if special_tier and when >= parse_datetime(special_tier["effective_from"]):
            multiplier = float(special_tier["multiplier"])
        elif normalized_tier == "auto":
            multiplier = 1.0
        elif normalized_tier in tier_multipliers:
            multiplier = float(tier_multipliers[normalized_tier])
        else:
            return self._unpriced(
                model, canonical, "USD", normalized_tier,
                "No official API rate for this model, service tier and usage date.",
            )
        unit = float(self.api["unit_tokens"])
        components = {
            "input": split["input"] * rates["input"] / unit * multiplier,
            "cached_input": split["cached_input"] * rates["cached_input"] / unit * multiplier,
            "cache_write": split["cache_write"] * rates["cache_write"] / unit * multiplier,
            "output": split["output"] * rates["output"] / unit * multiplier,
        }
        return Estimate(
            priced=True,
            value=sum(components.values()),
            unit="USD",
            model=model,
            canonical_model=canonical,
            components=components,
            rate=rates,
            effective_from=period.get("effective_from"),
            context_band="long" if is_long else "short",
            service_tier=normalized_tier,
            multiplier=multiplier,
        )

    def estimate_subscription_credits(
        self,
        *,
        model: str,
        timestamp: str | datetime,
        tokens: Mapping[str, Any],
        service_tier: str = "default",
    ) -> Estimate:
        when = parse_datetime(timestamp)
        canonical = self._canonical(self.subscription, model)
        record = self.subscription.get("models", {}).get(canonical)
        if not record:
            return self._unpriced(
                model,
                canonical,
                "credits",
                service_tier,
                "No official Codex subscription-credit rate in the bundled ledger.",
            )
        if when < parse_datetime(record.get("effective_from")):
            return self._unpriced(
                model,
                canonical,
                "credits",
                service_tier,
                "The usage timestamp predates this model's subscription-credit record.",
            )

        split = split_input_tokens(tokens)
        rates = {key: float(value) for key, value in record["credits"].items()}
        normalized_tier = str(service_tier or "default").strip().lower()
        special_tier = self.subscription.get("model_service_tiers", {}).get(canonical, {}).get(normalized_tier)
        if special_tier and when >= parse_datetime(special_tier["effective_from"]):
            multiplier = float(special_tier["multiplier"])
        elif normalized_tier in {"default", "standard", "auto"}:
            multiplier = 1.0
        elif normalized_tier in {"priority", "fast"} and canonical in self.subscription.get("fast_multipliers", {}):
            # Purchased-credit billing is separate from included-limit usage.
            multiplier = float(self.subscription["fast_multipliers"][canonical])
        else:
            return self._unpriced(
                model, canonical, "credits", normalized_tier,
                "No official paid-credit rate for this model, service tier and usage date.",
            )
        unit = float(self.subscription["unit_tokens"])

        # The official credit card has no cache-write column.  Keep this rule
        # local to the subscription estimator so API's 1.25x rule cannot leak in.
        components = {
            "input": (split["input"] + split["cache_write"]) * rates["input"] / unit * multiplier,
            "cached_input": split["cached_input"] * rates["cached_input"] / unit * multiplier,
            "output": split["output"] * rates["output"] / unit * multiplier,
        }
        return Estimate(
            priced=True,
            value=sum(components.values()),
            unit="credits",
            model=model,
            canonical_model=canonical,
            components=components,
            rate=rates,
            effective_from=record.get("effective_from"),
            context_band="subscription-card",
            service_tier=normalized_tier,
            multiplier=multiplier,
        )

    @staticmethod
    def _unpriced(
        model: str,
        canonical: str | None,
        unit: str,
        service_tier: str,
        reason: str,
    ) -> Estimate:
        return Estimate(
            priced=False,
            value=0.0,
            unit=unit,
            model=model,
            canonical_model=canonical,
            components={},
            rate=None,
            effective_from=None,
            context_band="unknown",
            service_tier=str(service_tier or "default"),
            multiplier=1.0,
            reason=reason,
        )

    def plan_reference(self, detected_plan_type: str | None, override: str | None = None) -> dict[str, Any] | None:
        plan_key = override
        confidence = "user-override" if override else None
        if not plan_key and detected_plan_type:
            hint = self.subscription.get("detected_plan_hints", {}).get(str(detected_plan_type).lower())
            if hint:
                plan_key = hint.get("plan")
                confidence = hint.get("confidence")
        if not plan_key:
            return None
        record = self.subscription.get("plans", {}).get(plan_key)
        if not record:
            return None
        return {"key": plan_key, "confidence": confidence, **record}

    def validate(self) -> None:
        errors: list[str] = []
        if self.api.get("table_kind") != "api":
            errors.append("api_prices.json must declare table_kind=api")
        if self.subscription.get("table_kind") != "subscription":
            errors.append("subscription_credits.json must declare table_kind=subscription")
        if "independent" not in str(self.subscription.get("separation_policy", "")).lower():
            errors.append("subscription table must explicitly declare its independent-ledger policy")

        for table_name, table in (("api", self.api), ("subscription", self.subscription)):
            allowed = set(table.get("source_policy", {}).get("allowed_hosts", []))
            checked_content = dict(table)
            checked_policy = dict(table.get("source_policy", {}))
            checked_policy.pop("forbidden_examples", None)
            checked_content["source_policy"] = checked_policy
            serialized = json.dumps(checked_content, ensure_ascii=False).lower()
            for forbidden in table.get("source_policy", {}).get("forbidden_examples", []):
                # The policy field itself necessarily names the forbidden example;
                # every other occurrence is rejected.
                if str(forbidden).lower() in serialized:
                    errors.append(f"{table_name} table contains forbidden source text: {forbidden}")
            for source in table.get("sources", []):
                url = str(source.get("url", ""))
                parsed = urlparse(url)
                if parsed.scheme != "https" or parsed.hostname not in allowed:
                    errors.append(f"{table_name} source is not on the official allowlist: {url}")

        for model, periods in self.api.get("models", {}).items():
            last_end: datetime | None = None
            for period in periods:
                start = parse_datetime(period.get("effective_from"))
                if last_end and start < last_end:
                    errors.append(f"overlapping API price periods for {model}")
                end_value = period.get("effective_to")
                last_end = parse_datetime(end_value) if end_value else None
                for rate_name, value in period.get("rates", {}).items():
                    if float(value) < 0:
                        errors.append(f"negative API rate {model}.{rate_name}")
        if errors:
            raise ValueError("; ".join(errors))

    def public_ledger(self) -> dict[str, Any]:
        api_rows: list[dict[str, Any]] = []
        for model, periods in self.api.get("models", {}).items():
            for period in periods:
                api_rows.append(
                    {
                        "model": model,
                        "effective_from": period.get("effective_from"),
                        "effective_to": period.get("effective_to"),
                        "rates": period.get("rates"),
                        "note": period.get("note"),
                        "service_tiers": period.get("service_tiers"),
                        "ultrafast": self.api.get("rules", {}).get("model_service_tiers", {}).get(model, {}).get("ultrafast"),
                    }
                )
        credit_rows = [
            {
                "model": model,
                "effective_from": record.get("effective_from"),
                "retired_from_subscription_at": record.get("retired_from_subscription_at"),
                "credits": record.get("credits"),
                "fast_multiplier": self.subscription.get("fast_multipliers", {}).get(model),
                "ultrafast": self.subscription.get("model_service_tiers", {}).get(model, {}).get("ultrafast"),
            }
            for model, record in self.subscription.get("models", {}).items()
        ]
        return {
            "retrieved_at": {
                "api": self.api.get("retrieved_at"),
                "subscription": self.subscription.get("retrieved_at"),
            },
            "api": api_rows,
            "subscription": credit_rows,
            "plans": self.subscription.get("plans", {}),
            "separation_policy": self.subscription.get("separation_policy"),
            "cache_write_policy": self.subscription.get("cache_write_policy"),
            "credit_estimate_policy": self.subscription.get("credit_estimate_policy"),
            "included_usage_multipliers": self.subscription.get("included_usage_multipliers", {}),
        }
