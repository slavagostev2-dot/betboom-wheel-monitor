from __future__ import annotations

import html
import json
from datetime import datetime, timedelta

import monitor
import notification_router
import vk_start_welcome

notification_router.install(monitor)

try:
    vk_start_welcome.dispatch_start_welcome_workflow()
except Exception as exc:
    print(f"WARNING VK Start workflow dispatch: {type(exc).__name__}: {exc}")

_original_assess_new = monitor.assess_new_wheel
_original_assess_pending = monitor.assess_pending_wheel
_original_fetch_all_sources = monitor.fetch_all_sources
_original_mark_participating = monitor.mark_participating
_original_process_active_wheels = monitor.process_active_wheels

_IDENTIFIER_MAPPINGS = monitor.load_identifier_sources()
try:
    _identifier_config = json.loads(
        monitor.IDENTIFIER_SOURCES_PATH.read_text(encoding="utf-8")
    )
except (OSError, json.JSONDecodeError):
    _identifier_config = {}
_COLLECTOR_SOURCES = {
    str(value).strip().lstrip("@").casefold()
    for value in _identifier_config.get("collectors", [])
    if str(value).strip()
}
_CANONICAL_MESSAGES: dict[str, monitor.Message] = {}
_WHEEL_PUBLICATIONS: dict[str, list[dict]] = {}


def _mapped_sources(identifier: str) -> set[str]:
    return {
        value.casefold()
        for value in monitor.related_sources(identifier, _IDENTIFIER_MAPPINGS)
    }


def _source_rank(identifier: str, source: str) -> int:
    normalized = source.strip().lstrip("@").casefold()
    if normalized in _mapped_sources(identifier):
        return 0
    if normalized in _COLLECTOR_SOURCES:
        return 2
    return 1


def _message_rank(message: monitor.Message, identifier: str) -> tuple:
    return (
        _source_rank(identifier, message.source),
        message.date.astimezone(monitor.UTC),
        message.message_id,
    )


def _preserve_source_messages(
    messages_by_source: dict[str, list[monitor.Message]],
) -> dict[str, list[monitor.Message]]:
    """Keep each Telegram post attributed to the channel that published it."""

    result: dict[str, list[monitor.Message]] = {}
    for source, messages in messages_by_source.items():
        rewritten: list[monitor.Message] = []
        seen_messages: set[tuple[str, int]] = set()
        for message in messages:
            marker = (message.source.casefold(), message.message_id)
            if marker in seen_messages:
                continue
            seen_messages.add(marker)
            rewritten.append(message)
        result[source] = rewritten
    return result


def fetch_all_sources_with_originals(sources):
    """Use the mapped creator or earliest non-collector post as wheel origin."""
    messages_by_source, source_errors, empty_sources = _original_fetch_all_sources(sources)
    candidates: dict[str, list[monitor.Message]] = {}

    for messages in messages_by_source.values():
        for message in messages:
            for link in monitor.extract_links(message.text):
                candidates.setdefault(monitor.wheel_key(link), []).append(message)

    _CANONICAL_MESSAGES.clear()
    _WHEEL_PUBLICATIONS.clear()
    for key, rows in candidates.items():
        if not rows:
            continue
        identifier = monitor.wheel_identifier(
            next(
                link
                for message in rows
                for link in monitor.extract_links(message.text)
                if monitor.wheel_key(link) == key
            )
        )
        _CANONICAL_MESSAGES[key] = min(
            rows,
            key=lambda message: _message_rank(message, identifier),
        )
        publications: dict[tuple[str, int], dict] = {}
        for row in rows:
            marker = (row.source.casefold(), row.message_id)
            publications[marker] = {
                "source": row.source,
                "message_id": row.message_id,
                "message_date": row.date.astimezone(monitor.UTC).isoformat(),
                "message_url": row.message_url,
            }
        _WHEEL_PUBLICATIONS[key] = sorted(
            publications.values(),
            key=lambda item: (str(item.get("message_date") or ""), str(item.get("source") or "").casefold()),
        )

    messages_by_source = _preserve_source_messages(messages_by_source)

    return messages_by_source, source_errors, empty_sources
