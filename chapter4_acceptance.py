from __future__ import annotations

from pathlib import Path

import notification_button_recovery
import telegram_ui
from admin_panel_runtime_v41 import TelegramPanelRuntimeV41, self_test as panel_self_test


ROOT = Path(__file__).resolve().parent


def main() -> int:
    telegram_ui.self_test()
    panel_self_test()
    notification_button_recovery.self_test()

    assert TelegramPanelRuntimeV41.RUNTIME_VERSION == 41
    assert Path(notification_button_recovery.__file__).resolve() == (
        ROOT / "notification_button_recovery.py"
    ).resolve()
    assert (ROOT / "scripts/validate_control_center.sh").is_file()

    user_callbacks = {
        str(button.get("callback_data") or "")
        for row in TelegramPanelRuntimeV41.compact_menu_rows(False)
        for button in row
    }
    admin_callbacks = {
        str(button.get("callback_data") or "")
        for row in TelegramPanelRuntimeV41.compact_menu_rows(True)
        for button in row
    }
    assert "page:status" in user_callbacks
    assert "page:control" not in user_callbacks
    assert "page:control" in admin_callbacks
    assert "page:status" not in admin_callbacks
    assert not telegram_ui.markup_issues(
        {"inline_keyboard": TelegramPanelRuntimeV41.compact_menu_rows(False)}
    )
    assert not telegram_ui.markup_issues(
        {"inline_keyboard": TelegramPanelRuntimeV41.compact_menu_rows(True)}
    )
    assert "Mini App — архивировано" in (ROOT / "MINI_APP_ARCHIVED.md").read_text(
        encoding="utf-8"
    )
    assert (ROOT / "tests/test_ui_chapter4.py").exists()
    print("Interface acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
