from __future__ import annotations

import re
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one marker, found {count}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{path}: regex marker not found: {pattern[:120]!r}")
    write(path, updated)


# 1. Add a third, independently owned BetBoom session for Telegram user xFLARXx.
replace_once(
    "betboom_account_participation.py",
    'DEFAULT_ALERT_USER = "Вячеслав"\n',
    'DEFAULT_ALERT_USER = "Вячеслав"\n'
    'XFLARXX_ACCOUNT_KEY = "xflarxx_primary"\n'
    'DEFAULT_XFLARXX_ACCOUNT_LABEL = "xFLARXx"\n'
    'DEFAULT_XFLARXX_ALERT_USER = "xFLARXx"\n',
)
replace_once(
    "betboom_account_participation.py",
    '''def alert_user() -> str:\n    return (\n        os.getenv("BETBOOM_ACCOUNT2_TELEGRAM_USER", DEFAULT_ALERT_USER).strip()\n        or DEFAULT_ALERT_USER\n    )\n\n\ndef _storage_state_raw() -> str:\n''',
    '''def alert_user() -> str:\n    return (\n        os.getenv("BETBOOM_ACCOUNT2_TELEGRAM_USER", DEFAULT_ALERT_USER).strip()\n        or DEFAULT_ALERT_USER\n    )\n\n\ndef xflarxx_account_label() -> str:\n    return (\n        os.getenv("BETBOOM_ACCOUNT3_LABEL", DEFAULT_XFLARXX_ACCOUNT_LABEL).strip()\n        or DEFAULT_XFLARXX_ACCOUNT_LABEL\n    )\n\n\ndef xflarxx_alert_user() -> str:\n    return (\n        os.getenv("BETBOOM_ACCOUNT3_TELEGRAM_USER", DEFAULT_XFLARXX_ALERT_USER).strip()\n        or DEFAULT_XFLARXX_ALERT_USER\n    )\n\n\ndef _storage_state_raw() -> str:\n''',
)
replace_once(
    "betboom_account_participation.py",
    '''def configured() -> bool:\n    return storage_state() is not None\n\n\ndef _parse_datetime(value: Any) -> datetime | None:\n''',
    '''def configured() -> bool:\n    return storage_state() is not None\n\n\ndef _xflarxx_storage_state_raw() -> str:\n    part5 = os.getenv("BETBOOM_STORAGE_STATE_JSON_PART5", "")\n    part6 = os.getenv("BETBOOM_STORAGE_STATE_JSON_PART6", "")\n    return part5 + part6 if part5 or part6 else ""\n\n\ndef xflarxx_storage_state() -> dict[str, Any] | None:\n    raw = _xflarxx_storage_state_raw()\n    if not raw:\n        return None\n    try:\n        value = json.loads(raw)\n    except json.JSONDecodeError:\n        return None\n    return value if isinstance(value, dict) else None\n\n\ndef xflarxx_configured() -> bool:\n    return xflarxx_storage_state() is not None\n\n\ndef _parse_datetime(value: Any) -> datetime | None:\n''',
)
replace_once(
    "betboom_account_participation.py",
    '''def _account_event_token(item: dict[str, Any], wheel_key: str = "") -> str:\n    return f"{_base_event_token(item, wheel_key)}#account:{ACCOUNT_KEY}"\n''',
    '''def _account_event_token(\n    item: dict[str, Any],\n    wheel_key: str = "",\n    account_key: str = ACCOUNT_KEY,\n) -> str:\n    return f"{_base_event_token(item, wheel_key)}#account:{account_key}"\n''',
)

