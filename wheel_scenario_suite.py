from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import monitor
import restart_duplicate_guard
import wheel_link_lifecycle


UTC = timezone.utc
LINK = "https://betboom.ru/freestream/scenario?utm_source=test"
PLAIN_LINK = "https://betboom.ru/freestream/scenario"
KEY = "scenario"


def message(source: str, message_id: int, at: datetime) -> monitor.Message:
    return monitor.Message(
        source=source,
        message_id=message_id,
        date=at,
        text=f"Колесо {LINK}",
        message_url=f"https://telegram.me/{source}/{message_id}",
    )


def timed_state(start: datetime, deadline: datetime) -> dict[str, Any]:
    return {
        "active_wheels": {
            KEY: {
                "identifier": KEY,
                "url": PLAIN_LINK,
                "source": "official",
                "message_id": 10,
                "message_date": start.isoformat(),
                "message_url": "https://telegram.me/official/10",
                "first_notified_at": start.isoformat(),
                "deadline": deadline.isoformat(),
            }
        },
        "wheel_publications": {
            KEY: [
                {
                    "source": "official",
                    "message_id": 10,
                    "message_date": start.isoformat(),
                    "message_url": "https://telegram.me/official/10",
                }
            ]
        },
        "url_alerts": {
            KEY: {
                "alerted_at": start.isoformat(),
                "deadline": deadline.isoformat(),
                "suppress_until": deadline.isoformat(),
            }
        },
    }


def self_test() -> None:
    start = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    deadline = start + timedelta(hours=3)

    # 1. URL normalization: UTM and plain URL are one wheel identity.
    assert monitor.wheel_key(LINK) == monitor.wheel_key(PLAIN_LINK) == KEY

    # 2. The exact Telegram publication remains a duplicate after a restart.
    state = timed_state(start, deadline)
    assert restart_duplicate_guard.publication_already_known(
        monitor, state, message("official", 10, start), LINK
    )

    # 3. A forwarded/reposted publication with another message id is still the
    # same active link while its timer is running.
    forwarded = message("collector", 501, start + timedelta(hours=1))
    assert not restart_duplicate_guard.publication_already_known(
        monitor, state, forwarded, LINK
    )
    during_timer = wheel_link_lifecycle.link_window(
        state,
        KEY,
        current=start + timedelta(hours=1),
        parser=monitor.parse_datetime,
    )
    assert during_timer.blocked and during_timer.source == "timer"

    # 4. A new publication after the timer is allowed as a new event.
    after_timer = wheel_link_lifecycle.link_window(
        state,
        KEY,
        current=deadline + timedelta(seconds=1),
        parser=monitor.parse_datetime,
    )
    assert not after_timer.blocked
    rotated = wheel_link_lifecycle.rotate_expired_event(
        state,
        KEY,
        current=deadline + timedelta(seconds=1),
        block_until=deadline,
    )
    assert rotated and KEY not in state["active_wheels"]

    # 5. No timer: same link at 30 and 119 minutes is a duplicate.
    untimed = {
        "active_wheels": {
            KEY: {
                "identifier": KEY,
                "url": PLAIN_LINK,
                "first_notified_at": start.isoformat(),
            }
        },
        "url_alerts": {KEY: {"alerted_at": start.isoformat()}},
    }
    for elapsed in (30, 119):
        window = wheel_link_lifecycle.link_window(
            untimed,
            KEY,
            current=start + timedelta(minutes=elapsed),
            parser=monitor.parse_datetime,
        )
        assert window.blocked and window.source == "no_timer"

    # 6. No timer: a genuinely new publication after two hours is allowed.
    after_two_hours = wheel_link_lifecycle.link_window(
        untimed,
        KEY,
        current=start + timedelta(minutes=121),
        parser=monitor.parse_datetime,
    )
    assert not after_two_hours.blocked

    # 7. A manual deadline replaces the two-hour rule and has priority.
    manual_deadline = start + timedelta(hours=5)
    manual = {
        "active_wheels": {
            KEY: {
                "identifier": KEY,
                "first_notified_at": start.isoformat(),
            }
        },
        "url_alerts": {KEY: {"alerted_at": start.isoformat()}},
        "manual_deadlines": {
            KEY: {
                "deadline": manual_deadline.isoformat(),
                "updated_at": (start + timedelta(hours=1)).isoformat(),
            }
        },
    }
    manual_window = wheel_link_lifecycle.link_window(
        manual,
        KEY,
        current=start + timedelta(hours=3),
        parser=monitor.parse_datetime,
    )
    assert manual_window.blocked and manual_window.source == "manual_timer"
    after_manual = wheel_link_lifecycle.link_window(
        manual,
        KEY,
        current=manual_deadline + timedelta(seconds=1),
        parser=monitor.parse_datetime,
    )
    assert not after_manual.blocked

    # 8. Setting a manual deadline updates the persisted suppression window.
    persisted: dict[str, Any] = {
        "url_alerts": {KEY: {"alerted_at": start.isoformat()}}
    }
    wheel_link_lifecycle.apply_manual_deadline(
        persisted,
        KEY,
        manual_deadline,
        current=start + timedelta(minutes=40),
    )
    assert persisted["url_alerts"][KEY]["suppress_until"] == manual_deadline.isoformat()
    assert persisted["url_alerts"][KEY]["lifecycle_rule"] == "manual_timer"

    # 9. New event rotation cannot inherit participation or old publications.
    reusable = {
        "active_wheels": {
            KEY: {
                "identifier": KEY,
                "first_notified_at": start.isoformat(),
            }
        },
        "participating_wheels": {KEY: {"marked_at": start.isoformat()}},
        "wheel_publications": {
            KEY: [{"source": "official", "message_id": 10}]
        },
        "url_alerts": {KEY: {"alerted_at": start.isoformat()}},
    }
    wheel_link_lifecycle.rotate_expired_event(
        reusable,
        KEY,
        current=start + timedelta(hours=3),
        block_until=start + timedelta(hours=2),
    )
    assert KEY not in reusable["participating_wheels"]
    assert KEY not in reusable["wheel_publications"]
    assert reusable["recently_completed_wheels"][KEY]["completion_reason"] == (
        "link_reuse_window_expired"
    )

    # 10. Different wheel identifiers never suppress one another.
    other = "https://betboom.ru/freestream/scenario-2"
    assert monitor.wheel_key(other) != KEY

    print("BB V.G. wheel scenario suite passed: 10 scenarios")


if __name__ == "__main__":
    self_test()
