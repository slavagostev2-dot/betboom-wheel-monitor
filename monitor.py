from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
SOURCES_PATH = ROOT / "public_sources.txt"
KNOWN_IDS_PATH = ROOT / "known_freestream_ids.txt"

UTC = timezone.utc
MOSCOW = ZoneInfo("Europe/Moscow")
DISPLAY_TZ = ZoneInfo(os.getenv("DISPLAY_TIMEZONE", "Asia/Barnaul"))

REQUEST_TIMEOUT = max(5, int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")))
KNOWN_BATCH_SIZE = max(0, int(os.getenv("KNOWN_BATCH_SIZE", "10")))
URL_DEDUP_MINUTES = max(0, int(os.getenv("URL_DEDUP_MINUTES", "60")))
KNOWN_ACTIVE_ALERT_COOLDOWN_HOURS = max(
    1, int(os.getenv("KNOWN_ACTIVE_ALERT_COOLDOWN_HOURS", "6"))
)
MANUAL_RUN = os.getenv("MANUAL_RUN", "").strip().lower() in {
    "1", "true", "yes", "on"
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)

# The protocol is optional because Telegram posts may display a bare domain.
LINK_RE = re.compile(
    r"(?<![A-Za-z0-9._-])"
    r"(?:https?://)?(?:www\.)?betboom\.ru/freestream/"
    r"[A-Za-z0-9._~-]+",
    re.IGNORECASE,
)

REL_MIN_RE = re.compile(
    r"(?:через|остал(?:ось|ось примерно)?|ещ[её])\s+"
    r"(\d{1,4})\s*мин",
    re.IGNORECASE,
)
REL_HOUR_RE = re.compile(
    r"(?:через|остал(?:ось|ось примерно)?|ещ[её])\s+"
    r"(\d{1,3})\s*(?:час|часа|часов|ч\b)",
    re.IGNORECASE,
)
CLOCK_RE = re.compile(
    r"(?:крутим|прокрут\w*|розыгрыш|старт|колесо)?"
    r"\s*(?:в|—|-)?\s*"
    r"([01]?\d|2[0-3])[:.]([0-5]\d)"
    r"\s*(?:мск|москва|по\s+мск)",
    re.IGNORECASE,
)
DURATION_RE = re.compile(
    r"(?:активн\w*|действ\w*|в\s+течение)\s+"
    r"(\d{1,4})\s*мин",
    re.IGNORECASE,
)
COUNTDOWN_RE = re.compile(
    r"(?:остал\w*|до\s+(?:прокрутки|старта|конца))"
    r"[^0-9]{0,40}"
    r"(?:(\d{1,3})\s*(?:ч|час(?:а|ов)?)\s*)?"
    r"(?:(\d{1,3})\s*(?:м|мин(?:ут[ыа]?)?)\s*)?"
    r"(?:(\d{1,3})\s*(?:с|сек(?:унд[ыа]?)?))?",
    re.IGNORECASE,
)

EXPIRED_PHRASES = (
    "розыгрыш завершен",
    "розыгрыш завершён",
    "колесо завершено",
    "акция завершена",
    "ссылка недействительна",
    "время участия истекло",
    "прием участников завершен",
    "приём участников завершён",
)
ACTIVE_PHRASES = (
    "до прокрутки",
    "до старта колеса",
    "колесо запущено",
    "крутим через",
    "участвовать в колесе",
)


@dataclass(frozen=True)
class Message:
    source: str
    message_id: int
    date: datetime
    text: str
    message_url: str


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def read_list(path: Path) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.split("#", 1)[0].strip().lstrip("@")
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(value)

    return values


def load_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    data.setdefault("version", 2)
    data.setdefault("initialized_sources", [])
    data.setdefault("seen", {})
    data.setdefault("recent_url_alerts", {})
    data.setdefault("known_status", {})
    return data


def save_state(state: dict) -> None:
    seen_cutoff = now_utc() - timedelta(days=180)
    url_cutoff = now_utc() - timedelta(days=14)

    state["seen"] = {
        key: value
        for key, value in state.get("seen", {}).items()
        if (parsed := parse_datetime(value)) is None or parsed >= seen_cutoff
    }
    state["recent_url_alerts"] = {
        key: value
        for key, value in state.get("recent_url_alerts", {}).items()
        if (parsed := parse_datetime(value)) is None or parsed >= url_cutoff
    }

    temp_path = STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(STATE_PATH)


def normalize_url(raw_url: str) -> str:
    cleaned = html.unescape(raw_url).strip().rstrip(".,;:!?)]}\"'")
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = "https://" + cleaned

    parts = urlsplit(cleaned)
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/")
    return urlunsplit(("https", netloc, path, "", ""))


def extract_links(text: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()

    for match in LINK_RE.finditer(text or ""):
        link = normalize_url(match.group(0))
        key = link.casefold()
        if key not in seen:
            seen.add(key)
            links.append(link)

    return links


def request_with_retries(
    method: str,
    url: str,
    *,
    attempts: int = 3,
    **kwargs,
) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = requests.request(method, url, **kwargs)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(
                    f"Temporary HTTP {response.status_code}",
                    response=response,
                )
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))

    assert last_error is not None
    raise last_error


