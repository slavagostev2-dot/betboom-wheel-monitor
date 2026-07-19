from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import monitor_data as data_store

ROOT = Path(__file__).resolve().parent
PRIMARY_PATH = ROOT / "public_sources.txt"
NIGHTLY_PATH = ROOT / "source_catalog.txt"
STATS_PATH = ROOT / "source_stats.json"
ACCESS_PATH = ROOT / "bot_access.json"
STATE_PATH = ROOT / "source_tier_state.json"

UTC = timezone.utc
INACTIVITY_DAYS = max(1, int(os.getenv("SOURCE_AUTO_DEMOTION_DAYS", "7")))
MIN_COVERAGE_DAYS = max(1, int(os.getenv("SOURCE_AUTO_DEMOTION_MIN_COVERAGE_DAYS", "6")))
MIN_SUCCESSFUL_CHECKS = max(1, int(os.getenv("SOURCE_AUTO_DEMOTION_MIN_CHECKS", "100")))
MAX_LAST_CHECK_AGE_HOURS = max(1, int(os.getenv("SOURCE_AUTO_DEMOTION_MAX_CHECK_AGE_HOURS", "2")))


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default
    return value if isinstance(value, dict) else default


def read_list(path: Path) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.split("#", 1)[0].strip().lstrip("@")
        key = value.casefold()
        if value and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def source_record(sources: dict[str, Any], source: str) -> dict[str, Any]:
    target = source.casefold()
    for key, value in sources.items():
        if str(key).casefold() == target and isinstance(value, dict):
            return value
    return {}


def daily_record(payload: dict[str, Any], day_key: str, source: str) -> dict[str, Any]:
    daily = payload.get("daily", {})
    if not isinstance(daily, dict):
        return {}
    day = daily.get(day_key, {})
    if not isinstance(day, dict):
        return {}
    sources = day.get("sources", {})
    if not isinstance(sources, dict):
        return {}
    return source_record(sources, source)


def coverage_days(payload: dict[str, Any], source: str, now: datetime) -> int:
    covered = 0
    for offset in range(INACTIVITY_DAYS):
        day_key = (now.date() - timedelta(days=offset)).isoformat()
        record = daily_record(payload, day_key, source)
        if int(record.get("successful_checks", 0) or 0) > 0:
            covered += 1
    return covered


def eligible_for_nightly(payload: dict[str, Any], source: str, now: datetime) -> tuple[bool, str]:
    sources = payload.get("sources", {})
    if not isinstance(sources, dict):
        return False, "нет статистики"
    record = source_record(sources, source)
    if not record:
        return False, "нет статистики"

    cutoff = now - timedelta(days=INACTIVITY_DAYS)
    first_checked = parse_dt(record.get("first_checked_at"))
    last_checked = parse_dt(record.get("last_checked_at"))
    last_wheel = parse_dt(record.get("last_wheel_post_at"))
    successful = int(record.get("successful_checks", 0) or 0)
    covered = coverage_days(payload, source, now)

    if first_checked is None or first_checked > cutoff:
        return False, "ещё не прошло 7 полных дней наблюдения"
    if last_checked is None or now - last_checked > timedelta(hours=MAX_LAST_CHECK_AGE_HOURS):
        return False, "монитор недавно не проверял источник"
    if successful < MIN_SUCCESSFUL_CHECKS:
        return False, "недостаточно успешных проверок"
    if covered < MIN_COVERAGE_DAYS:
        return False, "недостаточное покрытие по дням"
    if last_wheel is not None and last_wheel > cutoff:
        return False, "колесо находилось в последние 7 дней"
    return True, "7 полных дней без новых колёс при достаточном покрытии"


def main() -> int:
    now = datetime.now(UTC)
    primary = read_list(PRIMARY_PATH)
    nightly = read_list(NIGHTLY_PATH)
    payload = read_json(STATS_PATH, {"sources": {}, "daily": {}})

    candidates: list[str] = []
    reasons: dict[str, str] = {}
    for source in primary:
        eligible, reason = eligible_for_nightly(payload, source, now)
        reasons[source] = reason
        if eligible:
            candidates.append(source)

    state = {
        "version": 1,
        "last_run_at": now.isoformat(),
        "criteria": {
            "inactivity_days": INACTIVITY_DAYS,
            "minimum_coverage_days": MIN_COVERAGE_DAYS,
            "minimum_successful_checks": MIN_SUCCESSFUL_CHECKS,
            "maximum_last_check_age_hours": MAX_LAST_CHECK_AGE_HOURS,
        },
        "primary_before": len(primary),
        "policy": "manual_nightly_only",
        "primary_after": len(primary),
        "nightly_after": len(nightly),
        "total_after": len({value.casefold() for value in primary + nightly}),
        "moved_to_nightly": [],
        "would_move_to_nightly": candidates,
        "reasons": reasons,
    }
    data_store.atomic_write_json(STATE_PATH, state)
    print(
        f"Primary sources: {len(primary)}; nightly sources: {len(nightly)}; "
        f"eligible for manual review after {INACTIVITY_DAYS} days: {len(candidates)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
