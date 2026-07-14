from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import monitor
import monitor_data as data_store
import monitor_resilience


monitor_resilience.install(monitor)

ROOT = Path(__file__).resolve().parent
ACTIVE_PATH = ROOT / "public_sources.txt"
CATALOG_PATH = ROOT / "source_catalog.txt"
DISCOVERY_STATE_PATH = ROOT / "discovery_state.json"

LOOKBACK_HOURS = max(12, int(os.getenv("DISCOVERY_LOOKBACK_HOURS", "48")))
HISTORY_PAGES = max(1, min(8, int(os.getenv("DISCOVERY_PAGES", "4"))))
MANUAL_RUN = os.getenv("MANUAL_RUN", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def fetch_public_channel_page(
    username: str,
    before: int | None = None,
) -> list[monitor.Message]:
    url = f"https://t.me/s/{username}"
    if before is not None:
        url += f"?before={before}"

    response = monitor.request_with_retries(
        "GET",
        url,
        attempts=2,
        timeout=monitor.REQUEST_TIMEOUT,
        headers={"User-Agent": monitor.USER_AGENT},
        allow_redirects=True,
    )
    response.raise_for_status()
    soup = monitor.BeautifulSoup(response.text, "html.parser")
    result: list[monitor.Message] = []

    for node in soup.select("div.tgme_widget_message[data-post]"):
        data_post = str(node.get("data-post") or "")
        if "/" not in data_post:
            continue
        source, message_id_text = data_post.rsplit("/", 1)
        try:
            message_id = int(message_id_text)
        except ValueError:
            continue

        parts: list[str] = []
        text_node = node.select_one("div.tgme_widget_message_text")
        if text_node is not None:
            parts.append(text_node.get_text("\n", strip=True))
        for anchor in node.select("a[href]"):
            href = html.unescape(str(anchor.get("href") or "")).strip()
            if href:
                parts.append(href)

        time_node = node.select_one("time[datetime]")
        try:
            date = (
                datetime.fromisoformat(str(time_node.get("datetime")))
                if time_node
                else monitor.now_utc()
            )
        except ValueError:
            date = monitor.now_utc()
        if date.tzinfo is None:
            date = date.replace(tzinfo=monitor.UTC)

        result.append(
            monitor.Message(
                source=source or username,
                message_id=message_id,
                date=date,
                text="\n".join(dict.fromkeys(part for part in parts if part)),
                message_url=f"https://t.me/{source or username}/{message_id}",
            )
        )
    return sorted(result, key=lambda item: item.message_id)


def fetch_public_channel_history(username: str) -> list[monitor.Message]:
    messages: dict[int, monitor.Message] = {}
    before: int | None = None
    for _ in range(HISTORY_PAGES):
        page = fetch_public_channel_page(username, before)
        if not page:
            break
        for message in page:
            messages[message.message_id] = message
        next_before = min(message.message_id for message in page)
        if before == next_before:
            break
        before = next_before
    return sorted(messages.values(), key=lambda item: item.message_id)


def load_discovery_state() -> dict:
    try:
        state = json.loads(DISCOVERY_STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    state.setdefault("version", 2)
    state.setdefault("sources", {})
    state.setdefault("notified_wheels", {})
    return state


def save_discovery_state(state: dict) -> None:
    cutoff = monitor.now_utc() - timedelta(days=180)
    state["notified_wheels"] = {
        key: value
        for key, value in state.get("notified_wheels", {}).items()
        if not isinstance(value, dict)
        or (parsed := monitor.parse_datetime(value.get("notified_at"))) is None
        or parsed >= cutoff
    }
    DISCOVERY_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip().lstrip("@")
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        result.append(clean)
    return result


def notification_key(message: monitor.Message, link: str) -> str:
    return f"{message.source.casefold()}:{message.message_id}:{monitor.wheel_key(link)}"


def main() -> int:
    try:
        monitor.validate_environment()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    state = load_discovery_state()
    health = data_store.load_health()
    stats = data_store.load_stats()
    primary_sources = data_store.operational_sources(monitor.read_list(ACTIVE_PATH), "fast")
    catalog_sources = data_store.operational_sources(monitor.read_list(CATALOG_PATH), "nightly")
    sources = unique(catalog_sources)
    primary_keys = {value.casefold() for value in primary_sources}
    sources = [value for value in sources if value.casefold() not in primary_keys]

    cutoff = monitor.now_utc() - timedelta(hours=LOOKBACK_HOURS)
    checked = 0
    errors = 0
    new_wheels = 0
    source_rows = state.setdefault("sources", {})

    for source in sources:
        checked += 1
        source_row = source_rows.setdefault(source, {})
        source_row["last_checked_at"] = monitor.now_utc().isoformat()
        try:
            messages = fetch_public_channel_history(source)
        except Exception as exc:
            errors += 1
            detail = f"{type(exc).__name__}: {exc}"
            source_row["status"] = "error"
            source_row["last_error"] = detail[:500]
            data_store.record_source_problem(health, source, "error", detail)
            data_store.record_source_check_stats(stats, source, "error")
            continue

        source_row["status"] = "ok"
        source_row["last_messages_count"] = len(messages)
        source_row.pop("last_error", None)
        data_store.record_source_success(health, source, len(messages))
        data_store.record_source_check_stats(stats, source, "ok", len(messages))

        for message in messages:
            if message.date.astimezone(monitor.UTC) < cutoff:
                continue
            for link in monitor.extract_links(message.text):
                key = notification_key(message, link)
                if key in state["notified_wheels"]:
                    continue
                assessment = monitor.assess_new_wheel(message, link)
                if not assessment.should_notify:
                    continue
                monitor.notify_new_link(
                    message,
                    link,
                    assessment.deadline,
                    assessment.method,
                    monitor.load_identifier_sources(),
                )
                state["notified_wheels"][key] = {
                    "notified_at": monitor.now_utc().isoformat(),
                    "source": source,
                    "message_url": message.message_url,
                    "url": monitor.normalize_url(link),
                }
                data_store.mark_unique_wheel_post(stats, source, key, monitor.wheel_key(link))
                new_wheels += 1

    state["last_run_at"] = monitor.now_utc().isoformat()
    state["last_run_summary"] = {
        "sources": len(sources),
        "checked": checked,
        "errors": errors,
        "new_wheels": new_wheels,
    }
    save_discovery_state(state)
    data_store.save_health(health)
    data_store.save_stats(stats)

    print(
        f"Nightly sources: {len(sources)}; checked: {checked}; "
        f"errors: {errors}; new wheels: {new_wheels}"
    )
    if MANUAL_RUN:
        monitor.send_message(
            "🌙 <b>Ночная проверка завершена</b>\n\n"
            f"Источников: {len(sources)}\n"
            f"Проверено: {checked}\n"
            f"Ошибок: {errors}\n"
            f"Новых колёс: {new_wheels}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
