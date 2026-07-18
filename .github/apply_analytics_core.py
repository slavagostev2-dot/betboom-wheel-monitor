from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"marker missing in {path}: {old[:80]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "monitor_entry.py",
    '''    # Most wheel posts contain one identifier. Replacing reposts with the
    # canonical message makes deadline inference, source attribution and
    # duplicate keys consistently use the original publication.
    for source, messages in list(messages_by_source.items()):
        rewritten: list[monitor.Message] = []
        seen_messages: set[tuple[str, int]] = set()
        for message in messages:
            wheel_keys = {
                monitor.wheel_key(link)
                for link in monitor.extract_links(message.text)
            }
            canonical = (
                _CANONICAL_MESSAGES.get(next(iter(wheel_keys)))
                if len(wheel_keys) == 1
                else None
            )
            selected = canonical or message
            marker = (selected.source.casefold(), selected.message_id)
            if marker in seen_messages:
                continue
            seen_messages.add(marker)
            rewritten.append(selected)
        messages_by_source[source] = rewritten
''',
    '''    # Preserve original messages in each source stream. Assessment wrappers
    # still use the canonical publication for API/deadline semantics, while
    # statistics and wheel_publications retain every posting channel.
    for source, messages in list(messages_by_source.items()):
        rewritten: list[monitor.Message] = []
        seen_messages: set[tuple[str, int]] = set()
        for message in messages:
            marker = (message.source.casefold(), message.message_id)
            if marker in seen_messages:
                continue
            seen_messages.add(marker)
            rewritten.append(message)
        messages_by_source[source] = rewritten
''',
)

helper = '''


def reconcile_personal_vote_sources(
    data: dict[str, Any],
    *,
    event_key: str,
    sources: list[str],
    at: datetime | None = None,
) -> int:
    """Credit newly discovered sources for existing votes on one event."""

    targets: list[str] = []
    seen: set[str] = set()
    for source in sources:
        cleaned = _clean_source(source)
        folded = cleaned.casefold()
        if cleaned and folded not in seen:
            seen.add(folded)
            targets.append(cleaned)
    votes = data.get("personal_wheel_votes")
    if not targets or not isinstance(votes, dict):
        return 0

    current = (at or datetime.now(UTC)).astimezone(UTC)
    changed_pairs = 0
    for vote_id, raw_vote in votes.items():
        if not isinstance(raw_vote, dict):
            continue
        try:
            payload = normalize_vote_payload(raw_vote)
        except (TypeError, ValueError):
            continue
        if payload["event_key"] != _clean_wheel_key(event_key):
            continue
        known = {source.casefold() for source in payload["sources"]}
        missing = [source for source in targets if source.casefold() not in known]
        if not missing:
            continue

        raw_vote["sources"] = payload["sources"] + missing
        try:
            voted = datetime.fromisoformat(
                str(raw_vote.get("voted_at") or "").replace("Z", "+00:00")
            )
            voted = voted.astimezone(UTC) if voted.tzinfo else voted.replace(tzinfo=UTC)
        except ValueError:
            voted = current
        day = voted.date().isoformat()
        daily = data.setdefault("daily", {}).setdefault(
            day, {"sources": {}, "totals": {}}
        )
        totals = daily.setdefault("totals", {})
        metric = "admin_votes" if payload["role"] in {"admin", "owner"} else "user_votes"

        for source in missing:
            entry = data.setdefault("sources", {}).setdefault(source, {})
            points = entry.setdefault("personal_vote_points", {})
            if str(vote_id) in points:
                continue
            points[str(vote_id)] = payload["weight"]
            score = sum(max(0, int(value or 0)) for value in points.values())
            entry["personal_vote_score"] = score
            entry["quality_score"] = score
            entry["personal_votes"] = int(entry.get("personal_votes", 0) or 0) + 1
            entry[metric] = int(entry.get(metric, 0) or 0) + 1
            entry["last_vote_at"] = voted.isoformat()
            entry["last_updated_at"] = current.isoformat()

            source_day = daily.setdefault("sources", {}).setdefault(source, {})
            source_day["personal_votes"] = int(source_day.get("personal_votes", 0) or 0) + 1
            source_day["personal_vote_points"] = int(
                source_day.get("personal_vote_points", 0) or 0
            ) + payload["weight"]
            source_day[metric] = int(source_day.get(metric, 0) or 0) + 1
            totals["personal_vote_points"] = int(
                totals.get("personal_vote_points", 0) or 0
            ) + payload["weight"]
            changed_pairs += 1
    return changed_pairs
'''
replace_once(
    "personal_wheel_voting.py",
    "\n\ndef record_personal_vote(\n",
    helper + "\n\ndef record_personal_vote(\n",
)

