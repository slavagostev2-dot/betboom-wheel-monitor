from __future__ import annotations

import argparse
from urllib.parse import quote

from admin_panel_runtime_v18 import TelegramPanelRuntimeV18

MINIAPP_V4_URL = (
    "https://raw.githack.com/slavagostev2-dot/"
    "betboom-wheel-monitor/main/docs/index.html"
)
BRAND_NAME = "BB V.G."


class TelegramPanelRuntimeV19(TelegramPanelRuntimeV18):
    """Panel v19: BB V.G. branding and Mini App v4."""

    def miniapp_url_for_chat(self) -> str:
        params = ["v=4.0.0"]
        username = self.bot_username()
        if username:
            params.append(f"bot={quote(username)}")
        return MINIAPP_V4_URL + "?" + "&".join(params)

    def show_menu(self, *, clear_stack: bool = True) -> None:
        if clear_stack:
            self.navigation[str(self.current_user_id or "guest")] = ["menu"]
        role = self.role_for(self.current_user_id)
        admin = role in {"owner", "admin"}
        title = "панель управления" if admin else "информационная панель"
        self.send(
            f"◈ <b>{BRAND_NAME} — {title}</b>\n\n"
            f"Ваш доступ: <b>{self.role_name(role)}</b>\n"
            "Выберите раздел.",
            reply_markup={"inline_keyboard": self.compact_menu_rows(admin)},
        )

    def show_app_entry(self) -> None:
        url = self.miniapp_url_for_chat()
        self.send(
            f"📱 <b>Приложение {BRAND_NAME}</b>\n\n"
            "Актуальные колёса, статистика, источники и запросы пользователей.",
            reply_markup=self.with_nav([
                [{"text": "📱 Открыть внутри Telegram", "web_app": {"url": url}}],
                [{"text": "🌐 Открыть в браузере", "url": url}],
            ]),
        )


def self_test() -> None:
    assert BRAND_NAME == "BB V.G."
    assert MINIAPP_V4_URL.endswith("docs/index.html")
    print("admin_panel_runtime_v19 BB V.G. self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV19().run()


if __name__ == "__main__":
    raise SystemExit(main())
