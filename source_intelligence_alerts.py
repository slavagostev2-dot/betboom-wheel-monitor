from __future__ import annotations

import html
from typing import Any

from bbvg.monitor import source_discovery


def wheel_candidate_rows(
    state: dict[str, Any],
    known_sources: set[str] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Return only candidates that accumulated enough evidence for admin review."""

    known = {str(value).casefold() for value in (known_sources or set())}
    rows: list[tuple[str, dict[str, Any]]] = []
    candidates = state.get("candidates") if isinstance(state.get("candidates"), dict) else {}
    for key, raw in candidates.items():
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or key).strip().lstrip("@")
        if (
            not source
            or source.casefold().endswith("bot")
            or source.casefold() in known
            or raw.get("recommendation_alerted_at")
            or raw.get("admin_alerted_at")
        ):
            continue
        if raw.get("lifecycle_status") != "recommended":
            continue
        if not raw.get("public"):
            continue
        rows.append((source, raw))
    rows.sort(
        key=lambda item: (
            -int(item[1].get("wheel_links_found", 0) or 0),
            -int(item[1].get("score", 0) or 0),
            -int(item[1].get("observation_runs", 0) or 0),
            item[0].casefold(),
        )
    )
    return rows


def candidate_message(source: str, entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    found = int(entry.get("wheel_links_found", 0) or 0)
    score = int(entry.get("score", 0) or 0)
    latest = str(entry.get("latest_wheel_at") or "не определено")
    observed_days = int(entry.get("observation_days", 0) or 0)
    observation_runs = int(entry.get("observation_runs", 0) or 0)
    reason = str(entry.get("lifecycle_reason") or "накоплены признаки полезного источника")
    samples = entry.get("sample_wheels") if isinstance(entry.get("sample_wheels"), list) else []
    sample = next((row for row in samples if isinstance(row, dict)), {})
    identifier = str(sample.get("identifier") or "")
    message_url = str(sample.get("message_url") or "")

    lines = [
        "🛰️ <b>Рекомендован новый источник</b>",
        "",
        f"Канал: <b>@{html.escape(source)}</b>",
        f"Оценка: <b>{score}/100</b>",
        f"Найдено ссылок на колёса: <b>{found}</b>",
        f"Циклов наблюдения: <b>{observation_runs}</b>",
        f"Дней с первого обнаружения: <b>{observed_days}</b>",
        f"Последнее колесо: <code>{html.escape(latest)}</code>",
        f"Почему рекомендован: {html.escape(reason[:500])}",
    ]
    if identifier:
        lines.append(f"Пример: <code>{html.escape(identifier)}</code>")
    lines.extend(
        [
            "",
            "Автоматическая разведка только рекомендует канал. Решение о включении принимает администратор.",
        ]
    )

    buttons: list[list[dict[str, str]]] = [
        [{"text": "📨 Открыть канал", "url": f"https://telegram.me/{source}"}],
    ]
    if message_url:
        buttons.append([{"text": "🎡 Открыть найденный пост", "url": message_url}])
    buttons.extend(
        [
            [
                {
                    "text": "⚡ В основные",
                    "callback_data": f"intel:mode:fast:{source}",
                },
                {
                    "text": "🌙 В ночное",
                    "callback_data": f"intel:mode:nightly:{source}",
                },
            ],
            [
                {
                    "text": "👁 Продолжить наблюдение",
                    "callback_data": f"intel:defer:{source}",
                },
                {
                    "text": "🙈 Игнорировать",
                    "callback_data": f"intel:ignoreask:{source}",
                },
            ],
        ]
    )
    return "\n".join(lines), {"inline_keyboard": buttons}


def notify_new_candidates(module: Any, state: dict[str, Any]) -> int:
    _, known = module.known_sources()
    sent = 0
    for source, entry in wheel_candidate_rows(state, known):
        text, markup = candidate_message(source, entry)
        response = module.monitor.send_message(text, reply_markup=markup)
        result = response.get("result") if isinstance(response, dict) else None
        delivered = int(result.get("sent", 0) or 0) if isinstance(result, dict) else 0
        if delivered <= 0:
            continue
        timestamp = module.now_iso()
        entry["recommendation_alerted_at"] = timestamp
        entry["admin_alerted_at"] = timestamp
        entry["admin_alert_delivery_count"] = delivered
        sent += 1
    return sent


def run(module: Any) -> int:
    result = module.main()
    if result != 0:
        return result
    state = module.load_state()
    lifecycle_changes = source_discovery.evaluate_state(module, state)
    sent = notify_new_candidates(module, state)
    if lifecycle_changes or sent:
        module.save_state(state)
    summary = state.get("source_discovery_lifecycle", {})
    recommended = int(summary.get("recommended", 0) or 0) if isinstance(summary, dict) else 0
    print(
        f"Source intelligence lifecycle changes: {lifecycle_changes}; "
        f"recommended={recommended}; administrator alerts sent={sent}"
    )
    return 0


def self_test() -> None:
    state = {
        "candidates": {
            "newsource": {
                "source": "NewSource",
                "public": True,
                "wheel_links_found": 2,
                "score": 75,
                "lifecycle_status": "recommended",
                "observation_runs": 3,
                "observation_days": 2,
                "lifecycle_reason": "найдены прямые ссылки на колёса",
                "sample_wheels": [
                    {
                        "identifier": "wheel-a",
                        "message_url": "https://telegram.me/NewSource/10",
                    }
                ],
            },
            "observed": {
                "source": "Observed",
                "public": True,
                "wheel_links_found": 0,
                "score": 50,
                "lifecycle_status": "observed",
            },
            "configured": {
                "source": "Configured",
                "public": True,
                "wheel_links_found": 3,
                "score": 90,
                "lifecycle_status": "recommended",
            },
            "sent": {
                "source": "Sent",
                "public": True,
                "wheel_links_found": 2,
                "score": 90,
                "lifecycle_status": "recommended",
                "recommendation_alerted_at": "now",
            },
        }
    }
    rows = wheel_candidate_rows(state, {"configured"})
    assert [source for source, _ in rows] == ["NewSource"]
    text, markup = candidate_message(*rows[0])
    assert "Рекомендован новый источник" in text
    callbacks = [
        button.get("callback_data")
        for row in markup["inline_keyboard"]
        for button in row
        if button.get("callback_data")
    ]
    assert callbacks == [
        "intel:mode:fast:NewSource",
        "intel:mode:nightly:NewSource",
        "intel:defer:NewSource",
        "intel:ignoreask:NewSource",
    ]
    print("source intelligence lifecycle alert self-test passed")


if __name__ == "__main__":
    self_test()
