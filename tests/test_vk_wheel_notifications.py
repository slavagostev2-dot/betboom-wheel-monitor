from __future__ import annotations

import hashlib
import re
from typing import Any

import vk_wheel_notifications


class FakeRouter:
    WHEEL_URL_RE = re.compile(
        r"(?:https?://)?(?:www\.)?betboom\.ru/freestream/([A-Za-z0-9._~-]+)",
        re.IGNORECASE,
    )
    claimed: set[str] = set()
    completed: set[str] = set()

    @staticmethod
    def notification_kind(text: str) -> str:
        lowered = str(text).casefold()
        if "напоминание" in lowered:
            return "wheel_final_reminders"
        if "время прокрутки" in lowered:
            return "wheel_draw_alerts"
        return "wheels"

    @staticmethod
    def notification_event_identity(
        kind: str,
        text: str,
        url: str | None,
        reply_markup: dict | None,
    ) -> str:
        match = FakeRouter.WHEEL_URL_RE.search(str(url or text or ""))
        return f"wheel:{kind}:{match.group(1)}:detected" if match else ""

    @staticmethod
    def delivery_key(chat_id: str, kind: str, text: str, url: str | None) -> str:
        return hashlib.sha256(
            f"{chat_id}|{kind}|{text}|{url or ''}".encode("utf-8")
        ).hexdigest()

    @classmethod
    def claim_delivery(cls, key: str) -> bool:
        if key in cls.claimed or key in cls.completed:
            return False
        cls.claimed.add(key)
        return True

    @classmethod
    def release_delivery(cls, key: str) -> None:
        cls.claimed.discard(key)

    @classmethod
    def complete_delivery(cls, key: str) -> None:
        cls.claimed.discard(key)
        cls.completed.add(key)


def setup_function() -> None:
    FakeRouter.claimed.clear()
    FakeRouter.completed.clear()


def test_new_wheel_is_dispatched_once_and_html_is_removed() -> None:
    calls: list[dict[str, str]] = []

    def dispatcher(**kwargs: str) -> bool:
        calls.append(dict(kwargs))
        return True

    first = vk_wheel_notifications.dispatch_vk_wheel_notification(
        FakeRouter,
        "🎡 <b>Новое колесо BetBoom</b>",
        url="https://betboom.ru/freestream/test-wheel",
        dispatcher=dispatcher,
    )
    second = vk_wheel_notifications.dispatch_vk_wheel_notification(
        FakeRouter,
        "🎡 <b>Новое колесо BetBoom</b>",
        url="https://betboom.ru/freestream/test-wheel",
        dispatcher=dispatcher,
    )

    assert first["dispatched"] is True
    assert second.get("duplicate") is True
    assert len(calls) == 1
    assert calls[0]["message"] == (
        "🎡 Новое колесо BetBoom\n\nhttps://betboom.ru/freestream/test-wheel"
    )


def test_reminders_and_draw_alerts_are_not_sent_to_vk() -> None:
    calls: list[dict[str, str]] = []

    def dispatcher(**kwargs: str) -> bool:
        calls.append(dict(kwargs))
        return True

    reminder = vk_wheel_notifications.dispatch_vk_wheel_notification(
        FakeRouter,
        "🚨 Напоминание о колесе BetBoom",
        url="https://betboom.ru/freestream/reminder",
        dispatcher=dispatcher,
    )
    draw = vk_wheel_notifications.dispatch_vk_wheel_notification(
        FakeRouter,
        "🎯 Время прокрутки колеса наступило",
        url="https://betboom.ru/freestream/draw",
        dispatcher=dispatcher,
    )

    assert reminder["eligible"] is False
    assert draw["eligible"] is False
    assert calls == []


def test_vk_failure_does_not_break_successful_telegram_delivery(monkeypatch) -> None:
    class FakeMonitor:
        sent = 0

        @classmethod
        def send_message(
            cls,
            text: str,
            url: str | None = None,
            reply_markup: dict | None = None,
        ) -> dict[str, Any]:
            cls.sent += 1
            return {"ok": True, "result": {"sent": 1}}

    def broken_dispatch(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("simulated VK failure")

    monkeypatch.setattr(
        vk_wheel_notifications,
        "dispatch_vk_wheel_notification",
        broken_dispatch,
    )
    vk_wheel_notifications.install(FakeMonitor, FakeRouter)

    result = FakeMonitor.send_message(
        "🎡 Новое колесо BetBoom",
        url="https://betboom.ru/freestream/telegram-first",
    )

    assert result["ok"] is True
    assert FakeMonitor.sent == 1


def test_telegram_failure_is_preserved_even_if_vk_dispatch_runs(monkeypatch) -> None:
    calls: list[str] = []

    class FailingMonitor:
        @staticmethod
        def send_message(
            text: str,
            url: str | None = None,
            reply_markup: dict | None = None,
        ) -> dict[str, Any]:
            raise TimeoutError("telegram failed")

    def successful_dispatch(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("vk")
        return {"eligible": True, "dispatched": True}

    monkeypatch.setattr(
        vk_wheel_notifications,
        "dispatch_vk_wheel_notification",
        successful_dispatch,
    )
    vk_wheel_notifications.install(FailingMonitor, FakeRouter)

    try:
        FailingMonitor.send_message(
            "🎡 Новое колесо BetBoom",
            url="https://betboom.ru/freestream/vk-still-runs",
        )
    except TimeoutError:
        pass
    else:
        raise AssertionError("Telegram failure must remain visible to the monitor")

    assert calls == ["vk"]