xflarxx_runner = r'''

def run_xflarxx_account(
    recovery_result_path: Path = DEFAULT_RECOVERY_RESULT,
) -> dict[str, Any]:
    session = xflarxx_storage_state()
    if session is None:
        raise RuntimeError(
            "BetBoom-аккаунт xFLARXx не настроен: проверьте PART5/PART6"
        )

    state = _load_json(monitor.STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    events = state.setdefault("auto_participation_events", {})
    current = monitor.now_utc()
    attempted = 0
    succeeded = 0
    terminal_failed = 0
    deferred = 0
    skipped = 0

    for item in _candidate_rows(state, recovery_result_path):
        key = str(item.get("wheel_key") or item.get("identifier") or "").casefold()
        url = str(item.get("url") or "").strip()
        if not key or not url:
            continue
        token = _account_event_token(item, key, XFLARXX_ACCOUNT_KEY)
        previous = events.get(token)
        if not _should_attempt(previous, current):
            skipped += 1
            continue

        attempted += 1
        result = _participate_with_storage(url, session)
        record: dict[str, Any] = {
            "wheel_key": key,
            "event_token": _base_event_token(item, key),
            "account_key": XFLARXX_ACCOUNT_KEY,
            "account_label": xflarxx_account_label(),
            "alert_user": xflarxx_alert_user(),
            "status": str(result.status),
            "detail": str(result.detail)[:300],
            "attempted_at": current.isoformat(),
            "retry_allowed": False,
            "multi_account_version": 2,
        }

        if result.success:
            record["status"] = "participated"
            record["bot_success_pending_at"] = current.isoformat()
            record["bot_success_sync_status"] = "waiting_for_control_center"
            record["bot_success_sync_version"] = 1
            succeeded += 1
        elif str(result.status).casefold() in TERMINAL_FAILURE_STATUSES:
            record["bot_failure_pending_at"] = current.isoformat()
            record["bot_failure_sync_status"] = "waiting_for_control_center"
            record["bot_failure_sync_version"] = 1
            record["bot_failure_status"] = str(result.status)[:80]
            record["bot_failure_detail"] = str(result.detail)[:300]
            terminal_failed += 1
        else:
            record["retry_allowed"] = True
            record["retry_after_at"] = (
                current + timedelta(minutes=RETRY_DELAY_MINUTES)
            ).isoformat()
            record["user_alert_policy"] = "deferred_transient_failure"
            deferred += 1

        events[token] = record

    state["last_xflarxx_account_participation_at"] = current.isoformat()
    monitor.save_state(state)
    return {
        "account_key": XFLARXX_ACCOUNT_KEY,
        "account_label": xflarxx_account_label(),
        "alert_user": xflarxx_alert_user(),
        "attempted": attempted,
        "succeeded": succeeded,
        "terminal_failed": terminal_failed,
        "deferred": deferred,
        "skipped": skipped,
    }
'''
replace_once(
    "betboom_account_participation.py",
    "\n\ndef _normalized_names(user_id: str, record: dict[str, Any]) -> set[str]:\n",
    xflarxx_runner + "\n\ndef _normalized_names(user_id: str, record: dict[str, Any]) -> set[str]:\n",
)
replace_once(
    "betboom_account_participation.py",
    '''    result = run_second_account(args.recovery_result)\n    print(json.dumps(result, ensure_ascii=False, sort_keys=True))\n''',
    '''    results = [\n        run_second_account(args.recovery_result),\n        run_xflarxx_account(args.recovery_result),\n    ]\n    print(json.dumps({"accounts": results}, ensure_ascii=False, sort_keys=True))\n''',
)
replace_once(
    "betboom_account_participation.py",
    '''    item = {\n        "wheel_key": "wheel",\n''',
    '''    previous5 = os.environ.get("BETBOOM_STORAGE_STATE_JSON_PART5")\n    previous6 = os.environ.get("BETBOOM_STORAGE_STATE_JSON_PART6")\n    try:\n        raw = json.dumps({"cookies": [], "origins": []}, separators=(",", ":"))\n        middle = len(raw) // 2\n        os.environ["BETBOOM_STORAGE_STATE_JSON_PART5"] = raw[:middle]\n        os.environ["BETBOOM_STORAGE_STATE_JSON_PART6"] = raw[middle:]\n        assert xflarxx_configured()\n        assert xflarxx_storage_state() == {"cookies": [], "origins": []}\n    finally:\n        if previous5 is None:\n            os.environ.pop("BETBOOM_STORAGE_STATE_JSON_PART5", None)\n        else:\n            os.environ["BETBOOM_STORAGE_STATE_JSON_PART5"] = previous5\n        if previous6 is None:\n            os.environ.pop("BETBOOM_STORAGE_STATE_JSON_PART6", None)\n        else:\n            os.environ["BETBOOM_STORAGE_STATE_JSON_PART6"] = previous6\n\n    item = {\n        "wheel_key": "wheel",\n''',
)
replace_once(
    "betboom_account_participation.py",
    '''    assert _account_event_token(item).endswith("#account:vyacheslav_secondary")\n''',
    '''    assert _account_event_token(item).endswith("#account:vyacheslav_secondary")\n    assert _account_event_token(\n        item, account_key=XFLARXX_ACCOUNT_KEY\n    ).endswith("#account:xflarxx_primary")\n''',
)

