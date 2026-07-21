from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import requests

_API_ROOT = "https://api.github.com"
_STATE_PATH = "notification_delivery_state.json"
_TIMEOUT = 12


def _configured() -> bool:
    return bool(
        os.getenv("GITHUB_TOKEN", "").strip()
        and os.getenv("GITHUB_REPOSITORY", "").strip()
    )


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN'].strip()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "BB-VG-notification-checkpoint",
    }


def _endpoint() -> str:
    return f"{_API_ROOT}/repos/{os.environ['GITHUB_REPOSITORY'].strip()}/contents/{_STATE_PATH}"


def _branch() -> str:
    return (
        os.getenv("GITHUB_BRANCH", "").strip()
        or os.getenv("GITHUB_REF_NAME", "").strip()
        or "main"
    )


def _remote_state() -> tuple[dict[str, Any], str]:
    response = requests.get(
        _endpoint(),
        headers=_headers(),
        params={"ref": _branch()},
        timeout=_TIMEOUT,
    )
    if response.status_code == 404:
        return {}, ""
    response.raise_for_status()
    payload = response.json()
    raw = base64.b64decode(str(payload.get("content") or "")).decode("utf-8")
    value = json.loads(raw)
    return (value if isinstance(value, dict) else {}), str(payload.get("sha") or "")


def checkpoint(integrity_module: Any) -> bool:
    """Merge the local delivery ledger into main before/after external delivery.

    This closes the crash window where Telegram already received a message but a
    cancelled GitHub runner had not yet pushed notification_delivery_state.json.
    """

    if not _configured():
        return True

    for attempt in range(1, 4):
        try:
            local = integrity_module.load_state()
            remote, sha = _remote_state()
            merged = integrity_module.merge_states(remote, local)
            encoded = base64.b64encode(
                (json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            ).decode("ascii")
            body: dict[str, Any] = {
                "message": "Checkpoint BB V.G. notification delivery [skip ci]",
                "content": encoded,
                "branch": _branch(),
            }
            if sha:
                body["sha"] = sha
            response = requests.put(
                _endpoint(),
                headers=_headers(),
                json=body,
                timeout=_TIMEOUT,
            )
            if response.status_code in {409, 422} and attempt < 3:
                time.sleep(0.4 * attempt)
                continue
            response.raise_for_status()
            integrity_module.save_state(merged)
            return True
        except Exception as exc:
            if attempt >= 3:
                print(
                    "WARNING remote notification checkpoint failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                return False
            time.sleep(0.4 * attempt)
    return False


def install(router_module: Any, integrity_module: Any) -> None:
    if getattr(router_module, "_bbvg_remote_notification_checkpoint_installed", False):
        return

    original_claim = router_module.claim_delivery
    original_complete = router_module.complete_delivery
    original_release = router_module.release_delivery

    def durable_claim(key: str) -> bool:
        claimed = bool(original_claim(key))
        if not claimed:
            return False
        # Persist the reservation before Telegram is called. A replacement runner
        # therefore cannot send the same event while this claim is alive.
        if not checkpoint(integrity_module):
            original_release(key)
            return False
        return True

    def durable_complete(key: str) -> None:
        original_complete(key)
        checkpoint(integrity_module)

    def durable_release(key: str) -> None:
        original_release(key)
        checkpoint(integrity_module)

    router_module.claim_delivery = durable_claim
    router_module.complete_delivery = durable_complete
    router_module.release_delivery = durable_release
    router_module._bbvg_remote_notification_checkpoint_installed = True
