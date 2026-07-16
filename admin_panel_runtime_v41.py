from __future__ import annotations

import argparse
import html
from typing import Any

from admin_panel_runtime_v40 import TelegramPanelRuntimeV40, self_test as v40_self_test


class TelegramPanelRuntimeV41(TelegramPanelRuntimeV40):
    """Stable summaries, clear numbered wheel controls and concise home screen."""

    RUNTIME_VERSION = 41

    def show_menu(self, *, clear_stack: bool = True) -> None:
        if clear_stack:
            self.navigation[str(self.current_user_id or "guest")] = ["menu"]
        role = self.role_for(self.current_user_id)
        admin = role in {"owner", "admin"}
        text = (
            "🎡 <b>BB V.G.</b>\n\n"
            "Находит колёса BetBoom, показывает время прокрутки и хранит отметки участия.\n\n"
            f"Ваша роль: <b>{html.escape(self.role_name(role))}</b>\n\n"
            "Выберите раздел."
        )
        self.send(
            text,
            reply_markup={"inline_keyboard": self.compact_menu_rows(admin)},
        )


def self_test() -> None:
    v40_self_test()
    panel = TelegramPanelRuntimeV41()
    captured: list[tuple[str, dict[str, Any]]] = []
    panel.current_user_id = "1"
    panel.current_role = "admin"
    panel.navigation = {"1": ["menu"]}
    panel.role_for = lambda user_id: "admin"  # type: ignore[method-assign]
    panel.role_name = lambda role: "Администратор"  # type: ignore[method-assign]
    panel.send = lambda text, **kwargs: captured.append((text, kwargs)) or {}  # type: ignore[method-assign]

    panel.show_menu()
    text, kwargs = captured[-1]
    assert panel.RUNTIME_VERSION == 41
    assert "Находит колёса BetBoom" in text
    assert "Ваша роль: <b>Администратор</b>" in text
    callbacks = [
        str(button.get("callback_data") or "")
        for row in kwargs["reply_markup"]["inline_keyboard"]
        for button in row
        if isinstance(button, dict)
    ]
    assert "page:active" in callbacks
    assert "page:control" in callbacks
    print("BB V.G. v41 clear numbered interface self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV41().run()


if __name__ == "__main__":
    raise SystemExit(main())
