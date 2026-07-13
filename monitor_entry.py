from __future__ import annotations

import html
from datetime import timedelta

import monitor
import notification_router

notification_router.install(monitor)

_original_assess_new = monitor.assess_new_wheel
_original_assess_pending = monitor.assess_pending_wheel
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


def process_active_wheels_with_draw_alert(state, stats):
    """Send one alert when a known draw deadline is reached, then run normal cleanup."""
    current = monitor.now_utc()
    sent = state.setdefault("completed_wheel_alerts", {})
    for key, entry in list(state.setdefault("active_wheels", {}).items()):
        if not isinstance(entry, dict):
            continue
        deadline = monitor.parse_datetime(entry.get("deadline"))
        if not deadline or current < deadline:
            continue
        normalized = str(key).casefold()
        if normalized in sent:
            continue
        identifier = str(entry.get("identifier") or key)
        source = str(entry.get("source") or "неизвестно")
        url = str(entry.get("url") or "")
        participated = monitor.is_participating(state, key) or monitor.is_participating(state, identifier)
        markup = {"inline_keyboard": [[{"text": "🎡 Открыть колесо", "url": url}]]} if url else None
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
        else:
            sent[normalized] = {
                "identifier": identifier,
                "url": url,
                "deadline": deadline.isoformat(),
                "notified_at": current.isoformat(),
            }
            entry["draw_alert_sent_at"] = current.isoformat()
            monitor.data_store.increment_stat(stats, source, "draw_time_alerts")
    result = _original_process_active_wheels(state, stats)
    result["draw_alerts"] = sum(
        1 for value in sent.values()
        if isinstance(value, dict) and monitor.parse_datetime(value.get("notified_at"))
        and current - monitor.parse_datetime(value.get("notified_at")) < timedelta(minutes=10)
    )
    return result


monitor.assess_new_wheel = assess_new_notification_first
monitor.assess_pending_wheel = assess_pending_notification_first
monitor.process_active_wheels = process_active_wheels_with_draw_alert

if __name__ == "__main__":
    raise SystemExit(monitor.main())
