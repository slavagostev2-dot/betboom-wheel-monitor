from __future__ import annotations

import html
from datetime import datetime, timedelta

import monitor
import notification_router

notification_router.install(monitor)

_original_assess_new = monitor.assess_new_wheel
_original_assess_pending = monitor.assess_pending_wheel
_original_mark_participating = monitor.mark_participating
_original_process_active_wheels = monitor.process_active_wheels


def _notification_first(message, result):
    """Deliver a fresh unique Telegram wheel post even if page parsing is inconclusive."""
    age = monitor.message_age(message)
    if result.should_notify:
        return result
    if age <= timedelta(minutes=monitor.MAX_NEW_POST_AGE_MINUTES):
        return monitor.WheelAssessment(
            True,
            result.deadline,
            f"новая уникальная публикация; {result.method}",
            "preliminary",
            result.page_excerpt,
        )
    return result


def assess_new_notification_first(message, link, state=None):
    return _notification_first(message, _original_assess_new(message, link, state))


def assess_pending_notification_first(message, link, state=None):
    return _notification_first(message, _original_assess_pending(message, link, state))


def _deadline_from_record(record):
    if not isinstance(record, dict):
        return None
    direct = monitor.parse_datetime(record.get("deadline"))
    if direct:
        return direct
    published = monitor.parse_datetime(record.get("message_date"))
    text = str(record.get("message_text") or "")
    if not published or not text:
        return None
    deadline, _ = monitor.infer_deadline(text, published)
    return deadline


def _record_wheel_key(record):
    if not isinstance(record, dict):
        return ""
    key = str(record.get("wheel_key") or "").casefold()
    if key:
        return key
    url = str(record.get("url") or "")
    return monitor.wheel_key(url) if url else ""


def _recover_deadline(state, key, entry):
    direct = _deadline_from_record(entry)
    if direct:
        return direct

    participant = state.get("participating_wheels", {}).get(key)
    direct = _deadline_from_record(participant)
    if direct:
        return direct

    first_notified = monitor.parse_datetime(entry.get("first_notified_at"))
    oldest_allowed = (
        first_notified - timedelta(days=1)
        if first_notified
        else monitor.now_utc() - timedelta(days=monitor.BUTTON_CONTEXT_DAYS)
    )
    evidence = []
    collections = (
        state.get("button_contexts", {}).values(),
        state.get("pending_posts", {}).values(),
    )
    for records in collections:
        for record in records:
            if not isinstance(record, dict) or _record_wheel_key(record) != key:
                continue
            observed_at = (
                monitor.parse_datetime(record.get("created_at"))
                or monitor.parse_datetime(record.get("first_seen_at"))
                or monitor.parse_datetime(record.get("message_date"))
            )
            if observed_at and observed_at < oldest_allowed:
                continue
            deadline = _deadline_from_record(record)
            if deadline:
                evidence.append((observed_at or deadline, deadline))

    if not evidence:
        return None
    evidence.sort(key=lambda item: item[0], reverse=True)
    return evidence[0][1]


