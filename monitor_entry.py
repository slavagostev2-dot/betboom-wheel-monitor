from __future__ import annotations

from datetime import timedelta

import monitor
import notification_router

notification_router.install(monitor)

_original_assess_pending = monitor.assess_pending_wheel


def assess_pending_with_recovery(message, link, state=None):
    result = _original_assess_pending(message, link, state)
    if (
        not result.should_notify
        and result.status not in {"inactive", "active"}
        and monitor.message_age(message) <= timedelta(minutes=30)
    ):
        return monitor.WheelAssessment(
            True,
            result.deadline,
            f"страховочное уведомление для свежего поста; {result.method}",
            "fresh_unconfirmed",
            result.page_excerpt,
        )
    return result


monitor.assess_pending_wheel = assess_pending_with_recovery

if __name__ == "__main__":
    raise SystemExit(monitor.main())