def fetch_public_channel(username: str) -> list[Message]:
    response = request_with_retries(
        "GET",
        f"https://t.me/s/{username}",
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    result: list[Message] = []

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

        # Read every URL in the post. The BetBoom regex filters unrelated links later.
        for anchor in node.select("a[href]"):
            href = html.unescape(str(anchor.get("href") or "")).strip()
            if href:
                parts.append(href)

        time_node = node.select_one("time[datetime]")
        try:
            date = (
                datetime.fromisoformat(str(time_node.get("datetime")))
                if time_node
                else now_utc()
            )
        except ValueError:
            date = now_utc()
        if date.tzinfo is None:
            date = date.replace(tzinfo=UTC)

        result.append(
            Message(
                source=source or username,
                message_id=message_id,
                date=date,
                text="\n".join(dict.fromkeys(part for part in parts if part)),
                message_url=f"https://t.me/{source or username}/{message_id}",
            )
        )

    return sorted(result, key=lambda item: item.message_id)


def infer_deadline(
    text: str,
    published_at: datetime,
) -> tuple[datetime | None, str]:
    match = REL_MIN_RE.search(text)
    if match:
        return (
            published_at + timedelta(minutes=int(match.group(1))),
            "текст поста: относительные минуты",
        )

    match = REL_HOUR_RE.search(text)
    if match:
        return (
            published_at + timedelta(hours=int(match.group(1))),
            "текст поста: относительные часы",
        )

    match = DURATION_RE.search(text)
    if match:
        return (
            published_at + timedelta(minutes=int(match.group(1))),
            "текст поста: длительность",
        )

    lowered = text.lower()
    if "через полчаса" in lowered or "следующие полчаса" in lowered:
        return (
            published_at + timedelta(minutes=30),
            "текст поста: полчаса",
        )

    match = CLOCK_RE.search(text)
    if match:
        local_post = published_at.astimezone(MOSCOW)
        deadline = local_post.replace(
            hour=int(match.group(1)),
            minute=int(match.group(2)),
            second=0,
            microsecond=0,
        )
        if deadline < local_post - timedelta(minutes=2):
            deadline += timedelta(days=1)
        return deadline.astimezone(UTC), "текст поста: время МСК"

    return None, "время не определено"


def human_remaining(deadline: datetime | None) -> str:
    if deadline is None:
        return "не определено"

    seconds = int((deadline - now_utc()).total_seconds())
    if seconds <= 0:
        return "время уже наступило"

    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours} ч {minutes} мин"
    return f"{max(1, minutes)} мин"


def telegram_api(method: str, payload: dict) -> dict:
    token = os.environ["BOT_TOKEN"]
    response = request_with_retries(
        "POST",
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram Bot API error: {data}")
    return data


def send_message(text: str, url: str | None = None) -> None:
    payload: dict = {
        "chat_id": os.environ["BOT_CHAT_ID"],
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "Открыть колесо", "url": url}]]
        }
    telegram_api("sendMessage", payload)


def notification_key(message: Message, link: str) -> str:
    raw = f"{message.source}:{message.message_id}:{link}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_recent_duplicate(state: dict, link: str) -> bool:
    if URL_DEDUP_MINUTES <= 0:
        return False

    previous = parse_datetime(state["recent_url_alerts"].get(link))
    return bool(
        previous
        and now_utc() - previous < timedelta(minutes=URL_DEDUP_MINUTES)
    )


def notify_channel_link(message: Message, link: str) -> None:
    deadline, method = infer_deadline(message.text, message.date)
    source = html.escape(message.source)
    post_url = html.escape(message.message_url, quote=True)
    identifier = html.escape(
        urlsplit(link).path.rstrip("/").rsplit("/", 1)[-1]
    )
    published = message.date.astimezone(DISPLAY_TZ)

    text = (
        "🎡 <b>Новое колесо BetBoom</b>\n\n"
        f"Источник: <a href=\"{post_url}\">{source}</a>\n"
        f"Идентификатор: <code>{identifier}</code>\n"
        f"Пост: {published:%d.%m.%Y %H:%M}\n"
        f"⏳ До прокрутки: <b>{html.escape(human_remaining(deadline))}</b>\n"
        f"Определение времени: {html.escape(method)}"
    )
    send_message(text, link)


