from __future__ import annotations

import argparse
from typing import Any

from admin_panel_runtime_v15 import TelegramPanelRuntimeV15


class TelegramPanelRuntimeV16(TelegramPanelRuntimeV15):
    """Panel v16: all available sections are visible in the main inline menu."""

    @staticmethod
    def compact_menu_rows(admin: bool) -> list[list[dict[str, Any]]]:
        if admin:
            return [
                [
                    {"text": "📊 Статистика", "callback_data": "page:stats:1"},
                    {"text": "🔥 Активные колёса", "callback_data": "page:active"},
                ],
                [
                    {"text": "📡 Источники", "callback_data": "page:sources"},
                    {"text": "🌙 Ночное наблюдение", "callback_data": "page:discovery"},
                ],
                [
                    {"text": "🛰️ Разведка источников", "callback_data": "page:intelligence"},
                    {"text": "🏆 Рейтинг каналов", "callback_data": "page:ranking"},
                ],
                [
                    {"text": "⚙️ Настройки", "callback_data": "page:settings"},
                    {"text": "✅ Состояние системы", "callback_data": "page:status"},
                ],
                [{"text": "📱 Приложение", "callback_data": "page:app"}],
            ]
        return [
            [
                {"text": "📊 Статистика", "callback_data": "page:stats:1"},
                {"text": "🔥 Активные колёса", "callback_data": "page:active"},
            ],
            [
                {"text": "📡 Источники", "callback_data": "page:sources"},
                {"text": "🏆 Рейтинг каналов", "callback_data": "page:ranking"},
            ],
            [{"text": "📱 Приложение", "callback_data": "page:app"}],
        ]

    def render_page(self, page: str) -> None:
        # Backward compatibility for old messages that still contain the removed
        # "More sections" button.
        if page == "more":
            self.show_menu(clear_stack=True)
            return
        super().render_page(page)


def self_test() -> None:
    admin_rows = TelegramPanelRuntimeV16.compact_menu_rows(True)
    callbacks = [button.get("callback_data") for row in admin_rows for button in row]
    expected = {
        "page:stats:1",
        "page:active",
        "page:sources",
        "page:discovery",
        "page:intelligence",
        "page:ranking",
        "page:settings",
        "page:status",
        "page:app",
    }
    assert set(callbacks) == expected
    assert "page:more" not in callbacks
    assert "page:reports" not in callbacks
    assert all(len(row) <= 2 for row in admin_rows)
    print("admin_panel_runtime_v16 unified main menu self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV16().run()


if __name__ == "__main__":
    raise SystemExit(main())
