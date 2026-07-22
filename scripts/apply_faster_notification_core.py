from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected fragment not found in {path}: {old[:160]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once(
        "auto_participation_owner_sync.py",
        "SYNC_INTERVAL_SECONDS = 20\nFAILURE_GRACE_SECONDS = 90\nMAX_COMPLETED_EVENTS = 500\n",
        "SYNC_INTERVAL_SECONDS = 5\nFAILURE_GRACE_SECONDS = 30\nMAX_COMPLETED_EVENTS = 500\nTERMINAL_FAILURE_STATUSES = {\n    \"button_not_found\",\n    \"participation_closed\",\n    \"not_eligible\",\n    \"rejected\",\n}\n",
    )
    replace_once(
        "auto_participation_owner_sync.py",
        "        if (current - pending_at).total_seconds() < FAILURE_GRACE_SECONDS:\n            continue\n        if bool(raw.get(\"manual_notification_sent\")):\n",
        "        if (current - pending_at).total_seconds() < FAILURE_GRACE_SECONDS:\n            continue\n        status = str(\n            raw.get(\"bot_failure_status\") or raw.get(\"status\") or \"\"\n        ).casefold()\n        if status not in TERMINAL_FAILURE_STATUSES:\n            continue\n        if bool(raw.get(\"manual_notification_sent\")):\n",
    )

    replace_once(
        "auto_participation_recovery.py",
        "def _event_token(item: dict[str, Any]) -> str:\n",
        '''def _active_state_candidates(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    active = state.get("active_wheels")
    if not isinstance(active, dict):
        return {}
    candidates: dict[str, dict[str, Any]] = {}
    for raw_key, raw in active.items():
        if not isinstance(raw, dict):
            continue
        key = str(raw_key or raw.get("wheel_key") or raw.get("identifier") or "").casefold()
        url = str(raw.get("url") or "").strip()
        if not key or not url:
            continue
        try:
            message_id = int(raw.get("message_id") or 0)
        except (TypeError, ValueError):
            message_id = 0
        record = dict(raw)
        record["wheel_key"] = key
        record.setdefault("identifier", key)
        record["url"] = monitor.normalize_url(url)
        record.setdefault("source", str(raw.get("source") or ""))
        record["message_id"] = message_id
        record.setdefault(
            "message_date",
            str(
                raw.get("message_date")
                or raw.get("first_notified_at")
                or raw.get("created_at")
                or ""
            ),
        )
        record.setdefault("message_url", str(raw.get("message_url") or ""))
        record.setdefault("message_text", str(raw.get("message_text") or "")[:4000])
        candidates[key] = record
    return candidates


def _event_token(item: dict[str, Any]) -> str:
''',
    )

    old = '''def run_recovery() -> dict[str, Any]:
    """Find fresh approved wheels, verify them with BetBoom, and recover participation."""

    if not auto.configured():
        raise RuntimeError("BetBoom auto participation session is not configured")

    sources = monitor.read_list(monitor.SOURCES_PATH)
    results, errors, empty = monitor.fetch_all_sources(sources)
    now = monitor.now_utc()
    cutoff = now - timedelta(hours=3)

    persisted = _json(monitor.STATE_PATH, {})

    candidates: dict[str, dict[str, Any]] = {}
    for source, messages in results.items():
        if not isinstance(messages, list):
            continue
        for message in messages:
            try:
                published = message.date.astimezone(monitor.UTC)
            except Exception:
                continue
            if published < cutoff:
                continue
            for link in monitor.extract_links(message.text):
                key = monitor.wheel_key(link)
                current = candidates.get(key)
                record = {
                    "wheel_key": key,
                    "url": monitor.normalize_url(link),
                    "source": source,
                    "message_id": message.message_id,
                    "message_date": published.isoformat(),
                    "message_url": message.message_url,
                    "message_text": str(message.text or "")[:4000],
                }
                if current is None or record["message_date"] > current["message_date"]:
                    candidates[key] = record

    checked: list[dict[str, Any]] = []
'''
    new = '''def run_recovery(*, active_only: bool = False) -> dict[str, Any]:
    """Verify current active wheels quickly or run the full source recovery scan."""

    if not auto.configured():
        raise RuntimeError("BetBoom auto participation session is not configured")

    now = monitor.now_utc()
    persisted = _json(monitor.STATE_PATH, {})
    sources: list[str] = []
    results: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    empty: list[str] = []

    if active_only:
        candidates = _active_state_candidates(persisted)
    else:
        sources = monitor.read_list(monitor.SOURCES_PATH)
        results, errors, empty = monitor.fetch_all_sources(sources)
        cutoff = now - timedelta(hours=3)
        candidates: dict[str, dict[str, Any]] = {}
        for source, messages in results.items():
            if not isinstance(messages, list):
                continue
            for message in messages:
                try:
                    published = message.date.astimezone(monitor.UTC)
                except Exception:
                    continue
                if published < cutoff:
                    continue
                for link in monitor.extract_links(message.text):
                    key = monitor.wheel_key(link)
                    current = candidates.get(key)
                    record = {
                        "wheel_key": key,
                        "url": monitor.normalize_url(link),
                        "source": source,
                        "message_id": message.message_id,
                        "message_date": published.isoformat(),
                        "message_url": message.message_url,
                        "message_text": str(message.text or "")[:4000],
                    }
                    if current is None or record["message_date"] > current["message_date"]:
                        candidates[key] = record

    checked: list[dict[str, Any]] = []
'''
    replace_once("auto_participation_recovery.py", old, new)
    replace_once(
        "auto_participation_recovery.py",
        '        "scanned_at": now.isoformat(),\n        "sources_total": len(sources),\n',
        '        "scanned_at": now.isoformat(),\n        "mode": "active_only" if active_only else "full_source_scan",\n        "sources_total": len(sources),\n',
    )
    replace_once(
        "auto_participation_recovery.py",
        '    parser.add_argument("--self-test", action="store_true")\n    args = parser.parse_args()\n',
        '    parser.add_argument("--self-test", action="store_true")\n    parser.add_argument("--active-only", action="store_true")\n    args = parser.parse_args()\n',
    )
    replace_once(
        "auto_participation_recovery.py",
        "    payload = run_recovery()\n",
        "    payload = run_recovery(active_only=args.active_only)\n",
    )
    replace_once(
        "auto_participation_recovery.py",
        '    assert "bot_failure_pending_at" not in legacy_failure\n    print("auto participation recovery authoritative-outcome self-test passed")\n',
        '''    assert "bot_failure_pending_at" not in legacy_failure

    active_candidates = _active_state_candidates(
        {
            "active_wheels": {
                "wheel": {
                    "url": "https://betboom.ru/freestream/wheel",
                    "message_date": "2026-07-22T12:00:00+00:00",
                },
                "missing-url": {},
            }
        }
    )
    assert list(active_candidates) == ["wheel"]
    assert active_candidates["wheel"]["wheel_key"] == "wheel"
    print("auto participation recovery authoritative-outcome self-test passed")
''',
    )

    replace_once(
        "AGENTS.md",
        "Запуски `auto-participation.yml` сериализованы без отмены активного запуска; результат объединяется с последним `state.json` перед каждым push.",
        "Запуски `auto-participation.yml` сериализованы без отмены активного запуска. Сначала выполняется быстрый active-only recovery по уже найденным колёсам, результаты всех BetBoom-аккаунтов публикуются в `state.json`, и только затем запускается полный поиск по источникам как страховочный проход. Каждый push объединяется с последним `state.json`.",
    )
    replace_once(
        "AGENTS.md",
        "Только Control Center после пяти минут стабилизации точного `wheel_key + action_id + server_start_at` вправе учитывать отрицательный результат из закрытого списка терминальных статусов; ранее подтверждённый успех имеет безусловный приоритет.",
        "Только Control Center после 30 секунд стабилизации точного `wheel_key + action_id + server_start_at` вправе учитывать отрицательный результат из закрытого списка терминальных статусов и только после быстрого независимого recovery; ранее подтверждённый успех имеет безусловный приоритет.",
    )
    replace_once(
        "AGENTS.md",
        "- Непрерывность Control Center обеспечивается штатным `admin-bot.yml`:",
        "- Быстрые итоги автоучастия проверяются Control Center каждые 5 секунд.\n- Непрерывность Control Center обеспечивается штатным `admin-bot.yml`:",
    )

    changelog = Path("docs/PROJECT_CHANGELOG_RU.md")
    text = changelog.read_text(encoding="utf-8")
    marker = "---\n\n"
    entry = '''---

## 2026-07-23 — Ускорена доставка итогов автоучастия

Уведомления больше не ждут полного сканирования всех Telegram-источников. После основной попытки выполняется быстрый recovery только по текущим активным колёсам, сразу проверяются второй аккаунт владельца и аккаунт `xFLARXx`, после чего промежуточный подтверждённый результат публикуется для Control Center. Полный source-recovery остаётся вторым страховочным проходом.

Control Center проверяет итоги каждые 5 секунд и допускает отрицательный итог через 30 секунд только для терминальных статусов. Автоматический отдельный запуск `xflarxx-auto-participation.yml` переводится в ручной fallback, поскольку `xFLARXx` теперь входит в быстрый общий проход.

**Pre-update backup:** `backup/2026-07-23-before-faster-auto-notifications` (`c07a136bb356da5bb429bfdcbd618832afa17f80`).

'''
    if marker not in text:
        raise SystemExit("Changelog marker not found")
    changelog.write_text(text.replace(marker, entry, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
