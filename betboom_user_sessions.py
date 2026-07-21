from __future__ import annotations

import base64
import copy
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote

import requests

import bot_private_state
import personal_wheel_voting

UTC = timezone.utc
STATE_PATH = bot_private_state.STATE_PATH.name


def _repo() -> str:
    value = str(os.getenv("GITHUB_REPOSITORY") or "").strip()
    if not value:
        raise RuntimeError("GITHUB_REPOSITORY is required")
    return value


def _token() -> str:
    value = str(os.getenv("GITHUB_TOKEN") or "").strip()
    if not value:
        raise RuntimeError("GITHUB_TOKEN is required")
    return value


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _contents_url() -> str:
    return f"https://api.github.com/repos/{_repo()}/contents/{quote(STATE_PATH, safe='/')}"


def load_remote_bundle() -> tuple[dict[str, Any], str]:
    response = requests.get(
        _contents_url(),
        params={"ref": "main"},
        headers=_headers(),
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    text = base64.b64decode(str(payload.get("content") or "")).decode("utf-8")
    bundle = bot_private_state.load_text(text, access_default={}, source_requests_default={})
    return bundle, str(payload.get("sha") or "")


def update_remote_bundle(
    mutator: Callable[[dict[str, Any]], bool],
    message: str,
    *,
    attempts: int = 4,
) -> bool:
    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            bundle, sha = load_remote_bundle()
            working = copy.deepcopy(bundle)
            changed = bool(mutator(working))
            if not changed:
                return False
            text = bot_private_state.seal(working)
            response = requests.put(
                _contents_url(),
                headers=_headers(),
                json={
                    "message": message,
                    "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                    "sha": sha,
                    "branch": "main",
                },
                timeout=30,
            )
            if response.status_code in {200, 201}:
                return True
            if response.status_code in {409, 422}:
                last_error = RuntimeError(f"GitHub state conflict: HTTP {response.status_code}")
                continue
            response.raise_for_status()
        except Exception as exc:
            last_error = exc
    raise RuntimeError("Unable to update encrypted BetBoom user state") from last_error


def actor_token(user_id: str) -> str:
    return personal_wheel_voting.actor_vote_token(str(user_id))


def _display_name(record: dict[str, Any], user_id: str) -> str:
    full = " ".join(
        value
        for value in (
            str(record.get("first_name") or "").strip(),
            str(record.get("last_name") or "").strip(),
        )
        if value
    )
    return full or str(record.get("username") or user_id)


def account_status(record: dict[str, Any]) -> str:
    account = record.get("betboom_account")
    if not isinstance(account, dict):
        return "not_connected"
    if str(account.get("status") or "") != "connected":
        return str(account.get("status") or "not_connected")
    if not isinstance(account.get("storage_state"), dict):
        return "not_connected"
    return "connected"


def enabled_accounts(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    access = bundle.get("access") if isinstance(bundle.get("access"), dict) else {}
    users = access.get("users") if isinstance(access.get("users"), dict) else {}
    result: list[dict[str, Any]] = []
    for user_id, raw in users.items():
        if not isinstance(raw, dict) or account_status(raw) != "connected":
            continue
        account = raw.get("betboom_account") or {}
        if not bool(account.get("auto_participation_enabled", True)):
            continue
        result.append(
            {
                "user_id": str(user_id),
                "chat_id": str(raw.get("chat_id") or user_id),
                "display_name": _display_name(raw, str(user_id)),
                "actor": actor_token(str(user_id)),
                "storage_state": copy.deepcopy(account.get("storage_state")),
                "participating_wheels": copy.deepcopy(raw.get("participating_wheels") or {}),
            }
        )
    return result


def _legacy_storage_state() -> dict[str, Any] | None:
    raw = str(os.getenv("BETBOOM_STORAGE_STATE_JSON") or "").strip()
    if not raw:
        raw = str(os.getenv("BETBOOM_STORAGE_STATE_JSON_PART1") or "") + str(
            os.getenv("BETBOOM_STORAGE_STATE_JSON_PART2") or ""
        )
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def migrate_legacy_owner_session() -> bool:
    storage_state = _legacy_storage_state()
    if storage_state is None:
        return False

    def mutate(bundle: dict[str, Any]) -> bool:
        access = bundle.get("access") if isinstance(bundle.get("access"), dict) else {}
        owner_id = str(access.get("owner_id") or "")
        users = access.get("users") if isinstance(access.get("users"), dict) else {}
        record = users.get(owner_id) if isinstance(users.get(owner_id), dict) else None
        if not owner_id or not isinstance(record, dict):
            return False
        if account_status(record) == "connected":
            return False
        record["betboom_account"] = {
            "status": "connected",
            "auto_participation_enabled": True,
            "storage_state": storage_state,
            "connected_at": datetime.now(UTC).isoformat(),
            "source": "legacy_github_secret_migration",
        }
        return True

    return update_remote_bundle(
        mutate,
        "Migrate owner BetBoom session to encrypted user state [skip ci]",
    )


def find_connection_request(bundle: dict[str, Any], request_id: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    access = bundle.get("access") if isinstance(bundle.get("access"), dict) else {}
    users = access.get("users") if isinstance(access.get("users"), dict) else {}
    for user_id, raw in users.items():
        if not isinstance(raw, dict):
            continue
        request = raw.get("betboom_connection")
        if isinstance(request, dict) and str(request.get("request_id") or "") == str(request_id):
            return str(user_id), raw, request
    raise LookupError("BetBoom connection request not found")


def set_connection_status(request_id: str, status: str, **fields: Any) -> bool:
    def mutate(bundle: dict[str, Any]) -> bool:
        _, _, request = find_connection_request(bundle, request_id)
        request["status"] = status
        request["updated_at"] = datetime.now(UTC).isoformat()
        for key, value in fields.items():
            if value is None:
                request.pop(key, None)
            else:
                request[key] = value
        return True

    return update_remote_bundle(
        mutate,
        f"Update BetBoom connection request {status} [skip ci]",
    )


def save_connected_session(request_id: str, storage_state: dict[str, Any]) -> tuple[str, str]:
    result: dict[str, str] = {}

    def mutate(bundle: dict[str, Any]) -> bool:
        user_id, record, request = find_connection_request(bundle, request_id)
        now = datetime.now(UTC).isoformat()
        record["betboom_account"] = {
            "status": "connected",
            "auto_participation_enabled": True,
            "storage_state": copy.deepcopy(storage_state),
            "connected_at": now,
            "last_verified_at": now,
            "source": "self_service_remote_browser",
        }
        request.update({"status": "completed", "completed_at": now})
        request.pop("error", None)
        result["user_id"] = user_id
        result["chat_id"] = str(record.get("chat_id") or user_id)
        return True

    update_remote_bundle(
        mutate,
        "Save self-service BetBoom session [skip ci]",
    )
    return result.get("user_id", ""), result.get("chat_id", "")


def mark_personal_participation(
    user_id: str,
    event_key: str,
    item: dict[str, Any],
    *,
    status: str,
) -> bool:
    normalized_event = str(event_key or "").casefold()

    def mutate(bundle: dict[str, Any]) -> bool:
        access = bundle.get("access") if isinstance(bundle.get("access"), dict) else {}
        users = access.get("users") if isinstance(access.get("users"), dict) else {}
        record = users.get(str(user_id)) if isinstance(users.get(str(user_id)), dict) else None
        if not isinstance(record, dict):
            return False
        joined = record.get("participating_wheels")
        joined = dict(joined) if isinstance(joined, dict) else {}
        if normalized_event in joined:
            return False
        joined[normalized_event] = {
            "wheel_key": str(item.get("_key") or item.get("identifier") or "").casefold(),
            "action_id": item.get("action_id"),
            "event_id": item.get("event_id"),
            "generation_id": item.get("generation_id"),
            "server_start_at": item.get("server_start_at"),
            "joined_at": datetime.now(UTC).isoformat(),
            "method": "betboom_auto",
            "participation_status": status,
        }
        record["participating_wheels"] = joined
        account = record.get("betboom_account")
        if isinstance(account, dict):
            account["last_verified_at"] = datetime.now(UTC).isoformat()
            account["last_error"] = ""
        return True

    return update_remote_bundle(
        mutate,
        "Save personal BetBoom auto participation [skip ci]",
    )


def record_account_error(user_id: str, detail: str) -> bool:
    def mutate(bundle: dict[str, Any]) -> bool:
        access = bundle.get("access") if isinstance(bundle.get("access"), dict) else {}
        users = access.get("users") if isinstance(access.get("users"), dict) else {}
        record = users.get(str(user_id)) if isinstance(users.get(str(user_id)), dict) else None
        if not isinstance(record, dict):
            return False
        account = record.get("betboom_account")
        if not isinstance(account, dict):
            return False
        account["last_error"] = str(detail or "")[:300]
        account["last_error_at"] = datetime.now(UTC).isoformat()
        return True

    return update_remote_bundle(
        mutate,
        "Record personal BetBoom session error [skip ci]",
    )


def self_test() -> None:
    sample = {
        "access": {
            "users": {
                "1": {
                    "chat_id": "10",
                    "first_name": "Test",
                    "betboom_account": {
                        "status": "connected",
                        "auto_participation_enabled": True,
                        "storage_state": {"cookies": []},
                    },
                }
            }
        }
    }
    rows = enabled_accounts(sample)
    assert len(rows) == 1
    assert rows[0]["chat_id"] == "10"
    assert account_status(sample["access"]["users"]["1"]) == "connected"
    print("betboom user sessions self-test passed")


if __name__ == "__main__":
    self_test()
