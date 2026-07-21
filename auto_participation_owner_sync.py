from __future__ import annotations

import html
import threading
from datetime import datetime, timezone
from typing import Any

import personal_wheel_voting

UTC = timezone.utc
SYNC_INTERVAL_SECONDS = 20
MAX_COMPLETED_EVENTS = 500


def pending_events(state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return only auto-participation successes explicitly queued by the workflow."""

    events = state.get("auto_participation_events")
    if not isinstance(events, dict):
        return []
    result: list[tuple[str, dict[str, Any]]] = []
    for token, raw in events.items():
        if not isinstance(raw, dict):
            continue
        if not raw.get("bot_success_pending_at"):
            continue
        if str(raw.get("status") or "") != "participated":
            continue
        result.append((str(token), raw))
    result.sort(key=lambda item: str(item[1].get("bot_success_pending_at") or ""))
    return result


def _completion_records(owner: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = owner.get("auto_participation_success_events")
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): dict(value) if isinstance(value, dict) else {}
        for key, value in raw.items()
        if str(key)
    }


def _save_completion(
    panel: Any,
    owner_id: str,
    event_key: str,
    payload: dict[str, Any],
) -> None:
    access = panel.load_access(force=True)
    users = access.get("users") if isinstance(access.get("users"), dict) else {}
    owner = users.get(owner_id) if isinstance(users.get(owner_id), dict) else None
    if not isinstance(owner, dict):
        raise RuntimeError("Профиль владельца BB V.G. не найден при фиксации автоучастия")
    completed = _completion_records(owner)
    completed[event_key] = dict(payload)
    if len(completed) > MAX_COMPLETED_EVENTS:
        completed = dict(list(completed.items())[-MAX_COMPLETED_EVENTS:])
    owner["auto_participation_success_events"] = completed
    panel.access = access
    panel.access_loaded = True
    panel.save_access("Record automatic participation success for owner [skip ci]")


def _success_message(
    key: str,
    item: dict[str, Any],
    sources: list[str],
    weight: int,
    changed: bool,
) -> tuple[str, dict[str, Any] | None]:
    identifier = html.escape(str(item.get("identifier") or key))
    source_text = ", ".join(f"@{html.escape(source)}" for source in sources[:8])
    if len(sources) > 8:
        source_text += f" и ещё {len(sources) - 8}"
    mark_text = (
        "✅ Отметка «Участвую» в BB V.G. поставлена автоматически."
        if changed
        else "✅ Отметка «Участвую» уже была поставлена ранее — повторный голос не создавался."
    )
    text = (
        "✅ <b>Автоучастие в колесе BetBoom подтверждено</b>\n\n"
        f"Колесо: <code>{identifier}</code>\n"
        "BetBoom подтвердил участие.\n"
        f"{mark_text}\n"
        f"🏆 Рейтинг: применён штатный голос владельца — <b>{weight} очков</b> "
        "каждому уникальному источнику этого события. Повторное начисление для того же события исключено."
    )
    if source_text:
        text += f"\n📡 Источники: {source_text}"
    url = str(item.get("url") or "").strip()
    markup = (
        {"inline_keyboard": [[{"text": "🎡 Открыть колесо", "url": url}]]}
        if url
        else None
    )
    return text, markup


def sync_once(panel: Any) -> dict[str, int]:
    """Apply confirmed BetBoom participation through the normal personal-vote path."""

    snap = panel.snapshot()
    state = snap.state if isinstance(getattr(snap, "state", None), dict) else {}
    candidates = pending_events(state)
    if not candidates:
        return {"pending": 0, "completed": 0, "failed": 0}

    access = panel.load_access(force=True)
    owner_id = str(access.get("owner_id") or "").strip()
    users = access.get("users") if isinstance(access.get("users"), dict) else {}
    owner = users.get(owner_id) if isinstance(users.get(owner_id), dict) else None
    if not owner_id or not isinstance(owner, dict):
        raise RuntimeError("В зашифрованном состоянии BB V.G. не найден владелец")
    owner_chat_id = str(owner.get("chat_id") or owner_id).strip()
    if not owner_chat_id:
        raise RuntimeError("У владельца BB V.G. отсутствует Telegram chat_id")
    completed_records = _completion_records(owner)

    active = state.get("active_wheels") if isinstance(state.get("active_wheels"), dict) else {}
    completed_count = 0
    failed_count = 0
    original_context = (
        getattr(panel, "current_chat_id", None),
        getattr(panel, "current_user_id", None),
        getattr(panel, "current_role", "guest"),
    )

    for token, record in candidates:
        key = str(record.get("wheel_key") or "").casefold()
        item = active.get(key)
        if not key or not isinstance(item, dict):
            failed_count += 1
            continue
        event_key = personal_wheel_voting.wheel_event_key(key, item)
        previous = completed_records.get(event_key)
        if isinstance(previous, dict) and previous.get("notified_at"):
            continue

        try:
            panel.set_context(owner_chat_id, owner_id)
            result = panel.mark_personal_participation(key)
            changed = bool(result.get("changed")) if isinstance(result, dict) else False
            try:
                weight = int(result.get("weight", 5)) if isinstance(result, dict) else 5
            except (TypeError, ValueError):
                weight = 5
            sources = panel._sources_for_item(snap, key, item)
            text, markup = _success_message(key, item, sources, weight, changed)
            panel.send(text, reply_markup=markup, chat_id=owner_chat_id)
            now_text = datetime.now(UTC).isoformat()
            _save_completion(
                panel,
                owner_id,
                event_key,
                {
                    "wheel_key": key,
                    "source_event_token": token,
                    "notified_at": now_text,
                    "rating_weight": weight,
                    "vote_command_id": (
                        str(result.get("vote_command_id") or "")
                        if isinstance(result, dict)
                        else ""
                    ),
                },
            )
            completed_records[event_key] = {"notified_at": now_text}
            completed_count += 1
        except Exception as exc:
            failed_count += 1
            print(
                "WARNING auto participation owner sync: "
                f"wheel={key} {type(exc).__name__}: {exc}"
            )
        finally:
            panel.current_chat_id, panel.current_user_id, panel.current_role = original_context

    return {
        "pending": len(candidates),
        "completed": completed_count,
        "failed": failed_count,
    }


def _sync_loop(panel: Any) -> None:
    # Let the normal run() load access/setup Telegram and start its snapshot refresh first.
    if panel.stop_refresh.wait(5):
        return
    while not panel.stop_refresh.is_set():
        try:
            result = sync_once(panel)
            if result.get("completed"):
                print(
                    "Auto participation owner sync completed: "
                    f"{result['completed']} event(s)"
                )
        except Exception as exc:
            print(f"WARNING auto participation owner sync loop: {type(exc).__name__}: {exc}")
        if panel.stop_refresh.wait(SYNC_INTERVAL_SECONDS):
            return


def install(panel_class: type[Any]) -> None:
    if getattr(panel_class, "_bbvg_auto_participation_owner_sync_installed", False):
        return
    original_run = panel_class.run

    def run_with_auto_participation_owner_sync(self: Any) -> int:
        thread = threading.Thread(
            target=_sync_loop,
            args=(self,),
            name="auto-participation-owner-sync",
            daemon=True,
        )
        thread.start()
        return original_run(self)

    panel_class.run = run_with_auto_participation_owner_sync
    panel_class._bbvg_auto_participation_owner_sync_installed = True


def self_test() -> None:
    state = {
        "auto_participation_events": {
            "lent#action:952:2026-07-21T14:01:28.861000+00:00": {
                "wheel_key": "lent",
                "status": "participated",
                "bot_success_pending_at": "2026-07-21T14:02:36+00:00",
            },
            "old#action:1:": {
                "wheel_key": "old",
                "status": "participated",
            },
            "failed#action:2:": {
                "wheel_key": "failed",
                "status": "button_not_found",
                "bot_success_pending_at": "2026-07-21T14:00:00+00:00",
            },
        }
    }
    values = pending_events(state)
    assert [token for token, _ in values] == [
        "lent#action:952:2026-07-21T14:01:28.861000+00:00"
    ]
    print("auto participation owner sync self-test passed")


if __name__ == "__main__":
    self_test()
