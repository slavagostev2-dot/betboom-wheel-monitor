from __future__ import annotations

import html
from typing import Any, Callable


REMINDER_MARKERS = (
    "напоминание о колесе betboom",
    "последний шанс войти в колесо betboom",
    "вы ещё не отметили участие",
    "вы еще не отметили участие",
)
_GLOBAL_PARTICIPATING: set[str] = set()


def set_global_participating(wheel_key: str, participating: bool) -> None:
    normalized = str(wheel_key or "").casefold()
    if not normalized:
        return
    if participating:
        _GLOBAL_PARTICIPATING.add(normalized)
    else:
        _GLOBAL_PARTICIPATING.discard(normalized)


def participating_for_chat(config: dict[str, Any], chat_id: str, wheel_key: str) -> bool:
    if not wheel_key:
        return False
    users = config.get("users") if isinstance(config.get("users"), dict) else {}
    record: dict[str, Any] = {}
    for user_id, raw in users.items():
        if not isinstance(raw, dict):
            continue
        if str(raw.get("chat_id") or user_id) == str(chat_id):
            record = raw
            break
    raw = record.get("participating_wheels")
    if isinstance(raw, list):
        return wheel_key.casefold() in {str(value).casefold() for value in raw}
    if isinstance(raw, dict):
        return wheel_key.casefold() in {str(value).casefold() for value in raw}
    return False


def install(monitor_module: Any, router_module: Any) -> None:
    """Filter reminder deliveries by each recipient's own participation state."""

    if getattr(monitor_module, "_bbvg_personal_reminder_filter_installed", False):
        return
    original_api: Callable = monitor_module.telegram_api

    def telegram_api_filtered(method: str, payload: dict) -> dict:
        if method == "sendMessage" and isinstance(payload, dict):
            text = html.unescape(str(payload.get("text") or "")).casefold()
            if any(marker in text for marker in REMINDER_MARKERS):
                config, _ = router_module.load_config()
                key = router_module.wheel_key_from_message(
                    str(payload.get("text") or ""),
                    None,
                    payload.get("reply_markup")
                    if isinstance(payload.get("reply_markup"), dict)
                    else None,
                )
                chat_id = str(payload.get("chat_id") or "")
                personal = participating_for_chat(config, chat_id, key)
                global_admin = (
                    key.casefold() in _GLOBAL_PARTICIPATING
                    and router_module.is_admin_chat(config, chat_id)
                )
                if personal or global_admin:
                    return {
                        "ok": True,
                        "result": {
                            "suppressed": True,
                            "reason": "participation_already_marked",
                            "chat_id": chat_id,
                            "wheel_key": key,
                        },
                    }
        return original_api(method, payload)

    monitor_module.telegram_api = telegram_api_filtered
    monitor_module._bbvg_personal_reminder_filter_installed = True


def self_test() -> None:
    config = {
        "owner_id": "1",
        "admins": [],
        "users": {
            "1": {"chat_id": "10", "participating_wheels": {}},
            "2": {
                "chat_id": "20",
                "participating_wheels": {"wheel-a": {"joined_at": "now"}},
            },
            "3": {"chat_id": "30", "participating_wheels": {}},
        },
    }
    assert participating_for_chat(config, "20", "wheel-a")
    assert not participating_for_chat(config, "30", "wheel-a")
    assert not participating_for_chat(config, "20", "wheel-b")
    set_global_participating("wheel-a", True)
    assert "wheel-a" in _GLOBAL_PARTICIPATING
    set_global_participating("wheel-a", False)
    assert "wheel-a" not in _GLOBAL_PARTICIPATING
    print("personal reminder filter self-test passed")


if __name__ == "__main__":
    self_test()
