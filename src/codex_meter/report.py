"""Aggregate scanned events into a privacy-safe dashboard report."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from datetime import datetime, timezone
from typing import Any

from .monitor import build_weekly_monitor
from .pricing import PriceBook, TOKEN_FIELDS, parse_datetime, split_input_tokens
from .scanner import filter_events


def _empty_tokens() -> dict[str, int]:
    return {field: 0 for field in TOKEN_FIELDS}


def _add_tokens(target: dict[str, int], source: dict[str, Any]) -> None:
    for field in TOKEN_FIELDS:
        target[field] += max(0, int(source.get(field, 0) or 0))


def _money(value: float) -> float:
    return round(float(value), 10)


def _window_summary(window: Any) -> dict[str, Any] | None:
    if not isinstance(window, dict):
        return None
    used = window.get("used_percent")
    try:
        used_value = float(used) if used is not None else None
        used_value = max(0.0, min(100.0, used_value)) if used_value is not None and math.isfinite(used_value) else None
    except (TypeError, ValueError):
        used_value = None
    reset_value = window.get("resets_at")
    reset_iso = None
    try:
        if reset_value is not None:
            reset_iso = datetime.fromtimestamp(float(reset_value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        reset_iso = None
    return {
        "used_percent": used_value,
        "remaining_percent": round(100.0 - used_value, 2) if used_value is not None else None,
        "window_minutes": window.get("window_minutes"),
        "resets_at": reset_iso,
    }


def build_report(
    scan: dict[str, Any],
    pricebook: PriceBook,
    *,
    since: str | None = None,
    until: str | None = None,
    plan_override: str | None = None,
) -> dict[str, Any]:
    events = filter_events(scan.get("events", []), since=since, until=until)
    total_tokens = _empty_tokens()
    daily: dict[str, dict[str, Any]] = {}
    models: dict[str, dict[str, Any]] = {}
    sessions: dict[str, dict[str, Any]] = {}
    billing_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    plan_counts: Counter[str] = Counter()
    unknown_api: Counter[str] = Counter()
    unknown_credits: Counter[str] = Counter()

    api_equivalent = 0.0
    api_estimated_charge = 0.0
    subscription_credits = 0.0
    all_credit_equivalent = 0.0
    api_priced_tokens = 0
    credit_priced_tokens = 0
    unpriced_api_tokens = 0
    unpriced_api_charge_tokens = 0
    unpriced_credit_tokens = 0
    unpriced_subscription_call_tokens = 0
    long_context_calls = 0
    fast_calls = 0

    for event in events:
        tokens = event["tokens"]
        _add_tokens(total_tokens, tokens)
        model = str(event.get("model") or "unknown")
        tier = str(event.get("service_tier") or "default")
        billing = str(event.get("billing_mode") or "unknown")
        plan_type = event.get("plan_type")
        billing_counts[billing] += 1
        tier_counts[tier] += 1
        if plan_type:
            plan_counts[str(plan_type)] += 1
        if tier in {"fast", "priority", "ultrafast"}:
            fast_calls += 1

        api_standard = pricebook.estimate_api(
            model=model,
            timestamp=event["timestamp"],
            tokens=tokens,
            service_tier="standard",
        )
        api_observed = pricebook.estimate_api(
            model=model,
            timestamp=event["timestamp"],
            tokens=tokens,
            service_tier=tier,
        )
        credit = pricebook.estimate_subscription_credits(
            model=model,
            timestamp=event["timestamp"],
            tokens=tokens,
            service_tier=tier,
        )
        token_count = int(tokens.get("total_tokens", 0) or 0)
        if api_standard.priced:
            api_equivalent += api_standard.value
            api_priced_tokens += token_count
            if api_standard.context_band == "long":
                long_context_calls += 1
        else:
            unpriced_api_tokens += token_count
            unknown_api[model] += token_count
        if billing == "api" and api_observed.priced:
            api_estimated_charge += api_observed.value
        elif billing == "api":
            unpriced_api_charge_tokens += token_count
        if credit.priced:
            all_credit_equivalent += credit.value
            credit_priced_tokens += token_count
            if billing == "subscription":
                subscription_credits += credit.value
        else:
            unpriced_credit_tokens += token_count
            unknown_credits[model] += token_count
            if billing == "subscription":
                unpriced_subscription_call_tokens += token_count

        date_key = parse_datetime(event["timestamp"]).date().isoformat()
        day = daily.setdefault(
            date_key,
            {
                "date": date_key,
                "tokens": _empty_tokens(),
                "calls": 0,
                "api_equivalent_usd": 0.0,
                "subscription_credits": 0.0,
            },
        )
        _add_tokens(day["tokens"], tokens)
        day["calls"] += 1
        day["api_equivalent_usd"] += api_standard.value if api_standard.priced else 0.0
        day["subscription_credits"] += credit.value if credit.priced and billing == "subscription" else 0.0

        model_row = models.setdefault(
            model,
            {
                "model": model,
                "tokens": _empty_tokens(),
                "calls": 0,
                "sessions": set(),
                "service_tiers": Counter(),
                "billing_modes": Counter(),
                "api_equivalent_usd": 0.0,
                "subscription_credits": 0.0,
                "api_priced": True,
                "credits_priced": True,
            },
        )
        _add_tokens(model_row["tokens"], tokens)
        model_row["calls"] += 1
        model_row["sessions"].add(event["session_id"])
        model_row["service_tiers"][tier] += 1
        model_row["billing_modes"][billing] += 1
        model_row["api_equivalent_usd"] += api_standard.value if api_standard.priced else 0.0
        model_row["subscription_credits"] += credit.value if credit.priced and billing == "subscription" else 0.0
        model_row["api_priced"] = model_row["api_priced"] and api_standard.priced
        model_row["credits_priced"] = model_row["credits_priced"] and credit.priced

        session = sessions.setdefault(
            event["session_id"],
            {
                "id": event["session_id"],
                "first_at": event["timestamp"],
                "last_at": event["timestamp"],
                "tokens": _empty_tokens(),
                "calls": 0,
                "models": Counter(),
                "service_tiers": Counter(),
                "billing_modes": Counter(),
                "api_equivalent_usd": 0.0,
                "subscription_credits": 0.0,
            },
        )
        session["first_at"] = min(session["first_at"], event["timestamp"])
        session["last_at"] = max(session["last_at"], event["timestamp"])
        _add_tokens(session["tokens"], tokens)
        session["calls"] += 1
        session["models"][model] += 1
        session["service_tiers"][tier] += 1
        session["billing_modes"][billing] += 1
        session["api_equivalent_usd"] += api_standard.value if api_standard.priced else 0.0
        session["subscription_credits"] += credit.value if credit.priced and billing == "subscription" else 0.0

    daily_rows = []
    for day in sorted(daily.values(), key=lambda item: item["date"]):
        day["api_equivalent_usd"] = _money(day["api_equivalent_usd"])
        day["subscription_credits"] = _money(day["subscription_credits"])
        daily_rows.append(day)

    model_rows = []
    for row in models.values():
        row["sessions"] = len(row["sessions"])
        row["service_tiers"] = dict(row["service_tiers"])
        row["billing_modes"] = dict(row["billing_modes"])
        row["api_equivalent_usd"] = _money(row["api_equivalent_usd"])
        row["subscription_credits"] = _money(row["subscription_credits"])
        model_rows.append(row)
    model_rows.sort(key=lambda item: item["tokens"]["total_tokens"], reverse=True)

    session_rows = []
    for row in sessions.values():
        row["models"] = dict(row["models"])
        row["service_tiers"] = dict(row["service_tiers"])
        row["billing_modes"] = dict(row["billing_modes"])
        row["api_equivalent_usd"] = _money(row["api_equivalent_usd"])
        row["subscription_credits"] = _money(row["subscription_credits"])
        session_rows.append(row)
    session_rows.sort(key=lambda item: item["last_at"], reverse=True)

    latest_rate = scan.get("latest_rate_limit")
    current_plan_type = latest_rate.get("plan_type") if isinstance(latest_rate, dict) else None
    if not current_plan_type and plan_counts:
        current_plan_type = plan_counts.most_common(1)[0][0]
    plan_reference = pricebook.plan_reference(current_plan_type, override=plan_override)
    weekly_monitor = build_weekly_monitor(
        scan.get("rate_snapshots", []),
        scan.get("events", []),
        pricebook,
    )
    rate_limit = None
    if isinstance(latest_rate, dict):
        rate_limit = {
            "timestamp": latest_rate.get("timestamp"),
            "plan_type": latest_rate.get("plan_type"),
            "limit_name": latest_rate.get("limit_name"),
            "primary": _window_summary(latest_rate.get("primary")),
            "secondary": _window_summary(latest_rate.get("secondary")),
            "credits": latest_rate.get("credits"),
            "spend_control_reached": latest_rate.get("spend_control_reached"),
        }

    input_total = total_tokens["input_tokens"]
    cached_total = total_tokens["cached_input_tokens"]
    total_count = total_tokens["total_tokens"]
    coverage_api = api_priced_tokens / total_count if total_count else 1.0
    coverage_credits = credit_priced_tokens / total_count if total_count else 1.0

    source_map: dict[str, dict[str, str]] = {}
    for table in (pricebook.api, pricebook.subscription):
        for source in table.get("sources", []):
            source_map[source["url"]] = {"label": source["label"], "url": source["url"]}

    caveats = [
        "API 等价金额按每次调用发生日期选择官方历史单价；它不是订阅账单。",
        "订阅调用按独立的付费 credits 表折算等价用量，不代表实际扣款或套餐内已扣额度；会员月费不继承 API 降价。",
        "Fast 的付费 credits 按 2× 计算，套餐内额度消耗为 2.5×；Astra / Sol Ultrafast 分别为 6× 和 8×，不能混用。",
        "Plus/Pro/Business 的实际包含额度不是固定 token 包；精确剩余额度优先看日志中的官方限额百分比或 Codex /status。",
        "本地 token 日志不能完整反映 Web Search、容器、图像生成等按调用计费项目，也不推断区域处理 10% 加价。",
        "财务对账应以 OpenAI API Costs endpoint 或官方 Usage Dashboard/发票为准。",
        "未知或没有公开价的模型不会套用近似价格，相关 token 会明确列为未计价。",
        "周额度美元推算是本机 token 与官方百分比变化的相关估计，不是订阅现金价值或 OpenAI 承诺的固定额度。",
        "ChatGPT Work、云端任务和其它设备会共享或影响用量；若这些消耗未出现在本机日志，周额度推算可信度会下降。",
    ]
    if plan_reference and plan_reference.get("confidence") not in {"official-name", "user-override"}:
        caveats.append(
            "当前套餐映射来自本地日志的内部 plan_type，属于推断；可用 --plan 显式指定套餐。"
        )
    if unknown_api:
        caveats.append("存在 API 未计价模型：" + "、".join(sorted(unknown_api)))
    if unpriced_api_charge_tokens:
        caveats.append(f"API 预计费用有 {unpriced_api_charge_tokens:,} tokens 缺少对应模型、服务等级或日期的官方费率，未计入费用合计。")

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": {
            "since": since,
            "until": until,
            "first_event": events[0]["timestamp"] if events else None,
            "last_event": events[-1]["timestamp"] if events else None,
            "timezone": "UTC",
        },
        "summary": {
            "tokens": total_tokens,
            "calls": len(events),
            "sessions": len(sessions),
            "files_discovered": scan.get("files_discovered", 0),
            "api_standard_equivalent_usd": _money(api_equivalent),
            "api_estimated_charge_usd": _money(api_estimated_charge),
            "subscription_credits_estimate": _money(subscription_credits),
            "all_usage_credit_equivalent": _money(all_credit_equivalent),
            "cache_hit_ratio": round(cached_total / input_total, 6) if input_total else 0.0,
            "api_price_coverage": round(coverage_api, 6),
            "subscription_price_coverage": round(coverage_credits, 6),
            "unpriced_api_tokens": unpriced_api_tokens,
            "unpriced_api_charge_tokens": unpriced_api_charge_tokens,
            "unpriced_subscription_tokens": unpriced_credit_tokens,
            "unpriced_subscription_call_tokens": unpriced_subscription_call_tokens,
            "long_context_calls": long_context_calls,
            "fast_calls": fast_calls,
            "billing_modes": dict(billing_counts),
            "service_tiers": dict(tier_counts),
        },
        "current": {
            "rate_limit": rate_limit,
            "plan_reference": plan_reference,
            "detected_plan_type": current_plan_type,
        },
        "weekly_monitor": weekly_monitor,
        "daily": daily_rows,
        "models": model_rows,
        "sessions": session_rows,
        "unknown_pricing": {
            "api": dict(unknown_api),
            "subscription": dict(unknown_credits),
        },
        "scan": {
            "codex_home": scan.get("codex_home_label"),
            "plan_type_counts": scan.get("plan_type_counts", {}),
            "malformed_relevant_lines": scan.get("malformed_relevant_lines", 0),
            "failures": scan.get("failures", []),
            "privacy": scan.get("privacy", {}),
        },
        "pricing_ledger": pricebook.public_ledger(),
        "sources": list(source_map.values()),
        "caveats": caveats,
    }