# 2. Run PART5/PART6 in the normal serialized auto-participation workflow.
replace_once(
    ".github/workflows/auto-participation.yml",
    '''          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}\n          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}\n          BETBOOM_ACCOUNT2_LABEL: "Аккаунт 2"\n''',
    '''          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}\n          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}\n          BETBOOM_STORAGE_STATE_JSON_PART5: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART5 }}\n          BETBOOM_STORAGE_STATE_JSON_PART6: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART6 }}\n          BETBOOM_ACCOUNT2_LABEL: "Аккаунт 2"\n''',
)
replace_once(
    ".github/workflows/auto-participation.yml",
    '''           if not betboom_account_participation.configured():\n               raise SystemExit("Vyacheslav second BetBoom session PART3/PART4 is not configured")\n''',
    '''           if not betboom_account_participation.configured():\n               raise SystemExit("Vyacheslav second BetBoom session PART3/PART4 is not configured")\n           if not betboom_account_participation.xflarxx_configured():\n               raise SystemExit("xFLARXx BetBoom session PART5/PART6 is not configured")\n''',
)
replace_once(
    ".github/workflows/auto-participation.yml",
    '           print("Auto participation preflight OK for both BetBoom accounts")\n',
    '           print("Auto participation preflight OK for all configured BetBoom accounts")\n',
)
replace_once(
    ".github/workflows/auto-participation.yml",
    '      - name: Run second BetBoom account for Vyacheslav\n',
    '      - name: Run additional BetBoom accounts\n',
)
replace_once(
    ".github/workflows/auto-participation.yml",
    '''          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}\n          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}\n          BETBOOM_ACCOUNT2_LABEL: "Аккаунт 2"\n          BETBOOM_ACCOUNT2_TELEGRAM_USER: "Вячеслав"\n''',
    '''          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}\n          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}\n          BETBOOM_STORAGE_STATE_JSON_PART5: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART5 }}\n          BETBOOM_STORAGE_STATE_JSON_PART6: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART6 }}\n          BETBOOM_ACCOUNT2_LABEL: "Аккаунт 2"\n          BETBOOM_ACCOUNT2_TELEGRAM_USER: "Вячеслав"\n          BETBOOM_ACCOUNT3_LABEL: "xFLARXx"\n          BETBOOM_ACCOUNT3_TELEGRAM_USER: "xFLARXx"\n''',
)

# 3. Fix the TypeError in owner user details and deliver xFLARXx outcomes independently.
replace_once(
    "auto_participation_notifications.py",
    'import auto_participation_owner_sync\n',
    'import auto_participation_owner_sync\nimport betboom_account_participation\n',
)
replace_once(
    "auto_participation_notifications.py",
    'SECONDARY_ACCOUNT_LABEL = "Аккаунт 2"\n',
    'SECONDARY_ACCOUNT_LABEL = "Аккаунт 2"\nXFLARXX_ACCOUNT_KEY = "xflarxx_primary"\nXFLARXX_ACCOUNT_LABEL = "xFLARXx"\nXFLARXX_ALERT_USER = "xFLARXx"\n',
)
replace_once(
    "auto_participation_notifications.py",
    'AUTO_NOTIFICATION_DESCRIPTION = "Один общий итог по двум BetBoom-аккаунтам"\n',
    'AUTO_NOTIFICATION_DESCRIPTION = "Итоги автоматического участия в колёсах"\n',
)
replace_once(
    "auto_participation_notifications.py",
    '''    if key == SECONDARY_ACCOUNT_KEY:\n        return key, str(record.get("account_label") or SECONDARY_ACCOUNT_LABEL)\n    return PRIMARY_ACCOUNT_KEY, PRIMARY_ACCOUNT_LABEL\n''',
    '''    if key == SECONDARY_ACCOUNT_KEY:\n        return key, str(record.get("account_label") or SECONDARY_ACCOUNT_LABEL)\n    if key == PRIMARY_ACCOUNT_KEY:\n        return key, str(record.get("account_label") or PRIMARY_ACCOUNT_LABEL)\n    return key, str(record.get("account_label") or key)\n''',
)

