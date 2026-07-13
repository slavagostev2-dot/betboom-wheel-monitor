from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RATING_PATH = ROOT / "source_reputation.json"
UTC = timezone.utc

WEIGHTS = {
    "admin_confirmed": 40,
    "admin_inactive": -45,
    "first_publication": 8,
    "valid_link": 5,
    "invalid_or_stale": -10,
    "time_correct": 8,
    "time_wrong": -6,
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def clean_source(value: object) -> str:
    return str(value or "").strip().lstrip("@")


def clean_key(value: object) -> str:
    return str(value or "").strip().casefold()


def default_data() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": None,
        "weights": dict(WEIGHTS),
        "wheels": {},
        "sources": {},
        "ranking": [],
    }


def load(path: Path = RATING_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        value = default_data()
    if not isinstance(value, dict):
        value = default_data()
    value.setdefault("version", 1)
    value.setdefault("weights", dict(WEIGHTS))
    value.setdefault("wheels", {})
    value.setdefault("sources", {})
    value.setdefault("ranking", [])
    return value


def save(data: dict[str, Any], path: Path = RATING_PATH) -> None:
    rebuild(data)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _source_entry(data: dict[str, Any], source: str) -> dict[str, Any]:
    sources = data.setdefault("sources", {})
    key = clean_source(source)
    entry = sources.setdefault(
        key,
        {
            "events": [],
            "automatic": {},
        },
    )
    entry.setdefault("events", [])
    entry.setdefault("automatic", {})
    return entry


def _event_exists(entry: dict[str, Any], event_id: str) -> bool:
    return any(
        isinstance(item, dict) and str(item.get("id") or "") == event_id
        for item in entry.get("events", [])
    )


def add_event(
    data: dict[str, Any],
    source: str,
    *,
    event_id: str,
    wheel_key: str,
    signal: str,
    delta: int,
    reason: str,
    at: str | None = None,
    actor: str = "",
    metadata: dict[str, Any] | None = None,
) -> bool:
    source = clean_source(source)
    if not source or not event_id:
        return False
    entry = _source_entry(data, source)
    if _event_exists(entry, event_id):
        return False
    event = {
        "id": event_id,
        "wheel_key": clean_key(wheel_key),
        "signal": signal,
        "delta": int(delta),
        "reason": str(reason)[:500],
        "at": at or now_iso(),
    }
    if actor:
        event["actor"] = str(actor)
    if metadata:
        event["metadata"] = metadata
    entry["events"].append(event)
    if len(entry["events"]) > 1000:
        entry["events"] = entry["events"][-1000:]
    return True


def record_publication(
    data: dict[str, Any],
    *,
    source: str,
    message_id: int,
    published_at: str,
    message_url: str,
    wheel_url: str,
    wheel_key: str,
    inferred_deadline: str | None = None,
    detected_at: str | None = None,
) -> bool:
    source = clean_source(source)
    key = clean_key(wheel_key)
    if not source or not key:
        return False
    wheels = data.setdefault("wheels", {})
    wheel = wheels.setdefault(
        key,
        {
            "wheel_key": key,
            "url": str(wheel_url or ""),
            "publications": [],
            "admin_verdict": None,
            "verdict_revision": 0,
        },
    )
    wheel.setdefault("publications", [])
    marker = f"{source.casefold()}:{int(message_id or 0)}"
    for item in wheel["publications"]:
        if isinstance(item, dict) and str(item.get("marker") or "") == marker:
            return False
    publication = {
        "marker": marker,
        "source": source,
        "message_id": int(message_id or 0),
        "published_at": str(published_at or ""),
        "message_url": str(message_url or ""),
        "wheel_url": str(wheel_url or ""),
        "detected_at": detected_at or now_iso(),
    }
    if inferred_deadline:
        publication["inferred_deadline"] = str(inferred_deadline)
    wheel["publications"].append(publication)
    wheel["publications"].sort(
        key=lambda item: (
            parse_dt(item.get("published_at")) or datetime.max.replace(tzinfo=UTC),
            str(item.get("source") or "").casefold(),
            int(item.get("message_id", 0) or 0),
        )
    )
    first = wheel["publications"][0] if wheel["publications"] else {}
    wheel["first_source"] = str(first.get("source") or "")
    wheel["first_published_at"] = str(first.get("published_at") or "")
    wheel["url"] = str(wheel.get("url") or wheel_url or "")
    data["updated_at"] = now_iso()
    return True


def _unique_publications_by_source(wheel: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in wheel.get("publications", []):
        if not isinstance(item, dict):
            continue
        source = clean_source(item.get("source"))
        if not source:
            continue
        current = result.get(source.casefold())
        item_time = parse_dt(item.get("published_at")) or datetime.max.replace(tzinfo=UTC)
        current_time = (
            parse_dt(current.get("published_at")) if isinstance(current, dict) else None
        ) or datetime.max.replace(tzinfo=UTC)
        if current is None or item_time < current_time:
            result[source.casefold()] = item
    return result


def _reverse_previous_verdict(data: dict[str, Any], wheel: dict[str, Any], actor: str) -> None:
    applied = wheel.get("applied_events")
    if not isinstance(applied, list):
        return
    revision = int(wheel.get("verdict_revision", 0) or 0)
    for item in applied:
        if not isinstance(item, dict):
            continue
        source = clean_source(item.get("source"))
        event_id = str(item.get("event_id") or "")
        delta = int(item.get("delta", 0) or 0)
        if not source or not event_id or not delta:
            continue
        add_event(
            data,
            source,
            event_id=f"reversal:{revision}:{event_id}",
            wheel_key=str(wheel.get("wheel_key") or ""),
            signal="verdict_reversal",
            delta=-delta,
            reason="Предыдущее административное решение заменено новым.",
            actor=actor,
        )


def apply_admin_verdict(
    data: dict[str, Any],
    *,
    wheel_key: str,
    verdict: str,
    actor: str,
    active_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = clean_key(wheel_key)
    verdict = str(verdict or "").strip().lower()
    if not key or verdict not in {"active", "inactive"}:
        raise ValueError("Некорректное колесо или решение администратора")

    wheels = data.setdefault("wheels", {})
    wheel = wheels.setdefault(
        key,
        {
            "wheel_key": key,
            "url": "",
            "publications": [],
            "admin_verdict": None,
            "verdict_revision": 0,
        },
    )
    wheel.setdefault("publications", [])

    if active_context:
        source = clean_source(active_context.get("source"))
        if source:
            record_publication(
                data,
                source=source,
                message_id=int(active_context.get("message_id", 0) or 0),
                published_at=str(active_context.get("message_date") or ""),
                message_url=str(active_context.get("message_url") or ""),
                wheel_url=str(active_context.get("url") or ""),
                wheel_key=key,
                inferred_deadline=str(active_context.get("deadline") or "") or None,
            )
        wheel["url"] = str(wheel.get("url") or active_context.get("url") or "")

    previous = str(wheel.get("admin_verdict") or "")
    if previous == verdict:
        return {
            "changed": False,
            "wheel_key": key,
            "verdict": verdict,
            "sources": len(_unique_publications_by_source(wheel)),
        }

    if previous in {"active", "inactive"}:
        _reverse_previous_verdict(data, wheel, actor)

    revision = int(wheel.get("verdict_revision", 0) or 0) + 1
    wheel["verdict_revision"] = revision
    wheel["admin_verdict"] = verdict
    wheel["verdict_at"] = now_iso()
    wheel["verdict_by"] = str(actor or "admin")
    applied_events: list[dict[str, Any]] = []

    publications = _unique_publications_by_source(wheel)
    first_source = str(wheel.get("first_source") or "").casefold()
    actual_deadline = parse_dt((active_context or {}).get("deadline"))

    for publication in publications.values():
        source = clean_source(publication.get("source"))
        base_signal = "admin_confirmed" if verdict == "active" else "admin_inactive"
        base_delta = WEIGHTS[base_signal]
        base_event = f"verdict:{revision}:{verdict}:{source.casefold()}:{key}"
        if add_event(
            data,
            source,
            event_id=base_event,
            wheel_key=key,
            signal=base_signal,
            delta=base_delta,
            reason=(
                "Администратор подтвердил колесо кнопкой «Участвую»."
                if verdict == "active"
                else "Администратор признал находку неактивной."
            ),
            actor=actor,
            metadata={"message_url": str(publication.get("message_url") or "")},
        ):
            applied_events.append(
                {"source": source, "event_id": base_event, "delta": base_delta}
            )

        if verdict == "active":
            valid_event = f"valid:{revision}:{source.casefold()}:{key}"
            if add_event(
                data,
                source,
                event_id=valid_event,
                wheel_key=key,
                signal="valid_link",
                delta=WEIGHTS["valid_link"],
                reason="Ссылка сохранила работоспособность до подтверждения администратором.",
                actor=actor,
            ):
                applied_events.append(
                    {
                        "source": source,
                        "event_id": valid_event,
                        "delta": WEIGHTS["valid_link"],
                    }
                )
            if source.casefold() == first_source:
                first_event = f"first:{revision}:{source.casefold()}:{key}"
                if add_event(
                    data,
                    source,
                    event_id=first_event,
                    wheel_key=key,
                    signal="first_publication",
                    delta=WEIGHTS["first_publication"],
                    reason="Источник опубликовал это колесо раньше остальных зафиксированных источников.",
                    actor=actor,
                ):
                    applied_events.append(
                        {
                            "source": source,
                            "event_id": first_event,
                            "delta": WEIGHTS["first_publication"],
                        }
                    )
            inferred = parse_dt(publication.get("inferred_deadline"))
            if inferred and actual_deadline:
                difference = abs((inferred - actual_deadline).total_seconds())
                signal = "time_correct" if difference <= 15 * 60 else "time_wrong"
                delta = WEIGHTS[signal]
                time_event = f"time:{revision}:{source.casefold()}:{key}"
                if add_event(
                    data,
                    source,
                    event_id=time_event,
                    wheel_key=key,
                    signal=signal,
                    delta=delta,
                    reason=(
                        "Указанное источником время совпало с подтверждённым временем."
                        if signal == "time_correct"
                        else "Указанное источником время заметно отличалось от подтверждённого."
                    ),
                    actor=actor,
                    metadata={"difference_seconds": int(difference)},
                ):
                    applied_events.append(
                        {"source": source, "event_id": time_event, "delta": delta}
                    )
        else:
            stale_event = f"stale:{revision}:{source.casefold()}:{key}"
            if add_event(
                data,
                source,
                event_id=stale_event,
                wheel_key=key,
                signal="invalid_or_stale",
                delta=WEIGHTS["invalid_or_stale"],
                reason="Ссылка или публикация оказалась ложной, устаревшей либо недействующей.",
                actor=actor,
            ):
                applied_events.append(
                    {
                        "source": source,
                        "event_id": stale_event,
                        "delta": WEIGHTS["invalid_or_stale"],
                    }
                )

    wheel["applied_events"] = applied_events
    data["updated_at"] = now_iso()
    rebuild(data)
    return {
        "changed": True,
        "wheel_key": key,
        "verdict": verdict,
        "sources": len(publications),
    }


def sync_automatic_stats(
    data: dict[str, Any],
    source_stats: dict[str, Any] | None,
    discovery_stats: dict[str, Any] | None = None,
) -> None:
    merged: dict[str, dict[str, int]] = {}
    for collection in (source_stats or {}, discovery_stats or {}):
        if not isinstance(collection, dict):
            continue
        for source, raw in collection.items():
            if not isinstance(raw, dict):
                continue
            target = merged.setdefault(clean_source(source), {})
            for key, value in raw.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    target[key] = target.get(key, 0) + value

    for source, raw in merged.items():
        if not source:
            continue
        wheels = int(raw.get("wheel_posts", 0) or 0)
        activations = int(raw.get("activation_sent", 0) or 0)
        errors = int(raw.get("errors", 0) or 0) + int(raw.get("inactive_checks", 0) or 0)
        success = activations / wheels if wheels else 0.0
        automatic_score = round(
            max(-20.0, min(20.0, success * 15.0 + min(wheels, 10) * 0.5 - min(errors, 10)))
        )
        entry = _source_entry(data, source)
        entry["automatic"] = {
            "score": automatic_score,
            "wheel_posts": wheels,
            "activation_sent": activations,
            "errors_or_inactive": errors,
            "confidence": round(success * 100, 1) if wheels else 0.0,
        }
    rebuild(data)


def rebuild(data: dict[str, Any]) -> None:
    ranking: list[dict[str, Any]] = []
    for source, entry in data.setdefault("sources", {}).items():
        if not isinstance(entry, dict):
            continue
        events = [item for item in entry.get("events", []) if isinstance(item, dict)]
        events.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
        entry["events"] = events[:1000] if len(events) > 1000 else events
        manual_score = sum(int(item.get("delta", 0) or 0) for item in events)
        automatic = entry.get("automatic") if isinstance(entry.get("automatic"), dict) else {}
        automatic_score = int(automatic.get("score", 0) or 0)
        confirmed: set[str] = set()
        inactive: set[str] = set()
        for wheel_key, wheel in data.get("wheels", {}).items():
            if not isinstance(wheel, dict):
                continue
            source_keys = {
                clean_source(item.get("source")).casefold()
                for item in wheel.get("publications", [])
                if isinstance(item, dict) and clean_source(item.get("source"))
            }
            if source.casefold() not in source_keys:
                continue
            verdict = str(wheel.get("admin_verdict") or "")
            if verdict == "active":
                confirmed.add(str(wheel_key))
            elif verdict == "inactive":
                inactive.add(str(wheel_key))
        total = len(confirmed) + len(inactive)
        success_rate = round(len(confirmed) * 100 / total, 1) if total else 0.0
        recent_cutoff = datetime.now(UTC).timestamp() - 7 * 86400
        trend = 0
        for item in events:
            stamp = parse_dt(item.get("at"))
            if stamp and stamp.timestamp() >= recent_cutoff:
                trend += int(item.get("delta", 0) or 0)
        entry.update(
            {
                "source": source,
                "manual_score": manual_score,
                "automatic_score": automatic_score,
                "score": manual_score + automatic_score,
                "confirmed_wheels": len(confirmed),
                "inactive_wheels": len(inactive),
                "success_rate": success_rate,
                "trend": trend,
                "last_event_at": str(events[0].get("at") or "") if events else None,
            }
        )
        ranking.append(
            {
                "source": source,
                "score": entry["score"],
                "confirmed_wheels": entry["confirmed_wheels"],
                "inactive_wheels": entry["inactive_wheels"],
                "success_rate": entry["success_rate"],
                "trend": entry["trend"],
            }
        )
    ranking.sort(
        key=lambda item: (
            -int(item.get("score", 0) or 0),
            -int(item.get("confirmed_wheels", 0) or 0),
            int(item.get("inactive_wheels", 0) or 0),
            str(item.get("source") or "").casefold(),
        )
    )
    for index, item in enumerate(ranking, 1):
        item["place"] = index
    data["ranking"] = ranking
    data["weights"] = dict(WEIGHTS)
    data["version"] = 1
    data["updated_at"] = data.get("updated_at") or now_iso()


def self_test() -> None:
    data = default_data()
    record_publication(
        data,
        source="alpha",
        message_id=1,
        published_at="2026-07-14T00:00:00+00:00",
        message_url="https://t.me/alpha/1",
        wheel_url="https://betboom.ru/freestream/test",
        wheel_key="test",
    )
    record_publication(
        data,
        source="beta",
        message_id=2,
        published_at="2026-07-14T00:01:00+00:00",
        message_url="https://t.me/beta/2",
        wheel_url="https://betboom.ru/freestream/test",
        wheel_key="test",
    )
    result = apply_admin_verdict(
        data,
        wheel_key="test",
        verdict="active",
        actor="1",
        active_context={"deadline": "2026-07-14T01:00:00+00:00"},
    )
    assert result["sources"] == 2
    assert data["sources"]["alpha"]["score"] > data["sources"]["beta"]["score"]
    again = apply_admin_verdict(
        data, wheel_key="test", verdict="active", actor="1"
    )
    assert not again["changed"]
    print("BB V.G. source reputation self-test passed")


if __name__ == "__main__":
    self_test()
