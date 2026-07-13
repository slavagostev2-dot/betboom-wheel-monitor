from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import monitor_data

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "source_registry.json"
UTC = timezone.utc


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(default)
    return value if isinstance(value, dict) else dict(default)


def _read_sources(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    result: list[str] = []
    for line in lines:
        value = line.split("#", 1)[0].strip().lstrip("@")
        if value:
            result.append(value)
    return result


def _find_casefold(mapping: object, source: str) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    target = source.casefold()
    for key, value in mapping.items():
        if str(key).casefold() == target and isinstance(value, dict):
            return value
    return {}


def _merge_stats(*collections: object) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for collection in collections:
        if not isinstance(collection, dict):
            continue
        for source, raw in collection.items():
            if not isinstance(raw, dict):
                continue
            key = str(source).casefold()
            target = result.setdefault(key, {})
            for name, value in raw.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    target[name] = int(target.get(name, 0) or 0) + value
                elif value and not target.get(name):
                    target[name] = value
    return result


def _status_detail(
    source: str,
    mode: str,
    health: dict[str, Any],
    discovery: dict[str, Any],
) -> tuple[str, str, str, bool, bool]:
    raw_status = str(
        health.get("status")
        or discovery.get("status")
        or "not_checked"
    ).strip().lower()

    if raw_status == "ok":
        return (
            "available",
            "Проверяется",
            "Источник успешно отвечает и участвует в мониторинге.",
            True,
            True,
        )
    if raw_status == "quarantined":
        next_check = str(health.get("next_recheck_at") or "")
        suffix = f" Следующая попытка: {next_check}." if next_check else ""
        return (
            "unavailable",
            "Временно недоступен",
            "Источник временно пропускается после серии ошибок; система повторит проверку автоматически."
            + suffix,
            True,
            False,
        )
    if raw_status == "empty":
        return (
            "unavailable",
            "Нет публичных сообщений",
            "Telegram открыл источник, но публичные сообщения не найдены. Возможны закрытие, удаление или временное ограничение.",
            True,
            False,
        )
    if raw_status == "error":
        error = str(health.get("last_error") or discovery.get("error") or "ошибка ответа")
        return (
            "unavailable",
            "Ошибка проверки",
            f"Источник был запрошен, но проверка завершилась ошибкой: {error[:300]}",
            True,
            False,
        )
    if raw_status in {"disabled", "excluded"}:
        return (
            "excluded",
            "Исключён",
            "Источник исключён внутренними правилами мониторинга.",
            False,
            False,
        )
    return (
        "not_checked",
        "Ожидает проверки",
        (
            "Источник включён в единый список и ожидает ближайшей плановой проверки."
            if mode == "nightly"
            else "Источник включён в мониторинг, но результат проверки ещё не записан."
        ),
        False,
        False,
    )


def build_snapshot() -> dict[str, Any]:
    fast_values = monitor_data.operational_sources(
        _read_sources(ROOT / "public_sources.txt"), "fast"
    )
    nightly_values = monitor_data.operational_sources(
        _read_sources(ROOT / "source_catalog.txt"), "nightly"
    )

    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for mode, values in (("fast", fast_values), ("nightly", nightly_values)):
        for source in values:
            key = source.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append((source, mode))

    health_root = _load_json(ROOT / "source_health.json", {"sources": {}})
    discovery_root = _load_json(ROOT / "discovery_state.json", {})
    stats_root = _load_json(ROOT / "source_stats.json", {"sources": {}})
    rating_root = _load_json(ROOT / "source_reputation.json", {"sources": {}})

    fast_health = health_root.get("sources", {})
    nightly_health = discovery_root.get("health_sources", {})
    discovery_sources = discovery_root.get("sources", {})
    merged_stats = _merge_stats(
        stats_root.get("sources", {}),
        discovery_root.get("stats_sources", {}),
    )
    metadata = monitor_data.flatten_partner_channels()

    rows: dict[str, dict[str, Any]] = {}
    unavailable = 0
    checked = 0
    available = 0
    not_checked = 0

    for source, mode in ordered:
        health = _find_casefold(fast_health if mode == "fast" else nightly_health, source)
        discovery = _find_casefold(discovery_sources, source)
        status, status_label, reason, was_checked, is_available = _status_detail(
            source, mode, health, discovery
        )
        if was_checked:
            checked += 1
        if is_available:
            available += 1
        elif status == "unavailable":
            unavailable += 1
        elif status == "not_checked":
            not_checked += 1

        info = metadata.get(source.casefold(), {})
        stats = merged_stats.get(source.casefold(), {})
        rating = _find_casefold(rating_root.get("sources", {}), source)
        last_checked = (
            health.get("last_checked_at")
            or discovery.get("checked_at")
            or health.get("last_success_at")
        )
        rows[source] = {
            "source": source,
            "title": str(info.get("entity") or source),
            "status": status,
            "status_label": status_label,
            "reason": reason,
            "reason_code": status,
            "checked": was_checked,
            "available": is_available,
            "last_checked_at": last_checked,
            "last_success_at": health.get("last_success_at"),
            "last_error": health.get("last_error") or discovery.get("error"),
            "checks": int(stats.get("checks", 0) or 0),
            "messages_scanned": int(stats.get("messages_scanned", 0) or 0),
            "wheel_posts": int(stats.get("wheel_posts", 0) or 0),
            "confirmed_wheels": int(rating.get("confirmed_wheels", 0) or 0),
            "inactive_wheels": int(rating.get("inactive_wheels", 0) or 0),
            "rating_score": int(rating.get("score", 0) or 0),
            "success_rate": float(rating.get("success_rate", 0) or 0),
            # Internal scheduling is retained for diagnostics but should not be
            # presented as a separate user-facing category.
            "internal_scan_mode": mode,
        }

    return {
        "version": 1,
        "updated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total_sources": len(rows),
            "checked_sources": checked,
            "available_sources": available,
            "unavailable_sources": unavailable,
            "not_checked_sources": not_checked,
        },
        "sources": rows,
    }


def save_snapshot(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    data = build_snapshot()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return data


def self_test() -> None:
    data = build_snapshot()
    assert "summary" in data and "sources" in data
    assert data["summary"]["total_sources"] == len(data["sources"])
    print("BB V.G. source registry self-test passed")


if __name__ == "__main__":
    self_test()