external_helpers = r'''

def _settled_external_events(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[tuple[str, dict[str, Any], bool]]:
    events = state.get("auto_participation_events")
    if not isinstance(events, dict):
        return []
    approved_failures = {
        token
        for token, _record in auto_participation_owner_sync.pending_failure_events(
            state, now=now
        )
    }
    result: list[tuple[str, dict[str, Any], bool]] = []
    for raw_token, raw_record in events.items():
        if not isinstance(raw_record, dict):
            continue
        if str(raw_record.get("account_key") or "") != XFLARXX_ACCOUNT_KEY:
            continue
        token = str(raw_token)
        success = _success(raw_record)
        if success or token in approved_failures:
            result.append((token, raw_record, success))
    result.sort(key=lambda item: str(item[1].get("attempted_at") or item[0]))
    return result


def _single_result_message(
    key: str,
    item: dict[str, Any],
    record: dict[str, Any],
    success: bool,
) -> tuple[str, dict[str, Any]]:
    identifier = html.escape(str(item.get("identifier") or key))
    label = html.escape(str(record.get("account_label") or XFLARXX_ACCOUNT_LABEL))
    if success:
        title = "✅ <b>Участие принято</b>"
        detail = ""
    else:
        title = "⚠️ <b>Участие не принято</b>"
        detail = f"\nПричина: {html.escape(_failure_reason(record))}"
    return (
        f"{title}\n\n"
        f"Колесо: <code>{identifier}</code>\n"
        f"Аккаунт: <b>{label}</b>{detail}",
        _navigation(),
    )
'''
replace_once(
    "auto_participation_notifications.py",
    "\n\ndef sync_once(panel: Any) -> dict[str, int]:\n",
    external_helpers + "\n\ndef sync_once(panel: Any) -> dict[str, int]:\n",
)

