from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected fragment not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    # 1. Preserve the newest recurring wheel generation when workflow state is merged.
    replace_once(
        "auto_participation_bot_sync.py",
        "import monitor\n",
        "import monitor\nimport wheel_publications_v2\n",
    )
    replace_once(
        "auto_participation_bot_sync.py",
        '''def _merge_timed_record(remote: Any, local: Any) -> Any:\n''',
        '''def _active_event_marker(record: Any) -> datetime:\n    if not isinstance(record, dict):\n        return datetime.min.replace(tzinfo=UTC)\n    for field in ("server_start_at", "message_date", "first_notified_at", "created_at"):\n        parsed = _parse_datetime(record.get(field))\n        if parsed is not None:\n            return parsed\n    return _record_timestamp(record)\n\n\ndef _active_event_is_newer(remote: Any, local: Any) -> bool:\n    if not isinstance(local, dict):\n        return False\n    if not isinstance(remote, dict):\n        return True\n    remote_token = _event_token(remote)\n    local_token = _event_token(local)\n    if remote_token == local_token:\n        return False\n    remote_marker = _active_event_marker(remote)\n    local_marker = _active_event_marker(local)\n    if local_marker != remote_marker:\n        return local_marker > remote_marker\n    return _record_timestamp(local) > _record_timestamp(remote)\n\n\ndef _event_context(state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:\n    key = str(item.get("wheel_key") or item.get("identifier") or "").casefold()\n    source = dict(item)\n    active = state.get("active_wheels")\n    active_item = active.get(key) if isinstance(active, dict) else None\n    if isinstance(active_item, dict) and _event_token(active_item) == _event_token(item):\n        source = dict(active_item)\n        source.update(item)\n    fields = (\n        "identifier", "url", "source", "message_id", "message_date",\n        "message_url", "message_text", "button_token", "action_id",\n        "server_start_at", "deadline", "available_at", "generation_id",\n        "event_id",\n    )\n    context = {field: copy.deepcopy(source[field]) for field in fields if field in source}\n    context["wheel_key"] = key\n    context.setdefault("identifier", key)\n    context["referral_restricted"] = wheel_publications_v2.entry_is_referral_restricted(source)\n    return context\n\n\ndef _merge_timed_record(remote: Any, local: Any) -> Any:\n''',
    )
    replace_once(
        "auto_participation_bot_sync.py",
        '''            updated = copy.deepcopy(current)\n            for field in _AUTO_PARTICIPATION_FIELDS:\n                if field in raw_item:\n                    updated[field] = copy.deepcopy(raw_item[field])\n            if bool(raw_item.get("participating")):\n                updated["participating"] = True\n            active[key] = updated\n''',
        '''            if _active_event_is_newer(current, raw_item):\n                updated = copy.deepcopy(current)\n                updated.update(copy.deepcopy(raw_item))\n                active[key] = updated\n                continue\n            updated = copy.deepcopy(current)\n            for field in _AUTO_PARTICIPATION_FIELDS:\n                if field in raw_item:\n                    updated[field] = copy.deepcopy(raw_item[field])\n            if bool(raw_item.get("participating")):\n                updated["participating"] = True\n            active[key] = updated\n''',
    )
    replace_once(
        "auto_participation_bot_sync.py",
        '''        if isinstance(local_rows, dict):\n            for key, value in local_rows.items():\n                if str(key) not in rows:\n                    rows[str(key)] = copy.deepcopy(value)\n''',
        '''        if isinstance(local_rows, dict):\n            for key, value in local_rows.items():\n                normalized = str(key)\n                if normalized not in rows:\n                    rows[normalized] = copy.deepcopy(value)\n                elif collection_name == "participating_wheels":\n                    rows[normalized] = _merge_timed_record(rows[normalized], value)\n''',
    )
    replace_once(
        "auto_participation_bot_sync.py",
        '''        record = events.get(token)\n        if not isinstance(record, dict):\n            continue\n\n        if bool(attempt.get("success")):\n''',
        '''        record = events.get(token)\n        if not isinstance(record, dict):\n            continue\n        context = _event_context(state, attempt)\n        if context and record.get("event_context") != context:\n            record["event_context"] = context\n            changed = True\n\n        if bool(attempt.get("success")):\n''',
    )
    replace_once(
        "auto_participation_bot_sync.py",
        '''    assert _event_token({"wheel_key": "x", "message_date": "now"}) == "x#seen:now"\n\n    remote = {\n''',
        '''    assert _event_token({"wheel_key": "x", "message_date": "now"}) == "x#seen:now"\n\n    recurring_remote = {\n        "active_wheels": {\n            "zonertw5": {\n                "wheel_key": "zonertw5",\n                "action_id": 961,\n                "server_start_at": "2026-07-22T16:27:00+00:00",\n                "last_checked_at": "2026-07-22T18:30:00+00:00",\n            }\n        }\n    }\n    recurring_local = {\n        "active_wheels": {\n            "zonertw5": {\n                "wheel_key": "zonertw5",\n                "action_id": 989,\n                "server_start_at": "2026-07-22T18:26:05+00:00",\n                "message_date": "2026-07-22T18:27:00+00:00",\n                "participating": True,\n            }\n        }\n    }\n    recurring_merged = merge_auto_participation_state(recurring_remote, recurring_local)\n    assert recurring_merged["active_wheels"]["zonertw5"]["action_id"] == 989\n    assert recurring_merged["active_wheels"]["zonertw5"]["participating"] is True\n\n    remote = {\n''',
    )

    # 2. When recovery alone discovers a wheel, queue its normal primary notification.
    replace_once(
        "auto_participation_recovery.py",
        "import monitor\n",
        "import monitor\nimport wheel_publications_v2\n",
    )
    replace_once(
        "auto_participation_recovery.py",
        '''def _restore_runtime_state(\n''',
        '''def _notification_already_recorded(\n    state: dict[str, Any],\n    key: str,\n    item: dict[str, Any],\n) -> bool:\n    published = monitor.parse_datetime(item.get("message_date"))\n    threshold = published - timedelta(minutes=5) if published is not None else None\n    for collection_name in ("activation_alerts", "url_alerts"):\n        collection = state.get(collection_name)\n        record = collection.get(key) if isinstance(collection, dict) else None\n        if not isinstance(record, dict):\n            continue\n        alerted_at = monitor.parse_datetime(record.get("alerted_at"))\n        if threshold is None or (alerted_at is not None and alerted_at >= threshold):\n            return True\n    return False\n\n\ndef _restore_runtime_state(\n''',
    )
    replace_once(
        "auto_participation_recovery.py",
        '''        if is_recovered_missing:\n            active_wheels[key] = entry\n\n        # Capture success before refreshing API fields. A later browser probe is not\n''',
        '''        if is_recovered_missing:\n            active_wheels[key] = entry\n            if not _notification_already_recorded(state, key, item):\n                entry["recovered_initial_notification_pending_at"] = scanned_at.isoformat()\n                entry["recovered_initial_notification_reason"] = "recovery_discovered_missing_event"\n                entry["referral_restricted"] = wheel_publications_v2.entry_is_referral_restricted(item)\n\n        # Capture success before refreshing API fields. A later browser probe is not\n''',
    )
    replace_once(
        "auto_participation_recovery.py",
        '''    assert "bot_failure_pending_at" not in legacy_failure\n    print("auto participation recovery authoritative-outcome self-test passed")\n''',
        '''    assert "bot_failure_pending_at" not in legacy_failure\n    notification_state = {\n        "url_alerts": {\n            "old": {"alerted_at": "2026-07-21T10:00:00+00:00"}\n        }\n    }\n    assert not _notification_already_recorded(\n        notification_state,\n        "old",\n        {"message_date": "2026-07-22T10:00:00+00:00"},\n    )\n    assert _notification_already_recorded(\n        notification_state,\n        "old",\n        {"message_date": "2026-07-21T10:01:00+00:00"},\n    )\n    print("auto participation recovery authoritative-outcome self-test passed")\n''',
    )

    # 3. Let the normal monitor deliver the recovered primary notification before reminders/outcomes.
    replace_once(
        "bbvg_monitor_runtime.py",
        '''def process_active_without_page_verdict(state: dict, stats: dict):\n    current = monitor.now_utc()\n    verification = revalidate_active_wheels(state, current)\n''',
        '''def _deliver_recovered_initial_notifications(state: dict) -> dict[str, int | bool]:\n    sent = 0\n    failed = 0\n    changed = False\n    mappings = monitor.load_identifier_sources()\n    for key, entry in list(state.setdefault("active_wheels", {}).items()):\n        if not isinstance(entry, dict) or not entry.get("recovered_initial_notification_pending_at"):\n            continue\n        message = monitor.active_entry_message(entry)\n        url = str(entry.get("url") or "").strip()\n        if message is None or not url:\n            failed += 1\n            continue\n        try:\n            monitor.notify_new_link(\n                message,\n                url,\n                monitor.parse_datetime(entry.get("deadline")),\n                str(entry.get("method") or "восстановлено независимой проверкой"),\n                mappings,\n                state,\n                str(entry.get("page_excerpt") or ""),\n                action_id=_record_action_id(entry),\n                available_at=monitor.parse_datetime(entry.get("available_at")),\n                verification_status=str(entry.get("verification_status") or ""),\n                server_start_at=monitor.parse_datetime(entry.get("server_start_at")),\n            )\n        except Exception as exc:\n            entry["recovered_initial_notification_error"] = f"{type(exc).__name__}: {exc}"[:300]\n            failed += 1\n            changed = True\n            continue\n        entry.pop("recovered_initial_notification_pending_at", None)\n        entry.pop("recovered_initial_notification_error", None)\n        entry["recovered_initial_notification_sent_at"] = monitor.now_utc().isoformat()\n        sent += 1\n        changed = True\n    return {"sent": sent, "failed": failed, "changed": changed}\n\n\ndef process_active_without_page_verdict(state: dict, stats: dict):\n    current = monitor.now_utc()\n    recovered_notifications = _deliver_recovered_initial_notifications(state)\n    verification = revalidate_active_wheels(state, current)\n''',
    )
    replace_once(
        "bbvg_monitor_runtime.py",
        '''    changed = bool(verification.get("changed"))\n''',
        '''    changed = bool(verification.get("changed")) or bool(\n        recovered_notifications.get("changed")\n    )\n''',
    )
    replace_once(
        "bbvg_monitor_runtime.py",
        '''    result["verification_deferred"] = int(verification.get("deferred", 0) or 0)\n    result["pending_total"] = pending_total\n''',
        '''    result["verification_deferred"] = int(verification.get("deferred", 0) or 0)\n    result["recovered_initial_notifications_sent"] = int(\n        recovered_notifications.get("sent", 0) or 0\n    )\n    result["recovered_initial_notifications_failed"] = int(\n        recovered_notifications.get("failed", 0) or 0\n    )\n    result["pending_total"] = pending_total\n''',
    )

    # 4. Finalize recent outcomes even if active_wheels was removed or points at an older generation.
    replace_once(
        "auto_participation_notifications.py",
        "from datetime import datetime, timezone\n",
        "from datetime import datetime, timedelta, timezone\n",
    )
    replace_once(
        "auto_participation_notifications.py",
        '''AUTO_NOTIFICATION_DESCRIPTION = "Один общий итог по двум BetBoom-аккаунтам"\n''',
        '''AUTO_NOTIFICATION_DESCRIPTION = "Один общий итог по двум BetBoom-аккаунтам"\nRECOVERABLE_OUTCOME_WINDOW = timedelta(hours=12)\n''',
    )
    replace_once(
        "auto_participation_notifications.py",
        '''def _success(record: dict[str, Any]) -> bool:\n''',
        '''def _parse_datetime(value: Any) -> datetime | None:\n    text = str(value or "").strip()\n    if not text:\n        return None\n    try:\n        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))\n    except ValueError:\n        return None\n    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)\n\n\ndef _token_identity(base_token: str) -> tuple[int, str]:\n    if "#action:" not in base_token:\n        return 0, ""\n    tail = base_token.split("#action:", 1)[1]\n    action_text, separator, start = tail.partition(":")\n    try:\n        action_id = int(action_text)\n    except (TypeError, ValueError):\n        action_id = 0\n    return action_id, start if separator else ""\n\n\ndef _group_is_recent(accounts: dict[str, tuple[str, dict[str, Any], bool]]) -> bool:\n    timestamps = []\n    for _token, record, _success_value in accounts.values():\n        for field in ("bot_success_pending_at", "bot_failure_pending_at", "attempted_at"):\n            parsed = _parse_datetime(record.get(field))\n            if parsed is not None:\n                timestamps.append(parsed)\n                break\n    return bool(timestamps and datetime.now(UTC) - max(timestamps) <= RECOVERABLE_OUTCOME_WINDOW)\n\n\ndef _event_item(\n    state: dict[str, Any],\n    base_token: str,\n    accounts: dict[str, tuple[str, dict[str, Any], bool]],\n) -> tuple[dict[str, Any] | None, bool]:\n    primary_record = accounts[PRIMARY_ACCOUNT_KEY][1]\n    key = str(primary_record.get("wheel_key") or "").casefold()\n    active = state.get("active_wheels")\n    current = active.get(key) if isinstance(active, dict) else None\n    if isinstance(current, dict) and auto_participation_owner_sync._event_token(current, key) == base_token:\n        return dict(current), True\n\n    context = primary_record.get("event_context")\n    item = dict(context) if isinstance(context, dict) else {}\n    if not item:\n        candidates = []\n        contexts = state.get("button_contexts")\n        if isinstance(contexts, dict):\n            for raw in contexts.values():\n                if not isinstance(raw, dict):\n                    continue\n                raw_key = str(raw.get("wheel_key") or raw.get("identifier") or "").casefold()\n                if raw_key == key:\n                    candidates.append(dict(raw))\n        _action_id, start_text = _token_identity(base_token)\n        start_at = _parse_datetime(start_text)\n        if candidates:\n            def distance(candidate: dict[str, Any]) -> tuple[float, str]:\n                candidate_at = _parse_datetime(candidate.get("message_date") or candidate.get("created_at"))\n                if start_at is None or candidate_at is None:\n                    return (float("inf"), str(candidate.get("message_date") or ""))\n                return (abs((candidate_at - start_at).total_seconds()), candidate_at.isoformat())\n            item = min(candidates, key=distance)\n    if not item and not key:\n        return None, False\n    action_id, start_text = _token_identity(base_token)\n    item.setdefault("wheel_key", key)\n    item.setdefault("identifier", key)\n    if action_id > 0:\n        item["action_id"] = action_id\n    if start_text:\n        item["server_start_at"] = start_text\n    return item, False\n\n\ndef _success(record: dict[str, Any]) -> bool:\n''',
    )
    replace_once(
        "auto_participation_notifications.py",
        '''        first_record = accounts[PRIMARY_ACCOUNT_KEY][1]\n        key = str(first_record.get("wheel_key") or "").casefold()\n        item = active.get(key)\n        if not key or not isinstance(item, dict):\n            failed += 1\n            continue\n        if auto_participation_owner_sync._event_token(item, key) != base_token:\n            continue\n''',
        '''        first_record = accounts[PRIMARY_ACCOUNT_KEY][1]\n        key = str(first_record.get("wheel_key") or "").casefold()\n        item, active_matches = _event_item(state, base_token, accounts)\n        if not key or not isinstance(item, dict):\n            failed += 1\n            continue\n        if not active_matches and not _group_is_recent(accounts):\n            continue\n''',
    )
    replace_once(
        "auto_participation_notifications.py",
        '''            if any_success:\n                raw_result = panel.mark_personal_participation(key)\n                vote_result = raw_result if isinstance(raw_result, dict) else {}\n                original_button_updated = auto_participation_owner_sync._mark_original_notification(\n                    panel, owner_chat_id, item\n                )\n''',
        '''            if any_success and active_matches:\n                raw_result = panel.mark_personal_participation(key)\n                vote_result = raw_result if isinstance(raw_result, dict) else {}\n            elif any_success:\n                vote_result = {"changed": False, "recovered_outcome": True}\n            if any_success:\n                original_button_updated = auto_participation_owner_sync._mark_original_notification(\n                    panel, owner_chat_id, item\n                )\n''',
    )
    replace_once(
        "auto_participation_notifications.py",
        '''                "vote_changed": bool(vote_result.get("changed")),\n''',
        '''                "vote_changed": bool(vote_result.get("changed")),\n                "recovered_event_context": not active_matches,\n''',
    )
    replace_once(
        "auto_participation_notifications.py",
        '''    assert wheel_publications_v2.entry_is_referral_restricted(\n        {"message_text": "Колесо для рефов"}\n    )\n''',
        '''    assert wheel_publications_v2.entry_is_referral_restricted(\n        {"message_text": "Колесо для рефов"}\n    )\n    recovered_state = {\n        "button_contexts": {\n            "new": {\n                "wheel_key": "wheel",\n                "message_date": "2026-07-22T12:00:10+00:00",\n                "message_text": "Колесо для рефов",\n                "url": "https://betboom.ru/freestream/wheel",\n            },\n            "old": {\n                "wheel_key": "wheel",\n                "message_date": "2026-07-21T12:00:10+00:00",\n            },\n        }\n    }\n    recovered_item, active_matches = _event_item(recovered_state, base, groups[base])\n    assert active_matches is False\n    assert recovered_item and recovered_item["action_id"] == 42\n    assert wheel_publications_v2.entry_is_referral_restricted(recovered_item)\n''',
    )

    # 5. Document the operational contract.
    replace_once(
        "AGENTS.md",
        "Запуски `auto-participation.yml` сериализованы без отмены активного запуска. Подтверждённый успех основной event-попытки сразу ставится в очередь Control Center; затем выполняется быстрый независимый retry только по уже найденным активным колёсам, проверяются второй аккаунт владельца и `xFLARXx`, а промежуточный результат публикуется в `state.json` до полного пересканирования источников. Полный source-recovery остаётся страховочным вторым проходом, и каждый push объединяется с последним `state.json`.",
        "Запуски `auto-participation.yml` сериализованы без отмены активного запуска. Подтверждённый успех основной event-попытки сразу ставится в очередь Control Center; затем выполняется быстрый независимый retry только по уже найденным активным колёсам, проверяются второй аккаунт владельца и `xFLARXx`, а промежуточный результат публикуется в `state.json` до полного пересканирования источников. При объединении состояния полная идентичность более нового события (`action_id + server_start_at`) имеет приоритет над устаревшей записью того же URL. Если независимый recovery первым обнаружил колесо, он ставит обычное первичное уведомление в очередь живого monitor-runtime, включая обязательную пометку реферального ограничения. Полный source-recovery остаётся страховочным вторым проходом, и каждый push объединяется с последним `state.json`.",
    )
    changelog = Path("docs/PROJECT_CHANGELOG_RU.md")
    text = changelog.read_text(encoding="utf-8")
    marker = "---\n\n"
    entry = '''---\n\n## 2026-07-23 — Исправлены повторные колёса и зависшие итоги автоучастия\n\nУстранена гонка, при которой workflow записывал успешный результат нового `action_id`, а `active_wheels` после merge оставался на предыдущем запуске того же URL. Control Center теперь может восстановить контекст недавнего исхода из event-record или `button_contexts`, поэтому подтверждённые результаты не остаются навсегда в `waiting_for_control_center`.\n\nЕсли независимый recovery обнаружил активное колесо, которого ещё нет в monitor-state, живой monitor-runtime отправляет обычное первичное уведомление до дальнейших напоминаний. Текст публикации сохраняется, поэтому реферальное колесо обязательно получает пометку «Колесо только для рефералов»; отрицательный итог такого колеса по-прежнему не отправляется.\n\n**Pre-update backup:** `backup/2026-07-23-before-recurring-auto-outcome-repair`.\n\n'''
    if marker not in text:
        raise SystemExit("Changelog marker not found")
    changelog.write_text(text.replace(marker, entry, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
