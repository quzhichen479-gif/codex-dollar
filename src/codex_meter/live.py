"""Small, privacy-safe live snapshots with explicit measurement boundaries."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .pricing import PriceBook, parse_datetime, split_input_tokens
from .report import _window_summary


def _when(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return parse_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None


def build_live_snapshot(scan: dict[str, Any], book: PriceBook, *,
                        now: datetime | None = None) -> dict[str, Any]:
    now = parse_datetime(now or datetime.now(timezone.utc))
    window_seconds = 60
    recent = []
    latest = None
    for event in scan.get("events", []):
        when = _when(event.get("timestamp"))
        if when is None or when > now:
            continue
        if latest is None or when > latest[0]:
            latest = (when, event)
        if 0 <= (now - when).total_seconds() < window_seconds:
            recent.append(event)

    output = inputs = reasoning = 0
    api = credits = 0.0
    unpriced_api = unpriced_credits = 0
    for event in recent:
        tokens = event.get("tokens", {})
        split = split_input_tokens(tokens)
        inputs += split["input_total"]
        output += split["output"]
        reasoning += split["reasoning_output"]
        args = {"model": event.get("model", "unknown"),
                "timestamp": event["timestamp"], "tokens": tokens}
        estimate = book.estimate_api(**args, service_tier="standard")
        api += estimate.value if estimate.priced else 0
        unpriced_api += 0 if estimate.priced else split["total"]
        if event.get("billing_mode") == "subscription":
            estimate = book.estimate_subscription_credits(
                **args, service_tier=event.get("service_tier", "default"))
            credits += estimate.value if estimate.priced else 0
            unpriced_credits += 0 if estimate.priced else split["total"]

    raw = scan.get("latest_rate_limit") or {}
    stamp = _when(raw.get("timestamp"))
    age = (now - stamp).total_seconds() if stamp else None
    quota = {"timestamp": raw.get("timestamp"), "age_seconds": age,
             "stale": age is None or age < 0 or age > 300,
             "plan_type": raw.get("plan_type"), "limit_name": raw.get("limit_name"),
             "credits": raw.get("credits"), "spend_control_reached": raw.get("spend_control_reached")}
    for name in ("primary", "secondary"):
        summary = _window_summary(raw.get(name))
        if summary:
            reset = _when(summary.get("resets_at"))
            summary["expired"] = bool(reset and reset <= now)
        quota[name] = summary

    last_turn = None
    for turn in scan.get("turns", []):
        stamp = _when(turn.get("timestamp"))
        elapsed = turn.get("duration_ms")
        if stamp and stamp <= now and isinstance(elapsed, (int, float)) and math.isfinite(elapsed) and elapsed > 0:
            if last_turn is None or stamp > _when(last_turn["timestamp"]):
                last_turn = {**turn, "output_tokens_per_second": round(turn["output_tokens"] * 1000 / elapsed, 2)}

    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "window_seconds": window_seconds,
        "scope": "all-local-sessions",
        "speed": {"output_tokens_per_second": round(output / window_seconds, 2),
                  "input_tokens_per_second": round(inputs / window_seconds, 2),
                  "output_tokens": output, "input_tokens": inputs,
                  "reasoning_output_tokens": reasoning, "streaming_measured": False,
                  "active_sessions": len({e.get("session_id") for e in recent})},
        "latest_event_at": latest[1]["timestamp"] if latest else None,
        "latest_model": latest[1].get("model") if latest else None,
        "last_turn": last_turn,
        "quota": quota,
        "recent_cost": {"api_standard_equivalent_usd": round(api, 8),
                        "subscription_credits_estimate": round(credits, 6),
                        "unpriced_api_tokens": unpriced_api,
                        "unpriced_subscription_tokens": unpriced_credits},
        "scan": {"files_discovered": scan.get("files_discovered", 0),
                 "read_failures": len(scan.get("failures", []))},
    }