new_sync = r'''def sync_once(panel: Any) -> dict[str, int]:
    """Deliver one owner aggregate and independent xFLARXx outcomes."""

    snap = panel.snapshot()
    state = snap.state if isinstance(getattr(snap, "state", None), dict) else {}
    groups = _settled_event_groups(state)
    external_events = _settled_external_events(state)
    if not groups and not external_events:
        return {
            "pending": 0,
            "completed": 0,
            "failed": 0,
            "success_completed": 0,
            "failure_completed": 0,
            "account_completed": 0,
        }

    active = state.get("active_wheels") if isinstance(state.get("active_wheels"), dict) else {}
    original_context = (
        getattr(panel, "current_chat_id", None),
        getattr(panel, "current_user_id", None),
        getattr(panel, "current_role", "guest"),
    )
    completed = 0
    failed = 0
    success_completed = 0
    failure_completed = 0

    if groups:
        _access, owner_id, owner, owner_chat_id = auto_participation_owner_sync._owner_context(
            panel
        )
        success_records = auto_participation_owner_sync._completion_records(owner)
        failure_records = auto_participation_owner_sync._failure_records(owner)

        for base_token, accounts in sorted(groups.items()):
            first_record = accounts[PRIMARY_ACCOUNT_KEY][1]
            key = str(first_record.get("wheel_key") or "").casefold()
            item = active.get(key)
            if not key or not isinstance(item, dict):
                failed += 1
                continue
            if auto_participation_owner_sync._event_token(item, key) != base_token:
                continue
            event_key = personal_wheel_voting.wheel_event_key(key, item)
            if _processed(success_records.get(event_key)) or _processed(
                failure_records.get(event_key)
            ):
                continue

            all_success = all(value[2] for value in accounts.values())
            any_success = any(value[2] for value in accounts.values())
            referral_restricted = wheel_publications_v2.entry_is_referral_restricted(item)
            notifications_enabled = _notification_enabled(owner)
            should_send = notifications_enabled and (
                all_success or not referral_restricted
            )
            now_text = datetime.now(UTC).isoformat()
            account_payload = {
                account_key: {
                    "status": str(record.get("status") or ""),
                    "success": bool(success),
                    "label": _account_identity(record)[1],
                }
                for account_key, (_token, record, success) in accounts.items()
            }

            try:
                panel.set_context(owner_chat_id, owner_id)
                vote_result: dict[str, Any] = {}
                original_button_updated = False
                if any_success:
                    raw_result = panel.mark_personal_participation(key)
                    vote_result = raw_result if isinstance(raw_result, dict) else {}
                    original_button_updated = auto_participation_owner_sync._mark_original_notification(
                        panel, owner_chat_id, item
                    )
                if should_send:
                    text, markup = _result_message(key, item, accounts)
                    panel.send(text, reply_markup=markup, chat_id=owner_chat_id)

                payload = {
                    "wheel_key": key,
                    "source_event_token": base_token,
                    "completed_at": now_text,
                    "notified_at": now_text if should_send else "",
                    "notification_sent": should_send,
                    "notification_policy": (
                        "sent"
                        if should_send
                        else "disabled"
                        if not notifications_enabled
                        else "referral_failure_suppressed"
                    ),
                    "referral_restricted": referral_restricted,
                    "accounts": account_payload,
                    "original_button_updated": original_button_updated,
                    "vote_changed": bool(vote_result.get("changed")),
                    "vote_command_id": str(vote_result.get("vote_command_id") or ""),
                }
                if all_success:
                    auto_participation_owner_sync._save_completion(
                        panel, owner_id, event_key, payload
                    )
                    success_records[event_key] = {"completed_at": now_text}
                    success_completed += 1
                else:
                    auto_participation_owner_sync._save_failure(
                        panel, owner_id, event_key, payload
                    )
                    failure_records[event_key] = {"completed_at": now_text}
                    failure_completed += 1
                completed += 1
            except Exception as exc:
                failed += 1
                print(
                    "WARNING unified auto participation notification sync: "
                    f"wheel={key} {type(exc).__name__}: {exc}"
                )
            finally:
                panel.current_chat_id, panel.current_user_id, panel.current_role = (
                    original_context
                )

    for token, record, success in external_events:
        key = str(record.get("wheel_key") or "").casefold()
        item = active.get(key)
        if not key or not isinstance(item, dict):
            failed += 1
            continue
        base_token = _base_event_token(token, record)
        if auto_participation_owner_sync._event_token(item, key) != base_token:
            continue
        try:
            _access, user_id, user, chat_id = betboom_account_participation._target_context(
                panel, str(record.get("alert_user") or XFLARXX_ALERT_USER)
            )
            event_key = (
                personal_wheel_voting.wheel_event_key(key, item)
                + f"#account:{XFLARXX_ACCOUNT_KEY}"
            )
            field = (
                "auto_participation_success_events"
                if success
                else "auto_participation_failure_events"
            )
            previous = betboom_account_participation._outcome_records(user, field).get(event_key)
            if _processed(previous):
                continue

            panel.set_context(chat_id, user_id)
            vote_result: dict[str, Any] = {}
            original_button_updated = False
            if success:
                raw_result = panel.mark_personal_participation(key)
                vote_result = raw_result if isinstance(raw_result, dict) else {}
                original_button_updated = auto_participation_owner_sync._mark_original_notification(
                    panel, chat_id, item
                )
            referral_restricted = wheel_publications_v2.entry_is_referral_restricted(item)
            notifications_enabled = _notification_enabled(user)
            should_send = notifications_enabled and (
                success or not referral_restricted
            )
            now_text = datetime.now(UTC).isoformat()
            if should_send:
                text, markup = _single_result_message(key, item, record, success)
                panel.send(text, reply_markup=markup, chat_id=chat_id)
            betboom_account_participation._save_outcome(
                panel,
                user_id,
                field=field,
                event_key=event_key,
                payload={
                    "wheel_key": key,
                    "source_event_token": token,
                    "account_key": XFLARXX_ACCOUNT_KEY,
                    "account_label": str(record.get("account_label") or XFLARXX_ACCOUNT_LABEL),
                    "completed_at": now_text,
                    "notified_at": now_text if should_send else "",
                    "notification_sent": should_send,
                    "notification_policy": (
                        "sent"
                        if should_send
                        else "disabled"
                        if not notifications_enabled
                        else "referral_failure_suppressed"
                    ),
                    "referral_restricted": referral_restricted,
                    "original_button_updated": original_button_updated,
                    "vote_changed": bool(vote_result.get("changed")),
                    "vote_command_id": str(vote_result.get("vote_command_id") or ""),
                },
            )
            if success:
                success_completed += 1
            else:
                failure_completed += 1
            completed += 1
        except Exception as exc:
            failed += 1
            print(
                "WARNING xFLARXx auto participation notification sync: "
                f"wheel={key} {type(exc).__name__}: {exc}"
            )
        finally:
            panel.current_chat_id, panel.current_user_id, panel.current_role = (
                original_context
            )

    return {
        "pending": len(groups) + len(external_events),
        "completed": completed,
        "failed": failed,
        "success_completed": success_completed,
        "failure_completed": failure_completed,
        "account_completed": completed,
    }
'''
regex_once(
    "auto_participation_notifications.py",
    r"def sync_once\(panel: Any\) -> dict\[str, int\]:.*?\n\n\ndef _patch_panel_notifications",
    new_sync + "\n\n\ndef _patch_panel_notifications",
)
replace_once(
    "auto_participation_notifications.py",
    '            values = list(original_options(self, role))\n',
    '            values = list(original_options(role))\n',
)
replace_once(
    "auto_participation_notifications.py",
    '''    groups = _settled_event_groups(\n        state, now=datetime(2026, 7, 22, 12, 10, tzinfo=UTC)\n    )\n    assert list(groups) == [base]\n''',
    '''    groups = _settled_event_groups(\n        state, now=datetime(2026, 7, 22, 12, 10, tzinfo=UTC)\n    )\n    assert list(groups) == [base]\n    external_state = copy.deepcopy(state)\n    external_state["auto_participation_events"][\n        base + "#account:xflarxx_primary"\n    ] = {\n        "wheel_key": "wheel",\n        "event_token": base,\n        "account_key": XFLARXX_ACCOUNT_KEY,\n        "account_label": XFLARXX_ACCOUNT_LABEL,\n        "alert_user": XFLARXX_ALERT_USER,\n        "status": "participated",\n        "bot_success_pending_at": "2026-07-22T12:01:20+00:00",\n    }\n    external = _settled_external_events(\n        external_state, now=datetime(2026, 7, 22, 12, 10, tzinfo=UTC)\n    )\n    assert len(external) == 1\n    assert external[0][1]["account_key"] == XFLARXX_ACCOUNT_KEY\n''',
)

