"""Infer a weekly quota's API-dollar equivalent from local observations.

The percentage is an official subscription-limit signal.  The dollar value is
not: it is a model-mix-dependent API Standard equivalent derived by correlating
percentage movement with locally observed token events.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping

from .pricing import PriceBook, parse_datetime


WEEKLY_WINDOW_MINUTES = 7 * 24 * 60
WEEKLY_WINDOW_TOLERANCE_MINUTES = 60
RESET_BUCKET_SECONDS = 15 * 60
MAX_CALIBRATION_SAMPLES = 6
MAX_HISTORY_ROWS = 8


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if isfinite(parsed) else None


def _iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _epoch_iso(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return _iso(datetime.fromtimestamp(value, tz=timezone.utc))
    except (OSError, OverflowError, ValueError):
        return None


def _weekly_window(snapshot: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    candidates: list[tuple[float, str, Mapping[str, Any]]] = []
    for name in ("primary", "secondary"):
        window = snapshot.get(name)
        if not isinstance(window, Mapping):
            continue
        minutes = _safe_float(window.get("window_minutes"))
        if minutes is None:
            continue
        distance = abs(minutes - WEEKLY_WINDOW_MINUTES)
        if distance <= WEEKLY_WINDOW_TOLERANCE_MINUTES:
            candidates.append((distance, name, window))
    if not candidates:
        return None
    _, name, window = min(candidates, key=lambda item: item[0])
    return name, window


def extract_weekly_points(snapshots: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return privacy-safe, normalized weekly-window observations."""

    points: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for snapshot in snapshots:
        selected = _weekly_window(snapshot)
        if selected is None:
            continue
        source_window, window = selected
        used = _safe_float(window.get("used_percent"))
        if used is None:
            continue
        try:
            when = parse_datetime(snapshot.get("timestamp"))
        except (TypeError, ValueError):
            continue
        used = max(0.0, min(100.0, used))
        reset_epoch = _safe_float(window.get("resets_at"))
        plan_type = str(snapshot.get("plan_type") or "unknown").strip().lower()
        limit_name = str(snapshot.get("limit_name") or "general").strip().lower()
        key = (
            _iso(when),
            round(used, 6),
            round(reset_epoch, 3) if reset_epoch is not None else None,
            plan_type,
            limit_name,
            source_window,
        )
        if key in seen:
            continue
        seen.add(key)
        points.append(
            {
                "when": when,
                "timestamp": _iso(when),
                "used_percent": used,
                "remaining_percent": round(100.0 - used, 6),
                "reset_epoch": reset_epoch,
                "resets_at": _epoch_iso(reset_epoch),
                "plan_type": plan_type,
                "limit_name": limit_name,
                "source_window": source_window,
                "window_minutes": int(
                    _safe_float(window.get("window_minutes")) or WEEKLY_WINDOW_MINUTES
                ),
            }
        )
    points.sort(key=lambda point: point["when"])
    return points


