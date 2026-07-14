from __future__ import annotations

import os
import time
from datetime import datetime
from threading import Lock
from typing import Any, Callable
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

import monitor_data as data_store


OUTAGE_PREFIX = "GLOBAL_TRANSPORT_OUTAGE:"
BATCH_ATTEMPTS = max(2, min(5, int(os.getenv("TRANSPORT_BATCH_ATTEMPTS", "3"))))
BACKOFF_SECONDS = (5, 15, 30, 60)
WEB_DOMAINS = ("t.me", "telegram.me")
RETRYABLE_HTTP_STATUSES = {403, 408, 425, 429, 500, 502, 503, 504}

_TRANSIENT_MARKERS = (
    "nameresolutionerror",
    "failed to resolve",
    "temporary failure in name resolution",
    "name or service not known",
    "connectionerror",
    "connecttimeout",
    "readtimeout",
    "proxyerror",
    "remotedisconnected",
    "connection reset",
    "network is unreachable",
    "temporary http",
)

_outage_sources: set[str] = set()
_outage_detail = ""
_preferred_domains: dict[str, str] = {}
_last_domain_errors: dict[str, dict[str, str]] = {}
_domain_lock = Lock()


def is_transient_transport_error(value: object) -> bool:
    text = str(value or "").casefold()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def build_source_urls(source: str, preferred_domain: str | None = None) -> list[str]:
    """Return Telegram web-preview endpoints in the order they should be tried."""
    clean = str(source).strip().lstrip("@").strip("/")
    domains = list(WEB_DOMAINS)
    if preferred_domain in WEB_DOMAINS:
        domains.remove(preferred_domain)
        domains.insert(0, preferred_domain)
    return [f"https://{domain}/s/{clean}" for domain in domains]


def _preview_source(url: str) -> str:
    try:
        parsed = urlsplit(str(url))
    except ValueError:
        return ""
    host = parsed.netloc.casefold().split(":", 1)[0]
    if host not in WEB_DOMAINS or not parsed.path.startswith("/s/"):
        return ""
    raw = parsed.path[3:].strip("/").split("/", 1)[0]
    return unquote(raw).strip().lstrip("@")


def preferred_source_domain(source: str) -> str:
    with _domain_lock:
        return _preferred_domains.get(str(source).casefold(), "")


def working_source_domain(source: str) -> str:
    return preferred_source_domain(source)


def source_domain_errors(source: str) -> dict[str, str]:
    with _domain_lock:
        return dict(_last_domain_errors.get(str(source).casefold(), {}))


def _remember_working_domain(source: str, domain: str) -> None:
    if domain not in WEB_DOMAINS:
        return
    key = str(source).casefold()
    with _domain_lock:
        _preferred_domains[key] = domain
        _last_domain_errors.pop(key, None)


def _remember_domain_error(source: str, domain: str, error: object) -> None:
    key = str(source).casefold()
    with _domain_lock:
        _last_domain_errors.setdefault(key, {})[domain] = str(error)[:500]


def _domain_order(source: str) -> list[str]:
    preferred = preferred_source_domain(source)
    domains = list(WEB_DOMAINS)
    if preferred in domains:
        domains.remove(preferred)
        domains.insert(0, preferred)
    return domains


def _with_domain(url: str, domain: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme or "https", domain, parsed.path, parsed.query, parsed.fragment))