# The installed notification option wrapper is a bound method, but the saved original is static.
replace_once(
    "notification_button_recovery.py",
    '''    panel = TelegramPanelRuntimeButtonRecovery.__new__(TelegramPanelRuntimeButtonRecovery)\n    panel.mark_personal_participation = lambda key: events.append(str(key))  # type: ignore[method-assign]\n''',
    '''    panel = TelegramPanelRuntimeButtonRecovery.__new__(TelegramPanelRuntimeButtonRecovery)\n    options = panel._notification_options_for_role("owner")\n    assert any(str(item[0]) == "auto_participation" for item in options)\n    panel.mark_personal_participation = lambda key: events.append(str(key))  # type: ignore[method-assign]\n''',
)

# 4. Remove the two obsolete settings tabs and redirect stale callbacks.
replace_once(
    "bbvg/bot/runtime.py",
    '''        if self.is_admin():\n            rows.extend(\n                [\n                    [{"text": "🧭 API и Legacy", "callback_data": "page:wheelmode"}],\n                    [{"text": "⛔ Отключённый функционал", "callback_data": "page:disabled_features"}],\n                ]\n            )\n            interval = int(\n''',
    '''        if self.is_admin():\n            interval = int(\n''',
)
replace_once(
    "bbvg/bot/runtime.py",
    '''        if normalized in {"wheelmode", "disabled_features"} and not self.is_admin():\n            self.show_settings()\n            return\n''',
    '''        if normalized in {"wheelmode", "disabled_features"}:\n            self.show_settings()\n            return\n''',
)

