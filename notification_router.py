from __future__ import annotations

import copy
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

ACCESS_PATH = Path(__file__).resolve().parent / "bot_access.json"
UTC = timezone.utc
WHEEL_ID_RE = re.compile(r"Идентификатор:\s*<code>([^<]+)</code>", re.IGNORECASE)
WHEEL_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?betboom\.ru/freestream/([A-Za-z0-9._~-]+)",
    re.IGNORECASE,
)

DEFAULT_SETTINGS = {
    "wheel_notifications": True,
    "service_notifications": True,
    "daily_reports": True,
    "weekly_reports": True,
}


def load_config() -> tuple[dict[str, Any], bool]:
    try:
        value = json.loads(ACCESS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}, False
    return (value if isinstance(value, dict) else {}), True


def classify(text: str) -> str:
    lowered = text.casefold()
    if "ежедневный отчёт" in lowered:
        return "daily_reports"
    if "колёса не обнаружены" in lowered or "без колёс" in lowered and text.lstrip().startswith("📭"):
        return "weekly_reports"
    if text.lstrip().startswith(("🤖", "⚠️", "✅ <b>Ручная проверка", "🩺")):
        return "service_notifications"
    return "wheel_notifications"


def enabled_for(config: dict[str, Any], category: str) -> bool:
    settings = dict(DEFAULT_SETTINGS)
    raw = config.get("settings")
    if isinstance(raw, dict):
        for key in settings:
            if key in raw:
                settings[key] = bool(raw[key])
    return bool(settings.get(category, True))


def recipients(config: dict[str, Any], config_exists: bool) -> list[str]:
    values = config.get("notification_recipients") if isinstance(config, dict) else None
    if isinstance(values, list):
        result = sorted({str(value) for value in values if str(value)})
        if result or config.get("owner_id"):
            return result
    fallback = str(os.getenv("BOT_CHAT_ID", "")).strip()
    if fallback and (not config_exists or not config.get("owner_id")):
        return [fallback]
    return []


def wheel_key_from_message(text: str, url: str | None, reply_markup: dict | None) -> str:
    match = WHEEL_ID_RE.search(text or "")
    if match:
        return html.unescape(match.group(1)).strip().casefold()
    for candidate in (url or "", text or ""):
        match = WHEEL_URL_RE.search(candidate)
        if match:
            return unquote(match.group(1)).strip().casefold()
    if isinstance(reply_markup, dict):
        for row in reply_markup.get("inline_keyboard", []):
            if not isinstance(row, list):
                continue
            for button in row:
                if not isinstance(button, dict):
                    continue
                callback = str(button.get("callback_data") or "")
                if callback.startswith(("bb:x:", "bb:t:", "wheel:inactive:", "wheel:time:")):
                    return callback.split(":", 2)[2].casefold()
                button_url = str(button.get("url") or "")
                match = WHEEL_URL_RE.search(button_url)
                if match:
                    return unquote(match.group(1)).strip().casefold()
    return ""


def user_for_chat(config: dict[str, Any], chat_id: str) -> tuple[str, dict[str, Any]]:
    for user_id, record in config.get("users", {}).items():
        if not isinstance(record, dict):
            continue
        if str(record.get("chat_id") or user_id) == str(chat_id):
            return str(user_id), record
    return "", {}


def is_admin_chat(config: dict[str, Any], chat_id: str) -> bool:
    user_id, _ = user_for_chat(config, chat_id)
    return bool(
        user_id
        and user_id
        in {
            str(config.get("owner_id") or ""),
            *{str(value) for value in config.get("admins", [])},
        }
    )


def hidden_for_chat(config: dict[str, Any], chat_id: str, wheel_key: str) -> bool:
    if not wheel_key:
        return False
    _, record = user_for_chat(config, chat_id)
    raw = record.get("hidden_wheels") if isinstance(record, dict) else None
    if isinstance(raw, list):
        return wheel_key in {str(value).casefold() for value in raw}
    if not isinstance(raw, dict):
        return False
    value = raw.get(wheel_key)
    if value is None:
        return False
    if not isinstance(value, dict):
        return True
    expires_raw = value.get("expires_at")
    if not isinstance(expires_raw, str) or not expires_raw:
        return True
    try:
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires.astimezone(UTC) > datetime.now(UTC)


