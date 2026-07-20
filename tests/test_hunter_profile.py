from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from bbvg.bot import profile

UTC = timezone.utc


def event_key(wheel_key: str, entry: dict) -> str:
    action = entry.get("action_id")
    generation = entry.get("generation_id")
    if generation:
        return f"{wheel_key}#generation:{generation}"
    if action:
        return f"{wheel_key}#action:{action}"
    return wheel_key


def test_manual_and_auto_same_action_are_one_event() -> None:
    stats = {
        "personal_wheel_votes": {
            "one": {
                "actor": "vote_user",
                "wheel_key": "wheel-a",
                "event_key": "wheel-a#action:10",
                "voted_at": "2026-07-18T10:00:00+00:00",
            }
        }
    }
    state = {
        "auto_participation_events": {
            "wheel-a#action:10:2026-07-18T09:59:00+00:00": {
                "wheel_key": "wheel-a",
                "status": "participated",
                "attempted_at": "2026-07-18T09:59:00+00:00",
            }
        }
    }
    events = profile.collect_participation_events(
        stats, state, actor="vote_user", include_auto=True
    )
    assert len(events) == 1
    assert events[0]["event_key"] == "wheel-a#action:10"
    assert events[0]["method"] == "auto"


def test_generation_and_worker_event_identity_are_deduplicated() -> None:
    stats = {
        "personal_wheel_votes": {
            "one": {
                "actor": "vote_user",
                "wheel_key": "wheel-a",
                "event_key": "wheel-a#generation:abc",
                "voted_at": "2026-07-18T10:00:00+00:00",
            }
        }
    }
    state = {
        "auto_participation_events": {
            "wheel-a#event:abc": {
                "wheel_key": "wheel-a",
                "status": "already_participating",
                "attempted_at": "2026-07-18T09:59:00+00:00",
            }
        }
    }
    events = profile.collect_participation_events(
        stats, state, actor="vote_user", include_auto=True
    )
    assert len(events) == 1
    assert events[0]["event_key"] == "wheel-a#id:abc"


def test_profile_rebuilds_counts_streak_and_active_participation() -> None:
    stats = {
        "personal_wheel_votes": {
            str(index): {
                "actor": "vote_user",
                "wheel_key": f"wheel-{index}",
                "event_key": f"wheel-{index}#action:{index}",
                "voted_at": f"2026-07-{17 + index:02d}T12:00:00+00:00",
            }
            for index in range(1, 4)
        }
    }
    state = {
        "active_wheels": {
            "wheel-3": {"action_id": 3},
        },
        "auto_participation_events": {},
    }
    user = {
        "first_seen_at": "2026-07-01T00:00:00+00:00",
        "participating_wheels": {
            "wheel-3#action:3": {"wheel_key": "wheel-3"},
        },
    }
    result = profile.build_profile(
        stats,
        state,
        user,
        actor="vote_user",
        include_auto=False,
        event_key_fn=event_key,
        current=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
    )
    assert result["total"] == 3
    assert result["manual"] == 3
    assert result["auto"] == 0
    assert result["active"] == 1
    assert result["current_streak"] == 3
    assert result["best_streak"] == 3
    assert result["best_month"] == "2026-07"
    assert result["best_month_count"] == 3
    assert result["days_in_bot"] == 19
    assert "🔥 Серия 3 дня" in result["achievements"]


def test_auto_history_is_counted_only_when_requested() -> None:
    state = {
        "auto_participation_events": {
            "wheel-a#action:1:start": {
                "status": "participated",
                "wheel_key": "wheel-a",
                "attempted_at": "2026-07-20T10:00:00+00:00",
            }
        }
    }
    without_auto = profile.collect_participation_events(
        {}, state, actor="vote_user", include_auto=False
    )
    with_auto = profile.collect_participation_events(
        {}, state, actor="vote_user", include_auto=True
    )
    assert without_auto == []
    assert len(with_auto) == 1
    assert with_auto[0]["method"] == "auto"


def test_install_appends_profile_without_reordering_existing_menu() -> None:
    class Base:
        def compact_menu_rows(self, admin: bool):
            return [[{"text": "one"}], [{"text": "two"}]]

        def handle_callback(self, query):
            self.delegated = query.get("data")

    class Mixin:
        pass

    profile.install(Mixin)

    class Runtime(Mixin, Base):
        current_user_id = "1"

        def _prepare_callback_user(self, query):
            self.prepared = True

        def answer(self, query_id, text):
            self.answered = (query_id, text)

        def show_profile(self):
            self.shown = True

    runtime = Runtime()
    rows = runtime.compact_menu_rows(False)
    assert [row[0]["text"] for row in rows] == ["one", "two", "👤 Мой профиль"]

    runtime.handle_callback({"id": "q", "data": "page:profile"})
    assert runtime.prepared is True
    assert runtime.shown is True

    runtime.handle_callback({"data": "other"})
    assert runtime.delegated == "other"