replace_once("bbvg_monitor_main.py", "import personal_wheel_voting\n", "import personal_wheel_voting\nimport json\n")
replace_once(
    "bbvg_monitor_main.py",
    "_original_record_admin_wheel_decision = monitor.data_store.record_admin_wheel_decision\n",
    "_original_record_admin_wheel_decision = monitor.data_store.record_admin_wheel_decision\n_original_save_stats = monitor.data_store.save_stats\n",
)
reconcile = '''


def reconcile_multisource_votes(data: dict[str, Any], state: dict[str, Any]) -> int:
    keys: set[str] = set()
    for name in ("active_wheels", "wheel_action_history"):
        rows = state.get(name)
        if isinstance(rows, dict):
            keys.update(str(key).casefold() for key in rows)
    keys.update(str(key).casefold() for key in runtime.base_runtime._WHEEL_PUBLICATIONS)

    changed = 0
    for key in sorted(keys):
        active = state.get("active_wheels", {}).get(key)
        history = state.get("wheel_action_history", {}).get(key)
        identity = active if isinstance(active, dict) else history if isinstance(history, dict) else {}
        event_key = personal_wheel_voting.wheel_event_key(key, identity)
        sources = wheel_publications_v2.publication_sources(
            state, key, active if isinstance(active, dict) else None
        )
        incoming = runtime.base_runtime._WHEEL_PUBLICATIONS.get(key, [])
        if isinstance(incoming, list):
            sources.extend(
                str(row.get("source") or "").strip().lstrip("@")
                for row in incoming
                if isinstance(row, dict)
            )
        changed += personal_wheel_voting.reconcile_personal_vote_sources(
            data, event_key=event_key, sources=sources, at=monitor.now_utc()
        )
    return changed


def save_stats_with_multisource_reconciliation(data: dict[str, Any]) -> None:
    try:
        state = json.loads(monitor.STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
        changed = reconcile_multisource_votes(data, state)
        if changed:
            print(f"Reconciled multi-source rating pairs: {changed}")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"WARNING multi-source rating reconciliation: {type(exc).__name__}: {exc}")
    _original_save_stats(data)
'''
replace_once(
    "bbvg_monitor_main.py",
    "\n\ndef recover_deadline_manual_first(state: dict, key: str, entry: dict):\n",
    reconcile + "\n\ndef recover_deadline_manual_first(state: dict, key: str, entry: dict):\n",
)
replace_once(
    "bbvg_monitor_main.py",
    "monitor.data_store.record_admin_wheel_decision = record_admin_wheel_decision_additive\n",
    "monitor.data_store.record_admin_wheel_decision = record_admin_wheel_decision_additive\nmonitor.data_store.save_stats = save_stats_with_multisource_reconciliation\n",
)

replace_once(
    "bbvg/bot/sources.py",
    '''_EMPTY_REGISTRY = {
    "version": 2,
    "summary": {
''',
    '''_EMPTY_REGISTRY = {
    "version": 2,
    "generated_at": None,
    "summary": {
''',
)
replace_once(
    "bbvg/bot/sources.py",
    '''    return {
        "version": int(value.get("version", 2) or 2),
        "summary": dict(summary),
        "sources": [dict(row) for row in rows if isinstance(row, dict)],
    }
''',
    '''    return {
        "version": int(value.get("version", 2) or 2),
        "generated_at": str(value.get("generated_at") or "").strip() or None,
        "summary": dict(summary),
        "sources": [dict(row) for row in rows if isinstance(row, dict)],
    }
''',
)
replace_once(
    "bbvg/bot/sources.py",
    '''    return {
        "version": 2,
        "summary": summary,
        "sources": rows,
    }
''',
    '''    generated = max(
        (str(row.get("last_checked_at") or "") for row in rows),
        default=None,
    )
    return {
        "version": 2,
        "generated_at": generated or None,
        "summary": summary,
        "sources": rows,
    }
''',
)