def page_status(identifier: str) -> tuple[str, int | None, str]:
    url = f"https://betboom.ru/freestream/{identifier}"

    try:
        response = request_with_retries(
            "GET",
            url,
            attempts=2,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        status_code = response.status_code
        text = BeautifulSoup(response.text, "html.parser").get_text(
            "\n", strip=True
        )
    except requests.RequestException as exc:
        return "error", None, type(exc).__name__

    lowered = text.lower()
    if any(phrase in lowered for phrase in EXPIRED_PHRASES):
        return "expired", status_code, "найден явный признак завершения"

    countdown = COUNTDOWN_RE.search(text)
    if countdown and any(countdown.groups()):
        return "active", status_code, countdown.group(0)[:160]

    if any(phrase in lowered for phrase in ACTIVE_PHRASES):
        return "active", status_code, "найден признак активного колеса"

    return (
        "unknown",
        status_code,
        "страница открылась, но активность не подтверждена",
    )


def should_alert_known(previous: dict | None, status: str) -> bool:
    if status != "active":
        return False
    if not previous:
        return False
    if previous.get("status") == "active":
        return False

    last_alert = parse_datetime(previous.get("last_active_alert_at"))
    if last_alert and (
        now_utc() - last_alert
        < timedelta(hours=KNOWN_ACTIVE_ALERT_COOLDOWN_HOURS)
    ):
        return False
    return True


def check_known_links(state: dict, manual_active: list[str]) -> int:
    identifiers = read_list(KNOWN_IDS_PATH)
    if not identifiers or KNOWN_BATCH_SIZE <= 0:
        return 0

    # Rotate the checked subset every five-minute slot.
    slot = int(now_utc().timestamp() // 300)
    start = (slot * KNOWN_BATCH_SIZE) % len(identifiers)
    batch = [
        identifiers[(start + offset) % len(identifiers)]
        for offset in range(min(KNOWN_BATCH_SIZE, len(identifiers)))
    ]

    changes = 0
    statuses = state["known_status"]

    for identifier in batch:
        status, http_code, note = page_status(identifier)
        previous = statuses.get(identifier)
        alert = should_alert_known(previous, status)

        entry = {
            "status": status,
            "http_code": http_code,
            "note": note,
        }
        if previous and previous.get("last_active_alert_at"):
            entry["last_active_alert_at"] = previous["last_active_alert_at"]

        if alert:
            link = f"https://betboom.ru/freestream/{identifier}"
            send_message(
                "♻️ <b>Известная ссылка, возможно, снова активна</b>\n\n"
                f"Идентификатор: <code>{html.escape(identifier)}</code>\n"
                f"HTTP: {http_code}\n"
                f"Признак: {html.escape(note)}\n\n"
                "Это резервная проверка. Открой ссылку и убедись вручную.",
                link,
            )
            entry["last_active_alert_at"] = now_utc().isoformat()
            changes += 1

        statuses[identifier] = entry

        if MANUAL_RUN and status == "active":
            manual_active.append(identifier)

    return changes


def validate_environment() -> None:
    missing = [
        name
        for name in ("BOT_TOKEN", "BOT_CHAT_ID")
        if not os.getenv(name)
    ]
    if missing:
        raise RuntimeError(
            "Missing GitHub Actions secrets: " + ", ".join(missing)
        )


def main() -> int:
    try:
        validate_environment()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    state = load_state()
    initialized = set(state["initialized_sources"])
    seen: dict[str, str] = state["seen"]
    sources = read_list(SOURCES_PATH)

    found = 0
    duplicate_suppressed = 0
    errors: list[str] = []
    initialized_now = 0

    for username in sources:
        try:
            messages = fetch_public_channel(username)
        except Exception as exc:
            errors.append(f"@{username}: {type(exc).__name__}: {exc}")
            continue

        # An empty page is not a valid baseline: the channel may be unavailable.
        if not messages:
            errors.append(f"@{username}: no public messages found")
            continue

        current: list[tuple[str, Message, str]] = []
        for message in messages:
            for link in extract_links(message.text):
                current.append((notification_key(message, link), message, link))

        if username not in initialized:
            for key, _, _ in current:
                seen.setdefault(key, now_utc().isoformat())
            initialized.add(username)
            initialized_now += 1
            continue

        for key, message, link in current:
            if key in seen:
                continue

            # Always mark the post as handled, even when a repeated URL is muted.
            seen[key] = now_utc().isoformat()

            if is_recent_duplicate(state, link):
                duplicate_suppressed += 1
                continue

            notify_channel_link(message, link)
            state["recent_url_alerts"][link] = now_utc().isoformat()
            found += 1

    state["initialized_sources"] = sorted(initialized)

    manual_active: list[str] = []
    known_activated = check_known_links(state, manual_active)
    save_state(state)

    summary = (
        f"Sources: {len(sources)}; initialized now: {initialized_now}; "
        f"new links: {found}; duplicate alerts suppressed: "
        f"{duplicate_suppressed}; source errors: {len(errors)}; "
        f"known activations: {known_activated}"
    )
    print(summary)

    for error in errors[:30]:
        print(f"WARNING {error}")

    if MANUAL_RUN:
        active_text = (
            ", ".join(manual_active[:15])
            if manual_active
            else "не найдено"
        )
        send_message(
            "✅ <b>Ручная проверка завершена</b>\n\n"
            f"Публичных источников: {len(sources)}\n"
            f"Новых ссылок: {found}\n"
            f"Подавлено дублей: {duplicate_suppressed}\n"
            f"Ошибок источников: {len(errors)}\n"
            "Известные ссылки с признаками активности: "
            f"{html.escape(active_text)}\n\n"
            "При первом запуске старые публикации используются как "
            "исходная точка и не присылаются."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