def _reset_group(point: Mapping[str, Any]) -> tuple[str, str, int]:
    reset_epoch = point.get("reset_epoch")
    if isinstance(reset_epoch, (int, float)):
        reset_bucket = int(round(float(reset_epoch) / RESET_BUCKET_SECONDS))
    else:
        # A missing reset timestamp is unusual.  Keep observations in bounded
        # calendar-week groups instead of joining unrelated months together.
        reset_bucket = -int(point["when"].timestamp() // (WEEKLY_WINDOW_MINUTES * 60))
    return str(point["plan_type"]), str(point["limit_name"]), reset_bucket


def _observation_runs(points: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        grouped[_reset_group(point)].append(point)

    runs: list[list[dict[str, Any]]] = []
    max_gap_seconds = (WEEKLY_WINDOW_MINUTES + 24 * 60) * 60
    for group in grouped.values():
        group.sort(key=lambda point: point["when"])
        current: list[dict[str, Any]] = []
        for point in group:
            if current:
                previous = current[-1]
                gap = (point["when"] - previous["when"]).total_seconds()
                # One-point drops are commonly caused by integer rounding or a
                # stale concurrent snapshot.  Larger drops begin a new sample.
                material_drop = point["used_percent"] < previous["used_percent"] - 1.01
                if material_drop or gap > max_gap_seconds:
                    runs.append(current)
                    current = []
            current.append(point)
        if current:
            runs.append(current)
    return runs


def _prepare_event_metrics(
    events: Iterable[Mapping[str, Any]], pricebook: PriceBook
) -> tuple[list[datetime], list[dict[str, Any]]]:
    metrics: list[dict[str, Any]] = []
    for event in events:
        # API-key calls do not draw from a ChatGPT/Codex subscription limit.
        if str(event.get("billing_mode") or "unknown").lower() == "api":
            continue
        try:
            when = parse_datetime(event.get("timestamp"))
        except (TypeError, ValueError):
            continue
        tokens = event.get("tokens") if isinstance(event.get("tokens"), Mapping) else {}
        token_count = max(0, int(tokens.get("total_tokens", 0) or 0))
        model = str(event.get("model") or "unknown")
        tier = str(event.get("service_tier") or "default")
        api = pricebook.estimate_api(
            model=model,
            timestamp=when,
            tokens=tokens,
            service_tier="standard",
        )
        credits = pricebook.estimate_subscription_credits(
            model=model,
            timestamp=when,
            tokens=tokens,
            service_tier=tier,
        )
        metrics.append(
            {
                "when": when,
                "tokens": token_count,
                "api_usd": api.value if api.priced else 0.0,
                "api_priced": api.priced,
                "credits": credits.value if credits.priced else 0.0,
                "credits_priced": credits.priced,
                "model": model,
            }
        )
    metrics.sort(key=lambda metric: metric["when"])
    return [metric["when"] for metric in metrics], metrics


def _interval_metrics(
    start: datetime,
    end: datetime,
    event_times: list[datetime],
    event_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    left = bisect_right(event_times, start)
    right = bisect_right(event_times, end)
    selected = event_metrics[left:right]
    tokens = sum(metric["tokens"] for metric in selected)
    api_priced_tokens = sum(
        metric["tokens"] for metric in selected if metric["api_priced"]
    )
    credit_priced_tokens = sum(
        metric["tokens"] for metric in selected if metric["credits_priced"]
    )
    unknown_models = sorted(
        {metric["model"] for metric in selected if not metric["api_priced"]}
    )
    return {
        "calls": len(selected),
        "tokens": tokens,
        "api_usd": sum(metric["api_usd"] for metric in selected),
        "credits": sum(metric["credits"] for metric in selected),
        "api_coverage": api_priced_tokens / tokens if tokens else 0.0,
        "credit_coverage": credit_priced_tokens / tokens if tokens else 0.0,
        "unknown_models": unknown_models,
    }


def _confidence(sample: Mapping[str, Any]) -> dict[str, Any]:
    delta = float(sample["observed_percent_delta"])
    coverage = float(sample["api_price_coverage"])
    calls = int(sample["observed_calls"])
    duration_hours = float(sample["observation_hours"])
    score = (
        min(1.0, delta / 10.0) * 45.0
        + coverage * 25.0
        + min(1.0, calls / 8.0) * 15.0
        + min(1.0, duration_hours / 12.0) * 15.0
    )
    reasons: list[str] = []
    if delta < 3:
        reasons.append("额度变化不足 3 个百分点，整数百分比取整误差较大。")
    if coverage < 0.95:
        reasons.append("部分 token 没有公开官方 API 单价。")
    if calls < 2:
        reasons.append("本地调用样本不足 2 次。")
    if duration_hours < 1:
        reasons.append("观测时间不足 1 小时。")
    if score >= 80 and delta >= 10 and coverage >= 0.95:
        level = "high"
    elif score >= 55 and delta >= 3 and coverage >= 0.8:
        level = "medium"
    else:
        level = "low"
    return {"level": level, "score": round(score, 1), "reasons": reasons}


def _sample_for_run(
    run: list[dict[str, Any]],
    event_times: list[datetime],
    event_metrics: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if len(run) < 2:
        return None
    end = run[-1]
    candidates = run[:-1]
    minimum = min(point["used_percent"] for point in candidates)
    start = next(point for point in candidates if point["used_percent"] == minimum)
    delta = float(end["used_percent"] - start["used_percent"])
    if delta <= 0:
        return None

    observed = _interval_metrics(start["when"], end["when"], event_times, event_metrics)
    duration_hours = max(0.0, (end["when"] - start["when"]).total_seconds() / 3600.0)
    api_usd = float(observed["api_usd"])
    credits = float(observed["credits"])
    tokens = int(observed["tokens"])
    full_api = api_usd * 100.0 / delta if api_usd > 0 else None
    full_credits = credits * 100.0 / delta if credits > 0 else None
    full_tokens = round(tokens * 100.0 / delta) if tokens > 0 else None

    # Each displayed whole-number endpoint can be off by roughly half a point;
    # the delta therefore has about ±1 percentage point of rounding uncertainty.
    low_api = api_usd * 100.0 / (delta + 1.0) if api_usd > 0 else None
    high_api = api_usd * 100.0 / (delta - 1.0) if api_usd > 0 and delta > 1.0 else None
    sample = {
        "from_timestamp": start["timestamp"],
        "to_timestamp": end["timestamp"],
        "from_used_percent": round(float(start["used_percent"]), 6),
        "to_used_percent": round(float(end["used_percent"]), 6),
        "plan_type": end["plan_type"],
        "limit_name": end["limit_name"],
        "observed_percent_delta": round(delta, 6),
        "observation_hours": round(duration_hours, 4),
        "snapshot_count": sum(1 for point in run if point["when"] >= start["when"]),
        "observed_calls": observed["calls"],
        "observed_tokens": tokens,
        "observed_api_equivalent_usd": round(api_usd, 10),
        "observed_subscription_credits": round(credits, 10),
        "api_price_coverage": round(float(observed["api_coverage"]), 6),
        "subscription_price_coverage": round(float(observed["credit_coverage"]), 6),
        "unknown_models": observed["unknown_models"],
        "weekly_api_equivalent_usd": round(full_api, 10) if full_api is not None else None,
        "weekly_api_equivalent_low_usd": round(low_api, 10) if low_api is not None else None,
        "weekly_api_equivalent_high_usd": round(high_api, 10) if high_api is not None else None,
        "weekly_subscription_credits": round(full_credits, 10) if full_credits is not None else None,
        "weekly_token_equivalent": full_tokens,
        "resets_at": end["resets_at"],
    }
    sample["confidence"] = _confidence(sample)
    return sample


def _overlaps(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_start = parse_datetime(left["from_timestamp"])
    left_end = parse_datetime(left["to_timestamp"])
    right_start = parse_datetime(right["from_timestamp"])
    right_end = parse_datetime(right["to_timestamp"])
    return left_start < right_end and right_start < left_end


def _calibrated(
    samples: list[dict[str, Any]], *, plan_type: str, limit_name: str
) -> dict[str, Any] | None:
    candidates = [
        sample
        for sample in sorted(samples, key=lambda item: item["to_timestamp"], reverse=True)
        if sample["observed_percent_delta"] >= 3
        and sample["api_price_coverage"] >= 0.8
        and sample["observed_api_equivalent_usd"] > 0
        and sample["plan_type"] == plan_type
        and sample["limit_name"] == limit_name
    ]
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= MAX_CALIBRATION_SAMPLES:
            break
    if not selected:
        return None
    percent = sum(float(sample["observed_percent_delta"]) for sample in selected)
    api_usd = sum(float(sample["observed_api_equivalent_usd"]) for sample in selected)
    credits = sum(float(sample["observed_subscription_credits"]) for sample in selected)
    tokens = sum(int(sample["observed_tokens"]) for sample in selected)
    if percent <= 0:
        return None
    return {
        "sample_count": len(selected),
        "observed_percent_total": round(percent, 6),
        "observed_tokens": tokens,
        "weekly_api_equivalent_usd": round(api_usd * 100.0 / percent, 10),
        "weekly_subscription_credits": round(credits * 100.0 / percent, 10),
        "weekly_token_equivalent": round(tokens * 100.0 / percent),
        "method": "recent-non-overlapping-weighted-ratio",
    }


def build_weekly_monitor(
    snapshots: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
    pricebook: PriceBook,
) -> dict[str, Any]:
    points = extract_weekly_points(snapshots)
    base = {
        "window_minutes": WEEKLY_WINDOW_MINUTES,
        "snapshot_count": len(points),
        "latest": None,
        "current_estimate": None,
        "calibrated_estimate": None,
        "history": [],
        "method": "quota-percent-delta-correlated-with-local-token-events",
        "limitations": [
            "美元值是按同期模型组合折算的 API Standard 等价，不是订阅现金价值或官方承诺额度。",
            "ChatGPT Work、云端任务、其它设备、图像和未公开价模型可能改变百分比，但不一定出现在本机 token 日志中。",
            "官方百分比通常按整点显示；样本变化越小，推算区间越宽。",
        ],
    }
    if not points:
        return {"status": "unavailable", **base}

    latest_point = points[-1]
    base["latest"] = {
        key: latest_point[key]
        for key in (
            "timestamp",
            "used_percent",
            "remaining_percent",
            "resets_at",
            "plan_type",
            "limit_name",
            "source_window",
            "window_minutes",
        )
    }
    event_times, event_metrics = _prepare_event_metrics(events, pricebook)
    runs = _observation_runs(points)
    samples: list[dict[str, Any]] = []
    current_sample = None
    for run in runs:
        sample = _sample_for_run(run, event_times, event_metrics)
        if sample is None:
            continue
        samples.append(sample)
        if run[-1] is latest_point:
            current_sample = sample

    samples.sort(key=lambda sample: sample["to_timestamp"], reverse=True)
    base["history"] = samples[:MAX_HISTORY_ROWS]
    base["calibrated_estimate"] = _calibrated(
        samples,
        plan_type=latest_point["plan_type"],
        limit_name=latest_point["limit_name"],
    )
    base["current_estimate"] = current_sample

    if current_sample is None:
        return {"status": "collecting", **base}
    if current_sample["weekly_api_equivalent_usd"] is None:
        return {"status": "uncorrelated", **base}

    full_api = float(current_sample["weekly_api_equivalent_usd"])
    used = float(latest_point["used_percent"])
    current_sample["estimated_used_api_equivalent_usd"] = round(full_api * used / 100.0, 10)
    current_sample["estimated_remaining_api_equivalent_usd"] = round(
        full_api * (100.0 - used) / 100.0, 10
    )
    status = "ready" if current_sample["confidence"]["level"] in {"medium", "high"} else "provisional"
    return {"status": status, **base}