def request_source_preview_with_fallback(
    requester: Callable[..., requests.Response],
    method: str,
    url: str,
    *,
    attempts: int = 3,
    **kwargs: Any,
) -> requests.Response:
    """Request a Telegram public preview, falling back from t.me to telegram.me."""
    source = _preview_source(url)
    if str(method).upper() != "GET" or not source:
        return requester(method, url, attempts=attempts, **kwargs)

    last_response: requests.Response | None = None
    last_exception: requests.RequestException | None = None
    domains = _domain_order(source)

    for index, domain in enumerate(domains):
        candidate = _with_domain(url, domain)
        try:
            response = requester(method, candidate, attempts=attempts, **kwargs)
        except requests.RequestException as exc:
            last_exception = exc
            _remember_domain_error(source, domain, exc)
            if index + 1 < len(domains) and is_transient_transport_error(exc):
                print(
                    f"WARNING Telegram preview {domain} failed for @{source}; "
                    f"trying {domains[index + 1]}: {type(exc).__name__}: {exc}"
                )
                continue
            raise

        last_response = response
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code in RETRYABLE_HTTP_STATUSES and index + 1 < len(domains):
            detail = f"HTTP {status_code}"
            _remember_domain_error(source, domain, detail)
            print(
                f"WARNING Telegram preview {domain} returned {detail} for @{source}; "
                f"trying {domains[index + 1]}"
            )
            continue

        _remember_working_domain(source, domain)
        return response

    if last_exception is not None:
        raise last_exception
    if last_response is not None:
        return last_response
    raise requests.ConnectionError(f"No Telegram preview domain was available for @{source}")


def is_systemic_transport_outage(
    sources: list[str],
    results: dict[str, Any],
    errors: dict[str, str],
    empty: list[str],
) -> bool:
    if not sources or results or empty or len(errors) < len(sources):
        return False
    return all(is_transient_transport_error(errors.get(source, "")) for source in sources)


def outage_active() -> bool:
    return bool(_outage_sources)


def outage_detail() -> str:
    return _outage_detail


def _mark_transport_attempt(
    data: dict[str, Any], source: str, at: datetime | None = None
) -> None:
    at = at or data_store.now_utc()
    entry = data.setdefault("sources", {}).setdefault(source, {})
    entry["last_transport_outage_at"] = at.isoformat()
    entry["transport_outages"] = int(entry.get("transport_outages", 0) or 0) + 1
    entry["last_updated_at"] = at.isoformat()


def install(monitor_module: Any) -> None:
    """Install domain fallback, retry and accounting guards on the monitor runtime."""
    global _outage_sources, _outage_detail

    if getattr(monitor_module, "_bbvg_resilience_installed", False):
        return

    original_request_with_retries: Callable = monitor_module.request_with_retries
    original_fetch_all: Callable = monitor_module.fetch_all_sources
    original_record_success: Callable = data_store.record_source_success
    original_record_problem: Callable = data_store.record_source_problem
    original_record_stats: Callable = data_store.record_source_check_stats

    def resilient_request_with_retries(
        method: str,
        url: str,
        *,
        attempts: int = 3,
        **kwargs: Any,
    ) -> requests.Response:
        return request_source_preview_with_fallback(
            original_request_with_retries,
            method,
            url,
            attempts=attempts,
            **kwargs,
        )

    def resilient_fetch_all(sources: list[str]):
        global _outage_sources, _outage_detail
        _outage_sources = set()
        _outage_detail = ""

        last_result = ({}, {}, [])
        for attempt in range(1, BATCH_ATTEMPTS + 1):
            last_result = original_fetch_all(sources)
            results, errors, empty = last_result
            if not is_systemic_transport_outage(sources, results, errors, empty):
                return last_result

            sample = next(iter(errors.values()), "temporary Telegram transport failure")
            print(
                "WARNING systemic Telegram transport outage detected after both domains; "
                f"batch attempt {attempt}/{BATCH_ATTEMPTS}: {sample[:300]}"
            )
            if attempt < BATCH_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])

        results, errors, empty = last_result
        _outage_sources = {source.casefold() for source in sources}
        _outage_detail = next(iter(errors.values()), "temporary Telegram transport failure")
        tagged = {
            source: f"{OUTAGE_PREFIX} {detail}"
            for source, detail in errors.items()
        }
        return results, tagged, empty

    def resilient_record_success(
        data: dict[str, Any],
        username: str,
        messages_count: int,
        at: datetime | None = None,
    ) -> None:
        original_record_success(data, username, messages_count, at)
        domain = working_source_domain(username)
        if not domain:
            return
        stamp = at or data_store.now_utc()
        entry = data.setdefault("sources", {}).setdefault(username, {})
        entry["transport_domain"] = domain
        entry["transport_fallback_active"] = domain != WEB_DOMAINS[0]
        entry["last_transport_success_at"] = stamp.isoformat()
        entry.pop("last_transport_error", None)

    def resilient_record_problem(
        data: dict[str, Any],
        username: str,
        kind: str,
        error: str = "",
        at: datetime | None = None,
    ) -> bool:
        if kind == "error" and str(error).startswith(OUTAGE_PREFIX):
            stamp = at or data_store.now_utc()
            entry = data.setdefault("sources", {}).setdefault(username, {})
            entry.setdefault("checks", 0)
            entry.setdefault("successful_checks", 0)
            entry.setdefault("consecutive_errors", 0)
            entry.setdefault("consecutive_empty", 0)
            entry.setdefault("status", "unknown")
            entry["last_transport_outage_at"] = stamp.isoformat()
            entry["last_transport_error"] = str(error)[len(OUTAGE_PREFIX):].strip()[:500]
            entry["transport_outages"] = int(entry.get("transport_outages", 0) or 0) + 1
            entry["transport_domains_tried"] = list(WEB_DOMAINS)
            return False
        return original_record_problem(data, username, kind, error, at)

    def resilient_record_stats(
        data: dict[str, Any],
        source: str,
        status: str,
        messages_count: int = 0,
        at: datetime | None = None,
    ) -> None:
        if status == "error" and source.casefold() in _outage_sources:
            _mark_transport_attempt(data, source, at)
            return
        original_record_stats(data, source, status, messages_count, at)

    monitor_module.request_with_retries = resilient_request_with_retries
    monitor_module.fetch_all_sources = resilient_fetch_all
    data_store.record_source_success = resilient_record_success
    data_store.record_source_problem = resilient_record_problem
    data_store.record_source_check_stats = resilient_record_stats
    monitor_module._bbvg_resilience_installed = True