def markup_for_chat(reply_markup: dict | None, *, admin: bool) -> dict | None:
    if not isinstance(reply_markup, dict):
        return reply_markup
    result = copy.deepcopy(reply_markup)
    rows: list[list[dict[str, Any]]] = []
    for row in result.get("inline_keyboard", []):
        if not isinstance(row, list):
            continue
        filtered: list[dict[str, Any]] = []
        for button in row:
            if not isinstance(button, dict):
                continue
            callback = str(button.get("callback_data") or "")
            if not admin and callback.startswith(("bb:t:", "wheel:time:")):
                continue
            filtered.append(button)
        if filtered:
            rows.append(filtered)
    result["inline_keyboard"] = rows
    return result


def install(monitor_module: Any) -> None:
    def routed_send_message(
        text: str,
        url: str | None = None,
        reply_markup: dict | None = None,
    ) -> dict:
        config, exists = load_config()
        category = classify(text)
        if not enabled_for(config, category):
            print(f"Notification suppressed by setting: {category}")
            return {"ok": True, "result": {"suppressed": True, "category": category}}

        targets = recipients(config, exists)
        if not targets:
            print(f"Notification has no recipients: {category}")
            return {"ok": True, "result": {"suppressed": True, "category": category}}

        key = wheel_key_from_message(text, url, reply_markup)
        result: dict = {"ok": True, "result": {"sent": 0}}
        errors: list[str] = []
        sent = 0
        skipped = 0
        for chat_id in targets:
            if category == "wheel_notifications" and hidden_for_chat(config, chat_id, key):
                skipped += 1
                print(f"Wheel {key} hidden for notification target {chat_id}")
                continue
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            target_markup = markup_for_chat(
                reply_markup,
                admin=is_admin_chat(config, chat_id),
            )
            if target_markup is not None:
                payload["reply_markup"] = target_markup
            elif url:
                payload["reply_markup"] = {
                    "inline_keyboard": [[{"text": "Открыть колесо", "url": url}]]
                }
            try:
                response = monitor_module.telegram_api("sendMessage", payload)
                result = response
                sent += 1
                if isinstance(result.get("result"), dict):
                    result["result"]["routed_to"] = chat_id
            except Exception as exc:
                errors.append(f"{chat_id}:{type(exc).__name__}")
                print(f"WARNING notification target {chat_id}: {type(exc).__name__}: {exc}")
        if errors and len(errors) == len(targets) - skipped:
            raise RuntimeError("All notification targets failed: " + ", ".join(errors))
        if not isinstance(result.get("result"), dict):
            result["result"] = {}
        result["result"]["sent"] = sent
        result["result"]["hidden_skipped"] = skipped
        return result

    monitor_module.send_message = routed_send_message


def self_test() -> None:
    assert classify("📊 Ежедневный отчёт BB V.G.") == "daily_reports"
    assert classify("📭 За 7 дней колёса не обнаружены") == "weekly_reports"
    assert classify("🤖 BB V.G. работает") == "service_notifications"
    assert classify("🎡 Новое колесо") == "wheel_notifications"
    assert wheel_key_from_message("Идентификатор: <code>ZonerTG4</code>", None, None) == "zonertg4"
    user_markup = markup_for_chat(
        {"inline_keyboard": [[{"text": "Время", "callback_data": "bb:t:test"}, {"text": "Неактивное", "callback_data": "bb:x:test"}]]},
        admin=False,
    )
    assert "bb:t:test" not in str(user_markup) and "bb:x:test" in str(user_markup)
    print("BB V.G. notification router self-test passed")


if __name__ == "__main__":
    self_test()
