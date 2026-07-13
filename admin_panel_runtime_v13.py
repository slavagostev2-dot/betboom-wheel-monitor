from __future__ import annotations

import argparse
import html
from typing import Any

from admin_panel_runtime_v12 import TelegramPanelRuntimeV12


class TelegramPanelRuntimeV13(TelegramPanelRuntimeV12):
    """Panel v13: explicit source-intelligence launch status."""

    @staticmethod
    def intelligence_launch_text() -> str:
        return (
            "▶️ <b>Разведка новых источников запущена</b>\n\n"
            "Состояние: 🟡 запрос передан в GitHub Actions и ожидает начала выполнения.\n"
            "После запуска строка состояния в сводке изменится на «разведка выполняется», "
            "а после завершения — на результат последнего запуска."
        )

    def handle_callback(self, query: dict[str, Any]) -> None:
        data = str(query.get("data") or "")
        if data != "control:intelligence":
            super().handle_callback(query)
            return

        message = query.get("message") or {}
        chat = message.get("chat") or {}
        sender = query.get("from") or {}
        self.set_context(chat.get("id"), sender.get("id"))
        query_id = str(query.get("id") or "")

        if not self.is_admin():
            self.answer(query_id, "Недостаточно прав")
            return

        try:
            self.dispatch("source-intelligence.yml", None)
        except Exception as exc:
            self.answer(query_id, "Ошибка запуска")
            self.send(
                "⚠️ Не удалось запустить разведку: "
                f"<code>{html.escape(type(exc).__name__)}</code>.",
                reply_markup=self.with_nav(),
            )
            return

        self.answer(query_id, "Разведка запущена")
        self.send(
            self.intelligence_launch_text(),
            reply_markup=self.with_nav([[
                {"text": "🔄 Обновить состояние", "callback_data": "page:intelligence"}
            ]]),
        )


def self_test() -> None:
    text = TelegramPanelRuntimeV13.intelligence_launch_text()
    assert "Состояние:" in text
    assert "ожидает начала выполнения" in text
    print("admin_panel_runtime_v13 self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV13().run()


if __name__ == "__main__":
    raise SystemExit(main())
