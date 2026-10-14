"""Streaming, content-minimizing scanner for local Codex JSONL sessions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .pricing import TOKEN_FIELDS, parse_datetime


SESSION_ID_RE = re.compile(r"([0-9a-f]{8}-[0-9a-f-]{27,})", re.IGNORECASE)
SUBSCRIPTION_PLAN_TYPES = {
    "free",
    "go",
    "plus",
    "pro",
    "prolite",
    "business",
    "team",
    "enterprise",
    "edu",
    "education",
}
API_PLAN_TYPES = {"api", "payg", "pay_as_you_go", "usage_based"}


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _token_dict(raw: Any) -> dict[str, int]:
    source = raw if isinstance(raw, dict) else {}
    result = {field: _safe_int(source.get(field)) for field in TOKEN_FIELDS}
    if result["total_tokens"] == 0:
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
    return result


def _delta_tokens(current: dict[str, int], previous: dict[str, int] | None, fallback: dict[str, int]) -> dict[str, int]:
    if previous is None:
        return current
    delta = {field: current[field] - previous.get(field, 0) for field in TOKEN_FIELDS}
    if any(value < 0 for value in delta.values()):
        return fallback
    if all(value == 0 for value in delta.values()):
        return {field: 0 for field in TOKEN_FIELDS}
    if delta["total_tokens"] == 0:
        delta["total_tokens"] = delta["input_tokens"] + delta["output_tokens"]
    return delta


def classify_billing(plan_type: str | None, override: str = "auto") -> str:
    if override in {"api", "subscription"}:
        return override
    normalized = str(plan_type or "").strip().lower()
    if normalized in SUBSCRIPTION_PLAN_TYPES:
        return "subscription"
    if normalized in API_PLAN_TYPES:
        return "api"
    return "unknown"


def _anonymous_session_id(path: Path) -> str:
    match = SESSION_ID_RE.search(path.name)
    material = match.group(1).lower() if match else str(path.resolve()).lower()
    return "session-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]


def _sanitize_rate_limits(raw: Any, timestamp: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    def window(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            "used_percent": value.get("used_percent"),
            "window_minutes": value.get("window_minutes"),
            "resets_at": value.get("resets_at"),
        }

    credits = raw.get("credits") if isinstance(raw.get("credits"), dict) else {}
    return {
        "timestamp": timestamp,
        "plan_type": raw.get("plan_type"),
        "limit_name": raw.get("limit_name"),
        "primary": window(raw.get("primary")),
        "secondary": window(raw.get("secondary")),
        "credits": {
            "has_credits": credits.get("has_credits"),
            "unlimited": credits.get("unlimited"),
            "balance": credits.get("balance"),
        },
        "spend_control_reached": raw.get("spend_control_reached"),
    }


def _iso_or_fallback(value: Any, fallback: datetime) -> str:
    try:
        return parse_datetime(str(value)).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        return fallback.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def scan_session_file(path: Path, *, billing_mode: str = "auto") -> dict[str, Any]:
    current_model = "unknown"
    current_tier = "default"
    current_plan_type: str | None = None
    previous_total: dict[str, int] | None = None
    events: list[dict[str, Any]] = []
    rate_snapshots: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    active_turn: dict[str, Any] | None = None
    malformed = 0
    relevant_lines = 0
    file_time = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    with path.open("rb") as handle:
        for raw_line in handle:
            if not any(marker in raw_line for marker in (
                b"turn_context", b"thread_settings_applied", b"token_count",
                b'"task_started"', b'"task_complete"', b'"turn_aborted"',
            )):
                continue
            relevant_lines += 1
            try:
                record = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                malformed += 1
                continue
            if not isinstance(record, dict):
                continue
            top_type = record.get("type")
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}

            if top_type == "turn_context":
                candidate = payload.get("model")
                if candidate:
                    current_model = str(candidate).strip().lower()
                if "service_tier" in payload:
                    current_tier = str(payload["service_tier"] or "default").strip().lower()
                continue

            if top_type == "event_msg" and payload.get("type") == "thread_settings_applied":
                settings = payload.get("thread_settings") if isinstance(payload.get("thread_settings"), dict) else {}
                if settings.get("model"):
                    current_model = str(settings["model"]).strip().lower()
                if "service_tier" in settings:
                    current_tier = str(settings["service_tier"] or "default").strip().lower()
                continue

            if top_type == "event_msg" and payload.get("type") == "task_started":
                active_turn = {
                    "turn_id": payload.get("turn_id"),
                    "output_tokens": 0,
                    "complete_usage": True,
                }
                continue

            if top_type == "event_msg" and payload.get("type") == "turn_aborted":
                active_turn = None
                continue

            if top_type == "event_msg" and payload.get("type") == "task_complete":
                # Only retain numeric timing fields, never last_agent_message or IDs.
                if active_turn and active_turn["turn_id"] == payload.get("turn_id"):
                    def duration(name: str) -> float | None:
                        try:
                            value = float(payload[name])
                            return value if math.isfinite(value) and value >= 0 else None
                        except (KeyError, TypeError, ValueError, OverflowError):
                            return None

                    elapsed = duration("duration_ms")
                    ttft = duration("time_to_first_token_ms")
                    if elapsed and active_turn["complete_usage"]:
                        turns.append({
                            "timestamp": _iso_or_fallback(record.get("timestamp"), file_time),
                            "duration_ms": elapsed,
                            "time_to_first_token_ms": ttft if ttft is not None and ttft <= elapsed else None,
                            "output_tokens": active_turn["output_tokens"],
                            "model": current_model,
                        })
                active_turn = None
                continue

            if top_type != "event_msg" or payload.get("type") != "token_count":
                continue

            timestamp = _iso_or_fallback(record.get("timestamp"), file_time)
            rate_limits = payload.get("rate_limits")
            sanitized = _sanitize_rate_limits(rate_limits, timestamp)
            if sanitized:
                rate_snapshots.append(sanitized)
                if sanitized.get("plan_type") is not None:
                    current_plan_type = str(sanitized["plan_type"])

            info = payload.get("info") if isinstance(payload.get("info"), dict) else None
            if not info:
                continue
            total_raw = info.get("total_token_usage")
            last = _token_dict(info.get("last_token_usage"))
            if isinstance(total_raw, dict):
                total = _token_dict(total_raw)
                if active_turn and previous_total is None and total["output_tokens"] != last["output_tokens"]:
                    active_turn["complete_usage"] = False
                usage = _delta_tokens(total, previous_total, last)
                previous_total = total
            else:
                usage = last
            if usage["input_tokens"] == 0 and usage["output_tokens"] == 0:
                continue
            if active_turn:
                active_turn["output_tokens"] += usage["output_tokens"]

            events.append(
                {
                    "timestamp": timestamp,
                    "model": current_model,
                    "service_tier": current_tier,
                    "plan_type": current_plan_type,
                    "billing_mode": classify_billing(current_plan_type, billing_mode),
                    "tokens": usage,
                }
            )

    session_id = _anonymous_session_id(path)
    for event in events:
        event["session_id"] = session_id
    token_total = sum(event["tokens"]["total_tokens"] for event in events)
    return {
        "id": session_id,
        "source": "archived" if "archived_sessions" in {part.lower() for part in path.parts} else "active",
        "events": events,
        "rate_snapshots": rate_snapshots,
        "turns": turns,
        "token_total": token_total,
        "malformed_relevant_lines": malformed,
        "relevant_lines": relevant_lines,
        "modified_at": file_time.isoformat().replace("+00:00", "Z"),
    }


def discover_session_files(codex_home: Path, *, include_archived: bool = True) -> list[Path]:
    roots = [codex_home / "sessions"]
    if include_archived:
        roots.append(codex_home / "archived_sessions")
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                continue
            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)
            paths.append(resolved)
    return sorted(paths)


def scan_codex(
    codex_home: Path | None = None,
    *,
    include_archived: bool = True,
    billing_mode: str = "auto",
    cache: dict[Path, tuple[tuple[int, ...], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    home = (codex_home or default_codex_home()).expanduser().resolve()
    files = discover_session_files(home, include_archived=include_archived)
    by_session: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []

    for path in files:
        try:
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            cached = cache.get(path) if cache is not None else None
            if cached and cached[0] == key:
                session = cached[1]
            else:
                session = scan_session_file(path, billing_mode=billing_mode)
                if cache is not None:
                    cache[path] = (key, session)
        except (OSError, PermissionError) as exc:
            failures.append(
                {"session": _anonymous_session_id(path), "error": type(exc).__name__}
            )
            continue
        existing = by_session.get(session["id"])
        if existing is None or (session["token_total"], session["modified_at"]) > (existing["token_total"], existing["modified_at"]):
            by_session[session["id"]] = session

    if cache is not None:
        present = set(files)
        for path in list(cache):
            if path not in present:
                del cache[path]

    events: list[dict[str, Any]] = []
    rate_snapshots: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    malformed = 0
    for session in by_session.values():
        events.extend(session["events"])
        rate_snapshots.extend(session["rate_snapshots"])
        turns.extend(session.get("turns", []))
        malformed += session["malformed_relevant_lines"]
    events.sort(key=lambda item: item["timestamp"])
    rate_snapshots.sort(key=lambda item: item["timestamp"])

    plan_counts = Counter(str(event.get("plan_type")) for event in events if event.get("plan_type"))
    return {
        "codex_home_label": "~/.codex",
        "files_discovered": len(files),
        "sessions": list(by_session.values()),
        "events": events,
        "rate_snapshots": rate_snapshots,
        "turns": turns,
        "latest_rate_limit": rate_snapshots[-1] if rate_snapshots else None,
        "plan_type_counts": dict(plan_counts),
        "malformed_relevant_lines": malformed,
        "failures": failures,
        "privacy": {
            "prompt_content_exported": False,
            "paths_exported": False,
            "auth_files_read": False,
            "network_used": False,
        },
    }


class CachedScanner:
    """Reuse sanitized results for unchanged files; never cache message content.

    Changed files are reread so truncation, partial writes, counters and model
    changes follow exactly the same parser as a one-shot scan.
    """

    def __init__(self, codex_home: Path | None = None, *, include_archived: bool = True,
                 billing_mode: str = "auto"):
        self.home = codex_home
        self.include_archived = include_archived
        self.billing_mode = billing_mode
        self._cache: dict[Path, tuple[tuple[int, ...], dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def scan(self) -> dict[str, Any]:
        with self._lock:
            return scan_codex(self.home, include_archived=self.include_archived,
                              billing_mode=self.billing_mode, cache=self._cache)


def filter_events(
    events: Iterable[dict[str, Any]],
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    start = parse_datetime(since) if since else None
    end = parse_datetime(until) if until else None
    selected = []
    for event in events:
        when = parse_datetime(event["timestamp"])
        if start and when < start:
            continue
        if end and when >= end:
            continue
        selected.append(event)
    return selected
