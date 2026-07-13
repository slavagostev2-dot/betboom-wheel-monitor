from __future__ import annotations

import argparse
import html
from typing import Any

from admin_panel_runtime_v7 import (
    ADMIN_KEYBOARD_V7,
    BTN_INTELLIGENCE,
    BTN_NIGHTLY,
    TelegramPanelRuntimeV7,
    USER_KEYBOARD_V7,
)


class TelegramPanelRuntimeV8(TelegramPanelRuntimeV7):
    """Panel v8: corrected source/report routes and participation feedback."""

    def show_sources(self) -> None:
        snap = self.snapshot()
        groups = self.source_sets(snap)
        primary = groups.get("primary", [])
        reserve = groups.get("reserve", [])
        paused = groups.get("paused", [])
        rows: list[list[dict[str, str]]] = [
            [{"text": f"⚡ Основная проверка ({len(primary)})", "callback_data": "source_list:primary:0"}],
            [{"text": f"🌙 Ночная проверка ({len(reserve)})", "callback_data": "source_list:reserve:0"}],
            [{"text": f"⏸ Временно приостановлены ({len(paused)})", "callback_data": "source_list:paused:0"}],
        ]
        if self.is_admin():
            rows.append([{"text": "➕ Добавить источник", "callback_data": "source:add"}])
        self.send(
            "📡 <b>Источники</b>\n\n"
            f"Основная проверка: <b>{len(primary)}</b>\n"
            f"Ночная проверка: <b>{len(reserve)}</b>\n"
            f"Временно приостановлены: <b>{len(paused)}</b>\n\n"
            "Отчёт по каналам без колёс находится во вкладке «Отчёты».",
            reply_markup=self.with_nav(rows),
        )

    def show_reports(self) -> None:
        rows = [
            [
                {"text": "Сегодня", "callback_data": "page:report:1"},
                {"text": "7 дней", "callback_data": "page:report:7"},
                {"text": "30 дней", "callback_data": "page:report:30"},
            ],
            [{"text": "📭 Давно без колёс", "callback_data": "page:report:inactive"}],
            [{"text": "⚠️ Ошибки источников", "callback_data": "page:report:errors"}],
        ]
        self.send(
            "📅 <b>Отчёты</b>\n\nВыберите период или специальный отчёт.",
            reply_markup=self.with_nav(rows),
        )

    def handle_callback(self, query: dict[str, Any]) -> None:
        data = str(query.get("data") or "")
        message = query.get("message") or {}
        chat = message.get("chat") or {}
        sender = query.get("from") or {}
        self.set_context(chat.get("id"), sender.get("id"))
        query_id = str(query.get("id") or "")

        # Backward-compatible report aliases from messages sent by older panel versions.
        if data.startswith("report:"):
            data = f"page:{data}"
            query = dict(query)
            query["data"] = data

        if data.startswith("wheel:part:"):
            if not self.can_view():
                self.answer(query_id, "Недоступно")
                return
            key = data.split(":", 2)[2]
            try:
                self.dispatch_admin_action("participate_wheel", key)
            except Exception as exc:
                self.answer(query_id, "Ошибка")
                self.send(
                    f"⚠️ Не удалось поставить отметку участия: <code>{html.escape(type(exc).__name__)}</code>.",
                    reply_markup=self.with_nav(),
                )
                return
            self.answer(query_id, "Участие отмечается")
            self.send(
                "✅ <b>Отметка участия принята.</b>\n\n"
                "Изменение сохраняется через GitHub Actions и обычно появляется в списке после следующего обновления.",
                reply_markup=self.with_nav([[{"text": "🔄 Обновить колёса", "callback_data": "refresh:active"}]]),
            )
            return

        super().handle_callback(query)


class _TestPanel(TelegramPanelRuntimeV8):
    def __init__(self) -> None:
        # Avoid network-dependent parent initializers in routing tests.
        self.current_chat_id = "1"
        self.current_user_id = "1"
        self.current_role = "owner"
        self.navigation = {"1": ["menu"]}
        self.pending_input = {}
        self.sent: list[tuple[str, dict[str, Any] | None]] = []
        self.opened: list[str] = []

    def role_for(self, user_id: str | None) -> str:
        return "owner"

    def can_view(self) -> bool:
        return True

    def is_admin(self) -> bool:
        return True

    def set_context(self, chat_id: Any, user_id: Any) -> None:
        self.current_chat_id = str(chat_id)
        self.current_user_id = str(user_id)
        self.current_role = "owner"

    def send(self, text: str, *, reply_markup: dict[str, Any] | None = None, chat_id: str | None = None) -> dict:
        self.sent.append((text, reply_markup))
        return {"ok": True}

    def answer(self, query_id: str, text: str = "") -> None:
        return None

    def open_page(self, page: str, *, push: bool = True) -> None:
        self.opened.append(page)

    def dispatch_admin_action(self, action: str, value: str) -> None:
        assert action == "participate_wheel"
        assert value == "wheel1"


def self_test() -> None:
    panel = _TestPanel()
    menu_routes = {
        "📊 Статистика": "stats:1",
        "🔥 Активные колёса": "active",
        "📡 Источники": "sources",
        "🏆 Рейтинг каналов": "ranking",
        "📅 Отчёты": "reports",
        "✅ Проверка работы": "status",
        "🛠 Управление": "control",
        "⚙️ Настройки": "settings",
        BTN_NIGHTLY: "discovery",
        BTN_INTELLIGENCE: "intelligence",
    }
    for text, expected in menu_routes.items():
        panel.opened.clear()
        panel.handle_message({"chat": {"id": 1}, "from": {"id": 1}, "text": text})
        assert panel.opened == [expected], (text, panel.opened)

    # Verify corrected callback formats and backward compatibility.
    panel.opened.clear()
    panel.handle_callback({"id": "q1", "from": {"id": 1}, "message": {"chat": {"id": 1}}, "data": "page:report:inactive"})
    assert panel.opened == ["report:inactive"]
    panel.opened.clear()
    panel.handle_callback({"id": "q2", "from": {"id": 1}, "message": {"chat": {"id": 1}}, "data": "report:errors"})
    assert panel.opened == ["report:errors"]

    panel.sent.clear()
    panel.handle_callback({"id": "q3", "from": {"id": 1}, "message": {"chat": {"id": 1}}, "data": "wheel:part:wheel1"})
    assert panel.sent and "Отметка участия принята" in panel.sent[-1][0]

    assert "📡 Источники" in str(ADMIN_KEYBOARD_V7)
    assert "📱 Открыть приложение" in str(USER_KEYBOARD_V7)
    print("admin_panel_runtime_v8 full routing self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV8().run()


if __name__ == "__main__":
    raise SystemExit(main())
