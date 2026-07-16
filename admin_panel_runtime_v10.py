from __future__ import annotations

import argparse

from admin_panel_runtime_v9 import (
    ADMIN_KEYBOARD_V9,
    BTN_APP,
    TelegramPanelRuntimeV9,
    USER_KEYBOARD_V9,
)
from bbvg.bot.foundation import (
    MINI_APP_CDN_URL,
    MINIMAL_COMMANDS,
    PanelFoundationMixin,
    self_test as foundation_self_test,
)


class TelegramPanelRuntimeV10(PanelFoundationMixin, TelegramPanelRuntimeV9):
    """Compatibility entrypoint for the consolidated panel foundation."""


def self_test() -> None:
    foundation_self_test()
    assert MINI_APP_CDN_URL.startswith("https://cdn.jsdelivr.net/")
    assert [item["command"] for item in MINIMAL_COMMANDS] == ["start", "myid"]
    assert BTN_APP in str(ADMIN_KEYBOARD_V9)
    assert BTN_APP in str(USER_KEYBOARD_V9)
    print("admin_panel_runtime_v10 compatibility self-test passed")


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
