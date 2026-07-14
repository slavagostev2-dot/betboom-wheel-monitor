from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

import bot_private_state
from migrate_private_state import latest_matching

UTC = timezone.utc


def _default_access() -> dict[str, Any]:
    return {
        "version": 3,
        "owner_id": "",
        "admins": [],
        "users": {},
        "blocked_users": [],
        "notification_recipients": [],
        "settings": {
            "public_panel": True,
            "notifications": True,
            "monitor_interval_minutes": 5,
        },
    }


def _ensure_owner(access: dict[str, Any]) -> dict[str, Any]:
    result = _default_access()
    result.update(access if isinstance(access, dict) else {})
    result["admins"] = [str(value) for value in result.get("admins", []) if str(value)]
    result["blocked_users"] = [str(value) for value in result.get("blocked_users", []) if str(value)]
    result["notification_recipients"] = [
        str(value) for value in result.get("notification_recipients", []) if str(value)
    ]
    users = result.get("users")
    result["users"] = users if isinstance(users, dict) else {}
    settings = result.get("settings")
    merged_settings = _default_access()["settings"]
    if isinstance(settings, dict):
        merged_settings.update(settings)
    result["settings"] = merged_settings

    owner_id = str(
        result.get("owner_id")
        or os.getenv("ADMIN_USER_ID")
        or os.getenv("BOT_CHAT_ID")
        or ""
    ).strip()
    chat_id = str(os.getenv("BOT_CHAT_ID") or owner_id).strip()
    if owner_id:
        result["owner_id"] = owner_id
        now = datetime.now(UTC).isoformat()
        previous = result["users"].get(owner_id)
        previous = previous if isinstance(previous, dict) else {}
        result["users"][owner_id] = {
            **previous,
            "id": owner_id,
            "chat_id": str(previous.get("chat_id") or chat_id or owner_id),
            "username": str(previous.get("username") or ""),
            "first_name": str(previous.get("first_name") or "Администратор"),
            "last_name": str(previous.get("last_name") or ""),
            "first_seen_at": str(previous.get("first_seen_at") or now),
            "last_seen_at": str(previous.get("last_seen_at") or now),
            "notifications_enabled": True,
        }
        recipient = str(result["users"][owner_id].get("chat_id") or owner_id)
        recipients = {str(value) for value in result["notification_recipients"] if str(value)}
        recipients.add(recipient)
        result["notification_recipients"] = sorted(recipients)
    result["version"] = 3
    return result


def build_bundle() -> dict[str, Any]:
    legacy_access = latest_matching(
        "bot_access.json",
        lambda value: bool(value.get("users")) or bool(value.get("owner_id")),
        _default_access(),
    )
    source_requests = latest_matching(
        "source_requests.json",
        lambda value: bool(value.get("requests")),
        {"version": 1, "requests": {}},
    )
    return bot_private_state.default_bundle(
        _ensure_owner(legacy_access),
        source_requests,
    )


def migrate(force: bool = False) -> tuple[bool, int, int]:
    current = bot_private_state.load_file(
        access_default={},
        source_requests_default={"version": 1, "requests": {}},
    )
    current_access = current.get("access") if isinstance(current.get("access"), dict) else {}
    if not force and current_access.get("owner_id") and current_access.get("users"):
        users = len(current_access.get("users") or {})
        requests = len((current.get("source_requests") or {}).get("requests") or {})
        return False, users, requests

    bundle = build_bundle()
    bot_private_state.save_file(bundle)
    access = bundle.get("access") if isinstance(bundle.get("access"), dict) else {}
    requests_state = (
        bundle.get("source_requests")
        if isinstance(bundle.get("source_requests"), dict)
        else {}
    )
    return True, len(access.get("users") or {}), len(requests_state.get("requests") or {})


def self_test() -> None:
    sample = bot_private_state.default_bundle(
        _ensure_owner({"users": {}}),
        {"version": 1, "requests": {}},
    )
    encoded = bot_private_state.seal(sample, "test-secret")
    decoded = bot_private_state.unseal(encoded, "test-secret")
    assert decoded == sample
    assert decoded["access"]["settings"]["public_panel"] is True
    print("BB V.G. bot state migration self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.check:
        self_test()
        return 0
    changed, users, requests = migrate(force=args.force)
    print(
        "Bot private state migration completed: "
        f"changed={'yes' if changed else 'no'}, users={users}, source_requests={requests}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