replace_once("tests/test_lifecycle.py", "import monitor\n", "import monitor\nimport monitor_entry\n")
lifecycle_test = '''

class MultiSourceDiscoveryTests(unittest.TestCase):
    def test_source_streams_keep_original_publications(self) -> None:
        current = datetime(2026, 7, 17, 10, 30, tzinfo=UTC)
        link = "https://betboom.ru/freestream/zonertg8"
        first = monitor.Message(
            "mechanogun", 500, current, link, "https://telegram.me/mechanogun/500"
        )
        second = monitor.Message(
            "kolesaBB", 131, current + timedelta(minutes=1), link,
            "https://telegram.me/kolesaBB/131",
        )
        original = monitor_entry._original_fetch_all_sources
        try:
            monitor_entry._original_fetch_all_sources = lambda sources: (
                {"mechanogun": [first], "kolesaBB": [second]}, {}, []
            )
            messages, _, _ = monitor_entry.fetch_all_sources_with_originals(
                ["mechanogun", "kolesaBB"]
            )
        finally:
            monitor_entry._original_fetch_all_sources = original

        self.assertEqual(messages["mechanogun"][0].source, "mechanogun")
        self.assertEqual(messages["kolesaBB"][0].source, "kolesaBB")
        self.assertEqual(
            [row["source"] for row in monitor_entry._WHEEL_PUBLICATIONS["zonertg8"]],
            ["mechanogun", "kolesaBB"],
        )
        self.assertEqual(monitor_entry._CANONICAL_MESSAGES["zonertg8"].source, "mechanogun")
'''
replace_once(
    "tests/test_lifecycle.py",
    "\n\nif __name__ == \"__main__\":\n",
    lifecycle_test + "\n\nif __name__ == \"__main__\":\n",
)

voting_tests = '''


def test_late_second_source_expands_existing_vote_without_duplication() -> None:
    stats = {"version": 1, "sources": {}, "daily": {}}
    actor = personal_wheel_voting.actor_vote_token("100", secret="test-secret")
    event = "zonertg8#action:693"
    at = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    assert personal_wheel_voting.record_personal_vote(
        stats, event_key=event, sources=["mechanogun"], actor=actor,
        role="owner", weight=5, at=at,
    )
    assert personal_wheel_voting.reconcile_personal_vote_sources(
        stats, event_key=event, sources=["mechanogun", "kolesaBB"], at=at,
    ) == 1
    assert personal_wheel_voting.reconcile_personal_vote_sources(
        stats, event_key=event, sources=["mechanogun", "kolesaBB"], at=at,
    ) == 0
    assert stats["sources"]["mechanogun"]["quality_score"] == 5
    assert stats["sources"]["kolesaBB"]["quality_score"] == 5
    assert stats["daily"]["2026-07-17"]["totals"]["personal_votes"] == 1
    assert stats["daily"]["2026-07-17"]["totals"]["personal_vote_points"] == 10


def test_three_votes_credit_both_channels_equally() -> None:
    stats = {"version": 1, "sources": {}, "daily": {}}
    event = "zonertg8#action:693"
    for user_id, role, weight in (("1", "owner", 5), ("2", "admin", 5), ("3", "user", 1)):
        assert personal_wheel_voting.record_personal_vote(
            stats, event_key=event, sources=["mechanogun"],
            actor=personal_wheel_voting.actor_vote_token(user_id, secret="test-secret"),
            role=role, weight=weight, at=datetime(2026, 7, 17, 10, 0, tzinfo=UTC),
        )
    assert personal_wheel_voting.reconcile_personal_vote_sources(
        stats, event_key=event, sources=["mechanogun", "kolesaBB"]
    ) == 3
    assert stats["sources"]["mechanogun"]["quality_score"] == 11
    assert stats["sources"]["kolesaBB"]["quality_score"] == 11
    assert len(stats["personal_wheel_votes"]) == 3
'''
path = Path("tests/test_personal_wheel_voting.py")
text = path.read_text(encoding="utf-8")
if "test_late_second_source_expands_existing_vote_without_duplication" not in text:
    path.write_text(text.rstrip() + voting_tests + "\n", encoding="utf-8")
