from pathlib import Path


# Replace the old forever-dedup test with generation-aware scenarios.
path = Path("tests/test_recurring_event_hotfix.py")
text = path.read_text(encoding="utf-8")
start = text.index("    def test_same_action_id_never_repeats_even_after_link_window(self) -> None:\n")
end = text.index("    def test_new_action_id_releases_old_timer_immediately", start)
replacement = '''    def test_same_action_id_and_same_server_start_is_duplicate(self) -> None:
        runtime = bbvg_monitor_main.monitor
        current = datetime.now(UTC)
        server_start = current - timedelta(hours=1)
        message = runtime.Message(
            source="collector",
            message_id=200,
            date=current,
            text="https://betboom.ru/freestream/reused",
            message_url="https://telegram.me/collector/200",
        )
        state = {
            "active_wheels": {},
            "inactive_wheels": {},
            "recently_completed_wheels": {},
            "wheel_action_history": {
                "reused": {
                    "action_id": 100,
                    "server_start_at": server_start.isoformat(),
                    "generation_id": wheel_event_runtime.generation_id(
                        "reused", 100, server_start
                    ),
                    "state": "closed",
                    "seen_at": current.isoformat(),
                    "closed_at": current.isoformat(),
                }
            },
        }
        original_inspector = runtime.inspect_wheel_page
        runtime.inspect_wheel_page = lambda url: runtime.WheelInspection(
            "active",
            current + timedelta(hours=1),
            "confirmed",
            action_id=100,
            verification_status=runtime.WHEEL_VERIFICATION_CONFIRMED,
            server_start_at=server_start,
        )
        try:
            result = runtime.assess_new_wheel(
                message, "https://betboom.ru/freestream/reused", state
            )
        finally:
            runtime.inspect_wheel_page = original_inspector
        self.assertFalse(result.should_notify)
        self.assertEqual(result.status, "duplicate_action")

    def test_same_action_id_with_new_server_start_opens_new_generation(self) -> None:
        runtime = bbvg_monitor_main.monitor
        current = datetime.now(UTC)
        old_start = current - timedelta(days=1)
        new_start = current - timedelta(minutes=5)
        message = runtime.Message(
            source="creator",
            message_id=201,
            date=current,
            text="https://betboom.ru/freestream/reused",
            message_url="https://telegram.me/creator/201",
        )
        state = {
            "active_wheels": {},
            "inactive_wheels": {},
            "recently_completed_wheels": {
                "reused": {
                    "action_id": 100,
                    "server_start_at": old_start.isoformat(),
                    "generation_id": wheel_event_runtime.generation_id(
                        "reused", 100, old_start
                    ),
                    "removed_at": (current - timedelta(hours=12)).isoformat(),
                }
            },
            "wheel_action_history": {
                "reused": {
                    "action_id": 100,
                    "server_start_at": old_start.isoformat(),
                    "generation_id": wheel_event_runtime.generation_id(
                        "reused", 100, old_start
                    ),
                    "state": "closed",
                    "seen_at": (current - timedelta(hours=12)).isoformat(),
                    "closed_at": (current - timedelta(hours=12)).isoformat(),
                }
            },
            "participating_wheels": {"reused": {"marked_at": old_start.isoformat()}},
            "url_alerts": {"reused": {"alerted_at": old_start.isoformat()}},
            "activation_alerts": {},
            "manual_deadlines": {},
            "manual_overrides": {},
            "wheel_publications": {"reused": [{"source": "old"}]},
        }
        original_inspector = runtime.inspect_wheel_page
        runtime.inspect_wheel_page = lambda url: runtime.WheelInspection(
            "active",
            current + timedelta(hours=1),
            "confirmed",
            action_id=100,
            verification_status=runtime.WHEEL_VERIFICATION_CONFIRMED,
            server_start_at=new_start,
        )
        try:
            result = runtime.assess_new_wheel(
                message, "https://betboom.ru/freestream/reused", state
            )
        finally:
            runtime.inspect_wheel_page = original_inspector
        self.assertTrue(result.should_notify)
        self.assertEqual(result.action_id, 100)
        self.assertEqual(result.server_start_at, new_start)
        self.assertNotIn("reused", state["participating_wheels"])
        self.assertNotIn("reused", state["wheel_publications"])
        self.assertNotIn("reused", state["recently_completed_wheels"])

'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")

# Generation IDs split personal participation/rating even when action_id is reused.
path = Path("tests/test_personal_wheel_voting.py")
text = path.read_text(encoding="utf-8")
marker = "def test_new_action_id_is_a_new_vote_event() -> None:\n"
addition = '''def test_same_action_id_new_generation_is_a_new_vote_event() -> None:
    first = personal_wheel_voting.wheel_event_key(
        "wheel-a", {"action_id": 10, "generation_id": "generation-one"}
    )
    second = personal_wheel_voting.wheel_event_key(
        "wheel-a", {"action_id": 10, "generation_id": "generation-two"}
    )
    assert first != second

    stats = {"version": 1, "sources": {}, "daily": {}}
    actor = personal_wheel_voting.actor_vote_token("100", secret="test-secret")
    for event in (first, second):
        assert personal_wheel_voting.record_personal_vote(
            stats,
            event_key=event,
            sources=["first"],
            actor=actor,
            role="user",
            weight=1,
            at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        )
    assert stats["sources"]["first"]["quality_score"] == 2


'''
if addition not in text:
    if marker not in text:
        raise RuntimeError("personal vote test marker missing")
    text = text.replace(marker, addition + marker, 1)
path.write_text(text, encoding="utf-8")
