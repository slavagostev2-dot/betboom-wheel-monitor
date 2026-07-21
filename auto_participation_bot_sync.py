from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import admin_action_queue
import monitor
import personal_wheel_voting
from bbvg.bot.storage import PrivateStateRuntime

UTC = timezone.utc
DEFAULT_RECOVERY_RESULT = Path("/tmp/bbvg-auto-participation-recovery.json")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def _load_recovery_result(path: Path) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in reversed(lines):
        try:
            value = json.loads(line.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return {}


def _event_token(item: dict[str, Any]) -> str:
    key = str(item.get("wheel_key") or "").casefold()
    try:
        action_id = int(item.get("action_id") or 0)
    except (TypeError, ValueError):
        action_id = 0
    if action_id > 0:
        return f"{key}#action:{action_id}:{item.get('server_start_at') or ''}"
    return f"{key}#seen:{item.get('message_date') or ''}"


def _sources_for_item(
    state: dict[str, Any],
    key: str,
    item: dict[str, Any],
    attempt: dict[str, Any] | None = None,
) -> list[str]:
    """Use exactly the same source set semantics as the manual «Участвую» button."""

    values: list[str] = []
    rows = state.get("wheel_publications", {}).get(key.casefold(), [])
    if isinstance(rows, list):
        values.extend(
            str(row.get("source") or "").strip().lstrip("@")
            for row in rows
            if isinstance(row, dict)
        )
    raw_sources = item.get("sources")
    if isinstance(raw_sources, list):
        values.extend(str(value).strip().lstrip("@") for value in raw_sources)
    values.append(str(item.get("source") or "").strip().lstrip("@"))
    if isinstance(attempt, dict):
        values.append(str(attempt.get("source") or "").strip().lstrip("@"))

    seen: set[str] = set()
    result: list[str] = []
    for source in values:
        folded = source.casefold()
        if source and folded not in seen:
            seen.add(folded)
            result.append(source)
    return result


def _participation_records(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = record.get("participating_wheels")
    if isinstance(raw, list):
        return {
            str(value).casefold(): {"wheel_key": str(value).casefold()}
            for value in raw
            if str(value).strip()
        }
    if not isinstance(raw, dict):
        return {}
    return {
        str(key).casefold(): dict(value) if isinstance(value, dict) else {}
        for key, value in raw.items()
        if str(key).strip()
    }


def _pending_candidates(
    state: dict[str, Any], recovery: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    events = state.setdefault("auto_participation_events", {})
    active = state.setdefault("active_wheels", {})
    result: dict[str, dict[str, Any]] = {}

    attempts = recovery.get("attempts") if isinstance(recovery.get("attempts"), list) else []
    for raw in attempts:
        if not isinstance(raw, dict) or not bool(raw.get("success")):
            continue
        if str(raw.get("status") or "") == "already_marked_participating":
            continue
        token = _event_token(raw)
        record = events.get(token)
        if not isinstance(record, dict) or record.get("bot_success_sync_completed_at"):
            continue
        record.setdefault("bot_success_sync_pending_at", _now())
        record["bot_success_sync_status"] = "pending"
        result[token] = {"attempt": dict(raw), "record": record}

    # Only retry events explicitly marked pending by this synchronizer.
    # Historical successful wheels never become retroactive success notifications.
    for token, record in list(events.items()):
        if not isinstance(record, dict):
            continue
        if not record.get("bot_success_sync_pending_at") or record.get("bot_success_sync_completed_at"):
            continue
        key = str(record.get("wheel_key") or "").casefold()
        item = active.get(key)
        if not key or not isinstance(item, dict):
            continue
        result.setdefault(
            str(token),
            {
                "attempt": {
                    **item,
                    "wheel_key": key,
                    "success": True,
                    "status": str(item.get("auto_participation_status") or "participated"),
                    "detail": "BetBoom подтвердил участие",
                },
                "record": record,
            },
        )
    return result


def _save_state(state: dict[str, Any]) -> None:
    monitor.save_state(state)


def _owner_context(
    storage: PrivateStateRuntime,
) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    access = storage.load_access(force=True)
    owner_id = str(access.get("owner_id") or "").strip()
    users = access.get("users") if isinstance(access.get("users"), dict) else {}
    owner = users.get(owner_id) if isinstance(users.get(owner_id), dict) else None
    if not owner_id or not isinstance(owner, dict):
        raise RuntimeError("В зашифрованном состоянии BB V.G. не найден владелец")
    chat_id = str(owner.get("chat_id") or owner_id).strip()
    if not chat_id:
        raise RuntimeError("У владельца BB V.G. отсутствует Telegram chat_id")
    return access, owner_id, chat_id, owner


def _queue_owner_vote(
    state: dict[str, Any],
    key: str,
    item: dict[str, Any],
    attempt: dict[str, Any],
    owner_id: str,
) -> tuple[str, str, list[str], int]:
    event_key = personal_wheel_voting.wheel_event_key(key, item)
    sources = _sources_for_item(state, key, item, attempt)
    if not sources:
        raise RuntimeError("Для автоматической отметки участия не найдены источники колеса")
    weight = 5
    payload = personal_wheel_voting.normalize_vote_payload(
        {
            "wheel_key": key,
            "event_key": event_key,
            "actor": personal_wheel_voting.actor_vote_token(owner_id),
            "role": "owner",
            "weight": weight,
            "sources": sources,
        }
    )
    command_id = admin_action_queue.enqueue_remote(
        "record_personal_vote",
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )
    return command_id, event_key, sources, weight


def _save_owner_mark(
    storage: PrivateStateRuntime,
    access: dict[str, Any],
    owner_id: str,
    event_key: str,
    key: str,
    item: dict[str, Any],
    command_id: str,
    weight: int,
) -> bool:
    users = access.setdefault("users", {})
    owner = users.get(owner_id)
    if not isinstance(owner, dict):
        raise RuntimeError("Профиль владельца исчез во время синхронизации")

    joined = _participation_records(owner)
    existing = joined.get(event_key)
    if isinstance(existing, dict) and existing:
        if not existing.get("vote_command_id") and command_id:
            existing["vote_command_id"] = command_id
            existing.setdefault("vote_weight", weight)
            owner["participating_wheels"] = dict(sorted(joined.items()))
            storage.access = access
            storage.access_loaded = True
            storage.save_access("Repair automatic owner participation vote command [skip ci]")
            return True
        return False

    for stored_key, stored in list(joined.items()):
        same_wheel = str(stored.get("wheel_key") or "").casefold() == key
        if same_wheel or stored_key.startswith(key + "#"):
            joined.pop(stored_key, None)

    joined[event_key] = {
        "wheel_key": key,
        "action_id": item.get("action_id"),
        "event_id": item.get("event_id"),
        "generation_id": item.get("generation_id"),
        "server_start_at": item.get("server_start_at"),
        "joined_at": _now(),
        "vote_weight": weight,
        "vote_command_id": command_id,
        "participation_source": "betboom_auto_participation",
    }
    owner["participating_wheels"] = dict(sorted(joined.items()))
    storage.access = access
    storage.access_loaded = True
    storage.save_access("Auto-mark owner participation after BetBoom confirmation [skip ci]")
    return True


def _dispatch_control_center_refresh() -> None:
    token = str(os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
    repository = str(os.getenv("GITHUB_REPOSITORY") or "").strip()
    branch = str(os.getenv("GITHUB_BRANCH") or "main").strip() or "main"
    if not token or not repository:
        raise RuntimeError("GITHUB_TOKEN and GITHUB_REPOSITORY are required for Control Center refresh")
    api = str(os.getenv("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
    response = requests.post(
        f"{api}/repos/{repository}/actions/workflows/admin-bot.yml/dispatches",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"ref": branch},
        timeout=max(5, int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))),
    )
    if response.status_code != 204:
        raise RuntimeError(f"Control Center refresh dispatch failed: HTTP {response.status_code}")


def _send_success_notification(
    chat_id: str,
    key: str,
    item: dict[str, Any],
    sources: list[str],
    weight: int,
    already_marked: bool,
) -> None:
    identifier = str(item.get("identifier") or key)
    url = str(item.get("url") or "").strip()
    source_text = ", ".join(f"@{source}" for source in sources[:8])
    if len(sources) > 8:
        source_text += f" и ещё {len(sources) - 8}"
    mark_line = (
        "✅ Личная отметка «Участвую» уже была поставлена — повторный голос не создаётся."
        if already_marked
        else "✅ Личная отметка «Участвую» в BB V.G. поставлена автоматически."
    )
    text = (
        "✅ <b>Автоучастие в колесе BetBoom подтверждено</b>\n\n"
        f"Колесо: <code>{identifier}</code>\n"
        "BetBoom подтвердил участие.\n"
        f"{mark_line}\n"
        f"🏆 Рейтинг: голос владельца — <b>{weight} очков</b> каждому уникальному источнику "
        "этого события; повторное начисление для того же события исключено."
    )
    if source_text:
        text += f"\n📡 Источники: {source_text}"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🎡 Открыть колесо", "url": url}]]
        }
    monitor.telegram_api("sendMessage", payload)


def sync_confirmed_participation(
    recovery_result_path: Path = DEFAULT_RECOVERY_RESULT,
) -> dict[str, Any]:
    recovery = _load_recovery_result(recovery_result_path)
    state = _load_json(monitor.STATE_PATH, {})
    candidates = _pending_candidates(state, recovery)
    _save_state(state)
    if not candidates:
        return {"processed": 0, "completed": 0, "failed": 0, "details": []}

    storage = PrivateStateRuntime()
    access, owner_id, chat_id, owner = _owner_context(storage)
    ready: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    failed = 0

    for token, bundle in candidates.items():
        attempt = bundle["attempt"]
        record = bundle["record"]
        key = str(attempt.get("wheel_key") or record.get("wheel_key") or "").casefold()
        item = state.get("active_wheels", {}).get(key)
        if not key or not isinstance(item, dict):
            record["bot_success_sync_status"] = "waiting_for_active_state"
            _save_state(state)
            failed += 1
            details.append({"wheel_key": key, "status": "waiting_for_active_state"})
            continue

        try:
            event_key = personal_wheel_voting.wheel_event_key(key, item)
            joined = _participation_records(owner)
            existing = joined.get(event_key) if isinstance(joined.get(event_key), dict) else {}
            already_marked = bool(existing)
            sources = _sources_for_item(state, key, item, attempt)
            if not sources:
                raise RuntimeError("Для автоматической отметки не найдены источники")
            weight = 5

            command_id = str(
                record.get("bot_success_vote_command_id")
                or existing.get("vote_command_id")
                or ""
            )
            if not command_id:
                command_id, event_key, sources, weight = _queue_owner_vote(
                    state, key, item, attempt, owner_id
                )
            record["bot_success_vote_command_id"] = command_id
            record.setdefault("bot_success_vote_queued_at", _now())
            _save_state(state)

            if not record.get("bot_success_personal_mark_saved_at"):
                changed = _save_owner_mark(
                    storage,
                    access,
                    owner_id,
                    event_key,
                    key,
                    item,
                    command_id,
                    weight,
                )
                record["bot_success_personal_mark_saved_at"] = _now()
                record["bot_success_personal_mark_changed"] = bool(changed)
                _save_state(state)

            ready.append(
                {
                    "token": token,
                    "record": record,
                    "key": key,
                    "item": item,
                    "event_key": event_key,
                    "sources": sources,
                    "weight": weight,
                    "already_marked": already_marked,
                }
            )
        except Exception as exc:
            record["bot_success_sync_status"] = "retry_pending"
            record["bot_success_sync_error"] = f"{type(exc).__name__}: {exc}"[:300]
            _save_state(state)
            failed += 1
            details.append(
                {
                    "wheel_key": key,
                    "status": "retry_pending",
                    "error": record["bot_success_sync_error"],
                }
            )

    refresh_needed = [
        item for item in ready if not item["record"].get("bot_success_control_center_refresh_dispatched_at")
    ]
    if refresh_needed:
        try:
            _dispatch_control_center_refresh()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
            for item in refresh_needed:
                item["record"]["bot_success_sync_status"] = "retry_pending"
                item["record"]["bot_success_sync_error"] = error
            _save_state(state)
            failed += len(refresh_needed)
            details.extend(
                {
                    "wheel_key": item["key"],
                    "status": "retry_pending",
                    "error": error,
                }
                for item in refresh_needed
            )
            ready = [item for item in ready if item not in refresh_needed]
        else:
            dispatched_at = _now()
            for item in refresh_needed:
                item["record"]["bot_success_control_center_refresh_dispatched_at"] = dispatched_at
            _save_state(state)

    completed = 0
    for item in ready:
        record = item["record"]
        try:
            if not record.get("bot_success_notification_sent_at"):
                _send_success_notification(
                    chat_id,
                    item["key"],
                    item["item"],
                    item["sources"],
                    item["weight"],
                    item["already_marked"],
                )
                record["bot_success_notification_sent_at"] = _now()
                _save_state(state)
            record["bot_success_sync_status"] = "completed"
            record["bot_success_sync_completed_at"] = _now()
            record.pop("bot_success_sync_error", None)
            _save_state(state)
            completed += 1
            details.append(
                {
                    "wheel_key": item["key"],
                    "event_key": item["event_key"],
                    "status": "completed",
                    "rating_weight": item["weight"],
                    "sources": item["sources"],
                    "already_marked": item["already_marked"],
                }
            )
        except Exception as exc:
            record["bot_success_sync_status"] = "retry_pending"
            record["bot_success_sync_error"] = f"{type(exc).__name__}: {exc}"[:300]
            _save_state(state)
            failed += 1
            details.append(
                {
                    "wheel_key": item["key"],
                    "status": "retry_pending",
                    "error": record["bot_success_sync_error"],
                }
            )

    return {
        "processed": len(candidates),
        "completed": completed,
        "failed": failed,
        "details": details,
    }


def self_test() -> None:
    state = {
        "wheel_publications": {
            "lent": [
                {"source": "first"},
                {"source": "second"},
                {"source": "first"},
            ]
        },
        "active_wheels": {
            "lent": {
                "identifier": "lent",
                "source": "first",
                "action_id": 123,
                "server_start_at": "2026-07-21T12:00:00+00:00",
            }
        },
        "auto_participation_events": {
            "lent#action:123:2026-07-21T12:00:00+00:00": {
                "wheel_key": "lent",
                "status": "participated",
            }
        },
    }
    recovery = {
        "attempts": [
            {
                "wheel_key": "lent",
                "source": "second",
                "action_id": 123,
                "server_start_at": "2026-07-21T12:00:00+00:00",
                "success": True,
                "status": "participated",
            }
        ]
    }
    candidates = _pending_candidates(state, recovery)
    token = "lent#action:123:2026-07-21T12:00:00+00:00"
    assert token in candidates
    assert state["auto_participation_events"][token]["bot_success_sync_status"] == "pending"
    assert _sources_for_item(
        state,
        "lent",
        state["active_wheels"]["lent"],
        recovery["attempts"][0],
    ) == ["first", "second"]
    assert personal_wheel_voting.wheel_event_key(
        "lent", state["active_wheels"]["lent"]
    ) == "lent#action:123"
    print("auto participation bot sync self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-result", default=str(DEFAULT_RECOVERY_RESULT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = sync_confirmed_participation(Path(args.recovery_result))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if int(result.get("failed", 0) or 0) > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