def self_test() -> None:
    assert build_source_urls("test") == [
        "https://t.me/s/test",
        "https://telegram.me/s/test",
    ]
    assert build_source_urls("@test", "telegram.me") == [
        "https://telegram.me/s/test",
        "https://t.me/s/test",
    ]
    assert _preview_source("https://t.me/s/test?before=20") == "test"
    assert not _preview_source("https://api.telegram.org/bot123/getMe")
    assert is_transient_transport_error("NameResolutionError: Failed to resolve t.me")

    class FakeResponse:
        def __init__(self, url: str, status_code: int = 200):
            self.url = url
            self.status_code = status_code
            self.text = "<div class='tgme_widget_message' data-post='test/1'></div>"

    calls: list[str] = []

    def fake_request(method: str, url: str, *, attempts: int = 3, **kwargs: Any):
        calls.append(url)
        if urlsplit(url).netloc == "t.me":
            raise requests.ConnectionError("NameResolutionError: Failed to resolve t.me")
        return FakeResponse(url)

    with _domain_lock:
        _preferred_domains.clear()
        _last_domain_errors.clear()

    response = request_source_preview_with_fallback(
        fake_request,
        "GET",
        "https://t.me/s/test?before=20",
        timeout=10,
    )
    assert urlsplit(response.url).netloc == "telegram.me"
    assert [urlsplit(value).netloc for value in calls] == ["t.me", "telegram.me"]
    assert preferred_source_domain("test") == "telegram.me"

    calls.clear()
    response = request_source_preview_with_fallback(
        fake_request,
        "GET",
        "https://t.me/s/test",
        timeout=10,
    )
    assert urlsplit(response.url).netloc == "telegram.me"
    assert [urlsplit(value).netloc for value in calls] == ["telegram.me"]

    with _domain_lock:
        _preferred_domains.clear()
        _last_domain_errors.clear()
    print("monitor_resilience self-test passed")


if __name__ == "__main__":
    self_test()