# 5. Ensure Control Center preflight compiles the changed participation modules.
replace_once(
    "scripts/validate_control_center.sh",
    '''  admin_panel_v2.py admin_panel_runtime_v41.py notification_button_recovery.py \\\n  telegram_ui.py chapter4_acceptance.py''',
    '''  admin_panel_v2.py admin_panel_runtime_v41.py notification_button_recovery.py \\\n  auto_participation_notifications.py auto_participation_owner_sync.py betboom_account_participation.py \\\n  telegram_ui.py chapter4_acceptance.py''',
)

# 6. Document the active ownership and UI contracts.
replace_once(
    "AGENTS.md",
    '''- Второй BetBoom-аккаунт Вячеслава использует отдельную сессию `BETBOOM_STORAGE_STATE_JSON_PART3/PART4` и предметный модуль `betboom_account_participation.py`. Его event-token содержит `#account:vyacheslav_secondary`, поэтому успех или ошибка основного аккаунта не подавляют второй. Пользовательский итог не отправляется этим модулем отдельно: агрегатор ждёт оба результата и формирует не более одного короткого сообщения на событие. Личный голос и рейтинг за одно событие остаются идемпотентными.\n''',
    '''- Второй BetBoom-аккаунт Вячеслава использует отдельную сессию `BETBOOM_STORAGE_STATE_JSON_PART3/PART4` и предметный модуль `betboom_account_participation.py`. Его event-token содержит `#account:vyacheslav_secondary`, поэтому успех или ошибка основного аккаунта не подавляют второй. Пользовательский итог не отправляется этим модулем отдельно: агрегатор ждёт оба результата и формирует не более одного короткого сообщения на событие. Личный голос и рейтинг за одно событие остаются идемпотентными.\n- BetBoom-аккаунт Telegram-пользователя `xFLARXx` использует `BETBOOM_STORAGE_STATE_JSON_PART5/PART6` и event-token `#account:xflarxx_primary`. Он участвует независимо от двух аккаунтов владельца; итог, личная отметка и рейтинг принадлежат только профилю `xFLARXx`.\n''',
)
changelog = read("docs/PROJECT_CHANGELOG_RU.md")
marker = "---\n\n"
entry = '''## 2026-07-23 — xFLARXx подключён к автоучастию, управление пользователями исправлено\n\nBetBoom-сессия из `BETBOOM_STORAGE_STATE_JSON_PART5` и `BETBOOM_STORAGE_STATE_JSON_PART6` подключена к Telegram-профилю `xFLARXx` как независимый account-token `xflarxx_primary`. Результат, личная отметка участия и рейтинг записываются только этому пользователю; два аккаунта владельца по-прежнему объединяются в один итог.\n\nИсправлен `TypeError` при открытии карточки пользователя в разделе «Доступ и администраторы»: обёртка настройки автоучастия теперь корректно вызывает исходный статический список уведомлений. Из настроек удалены вкладки «API и Legacy» и «Отключённый функционал»; старые callback ведут обратно в настройки.\n\n**Pre-update backup:** `backup/2026-07-23-before-xflarxx-account-access-cleanup`.\n\n'''
if entry.splitlines()[0] not in changelog:
    if marker not in changelog:
        raise SystemExit("PROJECT_CHANGELOG_RU.md marker not found")
    write("docs/PROJECT_CHANGELOG_RU.md", changelog.replace(marker, marker + entry, 1))

# Static contract checks before tests.
assert "page:wheelmode" not in re.search(
    r"def show_settings\(self\) -> None:.*?\n    def show_interval",
    read("bbvg/bot/runtime.py"),
    flags=re.S,
).group(0)
assert "page:disabled_features" not in re.search(
    r"def show_settings\(self\) -> None:.*?\n    def show_interval",
    read("bbvg/bot/runtime.py"),
    flags=re.S,
).group(0)
assert "original_options(role)" in read("auto_participation_notifications.py")
assert "BETBOOM_STORAGE_STATE_JSON_PART5" in read(".github/workflows/auto-participation.yml")
assert "BETBOOM_STORAGE_STATE_JSON_PART6" in read(".github/workflows/auto-participation.yml")

print("xFLARXx account, access detail and settings cleanup patch applied")