def mark_participating_with_tracking(state, context):
    """Keep a participated wheel tracked even when its page timer is unavailable."""
    _original_mark_participating(state, context)

    key = _record_wheel_key(context)
    if not key:
        return
    current = monitor.now_utc()
    deadline = _deadline_from_record(context)
    url = str(context.get("url") or "")
    participant = state.setdefault("participating_wheels", {}).get(key)
    if isinstance(participant, dict) and deadline:
        participant["deadline"] = deadline.isoformat()
        participant["expires_at"] = monitor.participation_expiry(
            deadline, current=current
        ).isoformat()

    active = state.setdefault("active_wheels", {})
    entry = active.get(key)
    if not isinstance(entry, dict):
        created_at = monitor.parse_datetime(context.get("created_at")) or current
        message_date = monitor.parse_datetime(context.get("message_date")) or created_at
        try:
            message_id = int(context.get("message_id", 0) or 0)
        except (TypeError, ValueError):
            message_id = 0
        entry = {
            "identifier": str(context.get("identifier") or key),
            "url": monitor.normalize_url(url) if url else "",
            "source": str(context.get("source") or "неизвестно"),
            "message_id": message_id,
            "message_date": message_date.isoformat(),
            "message_url": str(context.get("message_url") or ""),
            "message_text": str(context.get("message_text") or "")[:4000],
            "status": str(context.get("status") or "tracked"),
            "method": str(context.get("method") or "участие отмечено")[:300],
            "page_excerpt": str(context.get("page_excerpt") or "")[:1200],
            "first_notified_at": created_at.isoformat(),
            "last_notification_at": created_at.isoformat(),
            "last_checked_at": current.isoformat(),
            "expires_at": monitor.participation_expiry(
                deadline, current=current
            ).isoformat(),
            "participating": True,
            "participating_at": current.isoformat(),
        }
        active[key] = entry
    else:
        entry["participating"] = True
        entry["participating_at"] = current.isoformat()

    if deadline and not monitor.parse_datetime(entry.get("deadline")):
        entry["deadline"] = deadline.isoformat()
        entry["expires_at"] = monitor.participation_expiry(
            deadline, current=current
        ).isoformat()


def process_active_wheels_with_draw_alert(state, stats):
    """Send one alert when a known or recovered draw deadline is reached."""
    current = monitor.now_utc()
    sent = state.setdefault("completed_wheel_alerts", {})
    changed = False
    alerts_sent = 0

    for key, entry in list(state.setdefault("active_wheels", {}).items()):
        if not isinstance(entry, dict):
            continue
        normalized = str(key).casefold()
        deadline = _recover_deadline(state, normalized, entry)
        if deadline and not monitor.parse_datetime(entry.get("deadline")):
            entry["deadline"] = deadline.isoformat()
            entry["expires_at"] = monitor.participation_expiry(
                deadline, current=current
            ).isoformat()
            participant = state.get("participating_wheels", {}).get(normalized)
            if isinstance(participant, dict):
                participant["deadline"] = deadline.isoformat()
                participant["expires_at"] = monitor.participation_expiry(
                    deadline, current=current
                ).isoformat()
            changed = True

        if not deadline or current < deadline or normalized in sent:
            continue

        identifier = str(entry.get("identifier") or key)
        source = str(entry.get("source") or "неизвестно")
        url = str(entry.get("url") or "")
        participated = monitor.is_participating(
            state, normalized
        ) or monitor.is_participating(state, identifier)
        markup = (
            {"inline_keyboard": [[{"text": "🎡 Открыть колесо", "url": url}]]}
            if url
            else None
        )
        try:
            monitor.send_message(
                "🎯 <b>Время прокрутки колеса наступило</b>\n\n"
                f"Идентификатор: <code>{html.escape(identifier)}</code>\n"
                f"Источник: @{html.escape(source)}\n"
                f"Ваша отметка участия: {'✅ участвую' if participated else '❌ не отмечена'}\n\n"
                "Колесо уже должно быть прокручено. Откройте страницу и проверьте результат.",
                reply_markup=markup,
            )
        except Exception as exc:
            entry["draw_alert_error"] = f"{type(exc).__name__}: {exc}"[:300]
            changed = True
        else:
            sent[normalized] = {
                "identifier": identifier,
                "url": url,
                "deadline": deadline.isoformat(),
                "notified_at": current.isoformat(),
            }
            entry["draw_alert_sent_at"] = current.isoformat()
            monitor.data_store.increment_stat(stats, source, "draw_time_alerts")
            alerts_sent += 1
            changed = True

    result = _original_process_active_wheels(state, stats)
    result["draw_alerts"] = alerts_sent
    if changed:
        result["changed"] = True
    return result


monitor.assess_new_wheel = assess_new_notification_first
monitor.assess_pending_wheel = assess_pending_notification_first
monitor.mark_participating = mark_participating_with_tracking
monitor.process_active_wheels = process_active_wheels_with_draw_alert

if __name__ == "__main__":
    raise SystemExit(monitor.main())
