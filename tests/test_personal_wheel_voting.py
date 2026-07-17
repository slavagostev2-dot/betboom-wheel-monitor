from __future__ import annotations

from datetime import datetime, timezone

import pytest

import bbvg_monitor_main
import personal_wheel_voting
from bbvg.bot import runtime as bot_runtime


UTC = timezone.utc


def test_user_and_admin_weights_credit_every_source_once() -> None:
    stats = {"version": 1, "sources": {}, "daily": {}}
    user = personal_wheel_voting.actor_vote_token("100", secret="test-secret")
    admin = personal_wheel_voting.actor_vote_token("200", secret="test-secret")
    event = "wheel-a#action:10"
    assert personal_wheel_voting.record_personal_vote(
        stats,
        event_key=event,
        sources=["first", "second", "first"],
        actor=user,
        role="user",
        weight=1,
        at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
    )
    assert personal_wheel_voting.record_personal_vote(
        stats,
        event_key=event,
        sources=["first", "second"],
        actor=admin,
        role="admin",
        weight=5,
        at=datetime(2026, 7, 16, 12, 1, tzinfo=UTC),
    )
    assert stats["sources"]["first"]["quality_score"] == 6
    assert stats["sources"]["second"]["quality_score"] == 6


def test_same_actor_is_idempotent_per_action_id() -> None:
    stats = {"version": 1, "sources": {}, "daily": {}}
    actor = personal_wheel_voting.actor_vote_token("100", secret="test-secret")
    kwargs = {
        "event_key": "wheel-a#action:10",
        "sources": ["first"],
        "actor": actor,
        "role": "user",
        "weight": 1,
        "at": datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
    }
    assert personal_wheel_voting.record_personal_vote(stats, **kwargs)
    assert not personal_wheel_voting.record_personal_vote(stats, **kwargs)
    assert stats["sources"]["first"]["quality_score"] == 1


def test_new_action_id_is_a_new_vote_event() -> None:
    stats = {"version": 1, "sources": {}, "daily": {}}
    actor = personal_wheel_voting.actor_vote_token("100", secret="test-secret")
    for action_id in (10, 11):
        assert personal_wheel_voting.record_personal_vote(
            stats,
            event_key=f"wheel-a#action:{action_id}",
            sources=["first"],
            actor=actor,
            role="user",
            weight=1,
            at=datetime(2026, 7, 16, 12, action_id, tzinfo=UTC),
        )
    assert stats["sources"]["first"]["quality_score"] == 2


def test_actor_token_never_contains_telegram_id() -> None:
    token = personal_wheel_voting.actor_vote_token("123456789", secret="test-secret")
    assert "123456789" not in token
    assert personal_wheel_voting.ACTOR_TOKEN_RE.fullmatch(token)


def test_reminder_event_key_does_not_reuse_old_action() -> None:
    old = personal_wheel_voting.wheel_event_key("wheel-a", {"action_id": 10})
    new = personal_wheel_voting.wheel_event_key("wheel-a", {"action_id": 11})
    assert old != new


def test_bot_token_is_not_accepted_as_state_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert bot_runtime.PersonalWheelVotingMixin is personal_wheel_voting.PersonalWheelVotingMixin
    monkeypatch.delenv("BOT_STATE_KEY", raising=False)
    monkeypatch.setenv("BOT_TOKEN", "bot-token-must-not-be-used")
    with pytest.raises(RuntimeError, match="BOT_STATE_KEY"):
        personal_wheel_voting.actor_vote_token("100")


def test_rating_reset_removes_scores_but_preserves_operations() -> None:
    stats = {
        "version": 1,
        "source_rating_epoch_day": "2026-07-14",
        "admin_wheel_decisions": {"old": {"decision": "confirmed"}},
        "personal_wheel_votes": {"old": {"weight": 5}},
        "sources": {
            "source": {
                "checks": 100,
                "messages_scanned": 2000,
                "recent_post_keys": {"post": {"wheel": "wheel-a"}},
                "wheel_posts": 7,
                "quality_score": 46,
                "quality_decisions": {"old": 40},
                "personal_vote_points": {"vote": 6},
                "personal_vote_score": 6,
                "personal_votes": 2,
                "user_votes": 1,
                "admin_votes": 1,
            }
        },
        "daily": {
            "2026-07-16": {
                "totals": {
                    "checks": 100,
                    "wheel_posts": 7,
                    "personal_vote_points": 6,
                },
                "sources": {
                    "source": {
                        "checks": 100,
                        "wheel_posts": 7,
                        "personal_vote_points": 6,
                    }
                },
            }
        },
    }

    changed = bbvg_monitor_main.reset_source_rating_epoch(
        stats,
        at=datetime(2026, 7, 17, 2, 0, tzinfo=UTC),
    )

    assert changed is True
    assert stats["source_rating_epoch_day"] == "2026-07-17"
    assert stats["source_rating_policy"] == "personal_votes_v1"
    assert "admin_wheel_decisions" not in stats
    assert "personal_wheel_votes" not in stats
    assert stats["sources"]["source"]["checks"] == 100
    assert stats["sources"]["source"]["messages_scanned"] == 2000
    assert stats["sources"]["source"]["recent_post_keys"] == {
        "post": {"wheel": "wheel-a"}
    }
    for field in bbvg_monitor_main.SOURCE_RATING_RESET_FIELDS:
        assert field not in stats["sources"]["source"]
        assert field not in stats["daily"]["2026-07-16"]["totals"]
        assert field not in stats["daily"]["2026-07-16"]["sources"]["source"]
    assert bbvg_monitor_main.reset_source_rating_epoch(stats) is False
