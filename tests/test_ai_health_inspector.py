from __future__ import annotations

import json
from pathlib import Path

from bbvg.ai_core import AIClient, AIConfig, FEATURE_HEALTH_INSPECTOR
from bbvg.health_inspector import admin_note, inspect, rules_assessment, safe_ai_input


def config(path: Path, *, enabled: bool) -> AIConfig:
    return AIConfig(
        enabled=enabled,
        enabled_features=frozenset({FEATURE_HEALTH_INSPECTOR}),
        provider="openai",
        model="test-model",
        timeout_seconds=5,
        max_calls_per_minute=10,
        cache_ttl_seconds=300,
        max_decisions=50,
        state_path=path,
        api_key="test-key",
    )


def critical_finding() -> dict:
    return {
        "kind": "monitor_stale",
        "severity": "critical",
        "title": "Монитор давно не обновлялся",
        "detail": "Последняя итерация была 25 минут назад.",
    }


def test_rules_assessment_is_authoritative() -> None:
    result = rules_assessment(
        {"monitor": {"checked_sources": 10, "reachable_sources": 0, "source_errors": 10}},
        [critical_finding()],
    )
    assert result["severity"] == "critical"
    assert result["requires_human_attention"] is True
    assert "monitor workflow" in result["recommended_action"]


def test_disabled_ai_returns_rules_fallback_without_provider_call(tmp_path: Path) -> None:
    calls = []
    client = AIClient(
        config(tmp_path / "ai.json", enabled=False),
        transport=lambda *_: calls.append(True) or "unexpected",
    )
    result = inspect(
        {"monitor": {"checked_sources": 10, "reachable_sources": 10, "source_errors": 0}},
        [],
        client=client,
    )
    assert result["mode"] == "rules"
    assert result["ai_status"] == "disabled"
    assert result["severity"] == "ok"
    assert calls == []


def test_ai_cannot_downgrade_deterministic_critical_severity(tmp_path: Path) -> None:
    client = AIClient(
        config(tmp_path / "ai.json", enabled=True),
        transport=lambda *_: json.dumps(
            {
                "summary": "Всё отлично",
                "impact": "Проблем нет",
                "recommended_action": "Ничего не делать",
                "confidence": 0.99,
                "severity": "ok",
            },
            ensure_ascii=False,
        ),
    )
    result = inspect(
        {"monitor": {"checked_sources": 10, "reachable_sources": 0, "source_errors": 10}},
        [critical_finding()],
        client=client,
    )
    assert result["mode"] == "ai"
    assert result["severity"] == "critical"
    assert result["requires_human_attention"] is True
    assert admin_note(result)


def test_ai_input_uses_only_whitelisted_diagnostic_fields() -> None:
    rules = rules_assessment({}, [critical_finding()])
    payload = safe_ai_input(
        {
            "monitor": {"checked_sources": 1, "reachable_sources": 1},
            "secret_token": "must-not-leak",
            "chat_id": "12345",
            "users": {"owner": {"name": "private"}},
        },
        [critical_finding()],
        rules,
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "must-not-leak" not in serialized
    assert "12345" not in serialized
    assert "private" not in serialized


def test_admin_note_is_only_for_critical() -> None:
    assert admin_note({"severity": "ok"}) == ""
    assert admin_note({"severity": "warning"}) == ""
