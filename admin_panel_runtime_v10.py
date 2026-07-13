from __future__ import annotations

import argparse
from typing import Any

import admin_bot as legacy
from admin_panel_runtime_v9 import (
    ADMIN_KEYBOARD_V9,
    BTN_APP,
    TelegramPanelRuntimeV9,
    USER_KEYBOARD_V9,
)

MINI_APP_CDN_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "slavagostev2-dot/betboom-wheel-monitor@main/docs/index.html"
)

MINIMAL_COMMANDS = [
    {"command": "start", "description": "Открыть панель"},
    {"command": "myid", "description": "Показать мой Telegram ID"},
]


class TelegramPanelRuntimeV10(TelegramPanelRuntimeV9):
    """Panel v10: CDN-hosted Mini App and minimal command menu."""

    def setup_bot(self) -> None:
        self.telegram_api("deleteWebhook", {"drop_pending_updates": False})
        self.telegram_api("setMyCommands", {"commands": MINIMAL_COMMANDS})
        # Keep Telegram's blue Menu button as a compact command launcher.
        self.telegram_api(
            "setChatMenuButton",
            {"menu_button": {"type": "commands"}},
        )

    def show_app_entry(self) -> None:
        self.send(
            "📱 <b>Приложение BetBoom Monitor</b>\n\n"
            "Приложение опубликовано через независимую HTTPS-раздачу файлов репозитория. "
            "Можно открыть его внутри Telegram или в обычном браузере.",
            reply_markup=self.with_nav([
                [{"text": "📱 Открыть внутри Telegram", "web_app": {"url": MINI_APP_CDN_URL}}],
                [{"text": "🌐 Открыть в браузере", "url": MINI_APP_CDN_URL}],
            ]),
        )

    def handle_message(self, message: dict[str, Any]) -> None:
        text = str(message.get("text") or "").strip()
        command = text.split("@", 1)[0].split(maxsplit=1)[0].casefold() if text else ""
        if command == "/myid":
            chat = message.get("chat") or {}
            sender = message.get("from") or {}
            self.set_context(chat.get("id"), sender.get("id"))
            self.send(
                f"🆔 Ваш Telegram ID: <code>{self.current_user_id or ''}</code>",
                reply_markup=self.with_nav(),
            )
            return
        super().handle_message(message)


def self_test() -> None:
    assert MINI_APP_CDN_URL.startswith("https://cdn.jsdelivr.net/")
    assert [item["command"] for item in MINIMAL_COMMANDS] == ["start", "myid"]
    assert BTN_APP in str(ADMIN_KEYBOARD_V9)
    assert BTN_APP in str(USER_KEYBOARD_V9)
    print("admin_panel_runtime_v10 self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV10().run()


if __name__ == "__main__":
    raise SystemExit(main())
