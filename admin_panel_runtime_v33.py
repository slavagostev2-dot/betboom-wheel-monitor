from __future__ import annotations

import argparse

from admin_panel_runtime_v32 import TelegramPanelRuntimeV32
from bbvg.bot.users import (
    ADMIN_NOTIFICATION_OPTIONS,
    SUMMARY_NOTIFICATION_OPTIONS,
    USER_NOTIFICATION_OPTIONS,
    WHEEL_NOTIFICATION_OPTIONS,
    UserSettingsMixin,
    self_test as users_self_test,
)


class TelegramPanelRuntimeV33(UserSettingsMixin, TelegramPanelRuntimeV32):
    """Compatibility entrypoint for consolidated user settings and privacy."""


def self_test() -> None:
    users_self_test()
    assert {key for key, _, _ in WHEEL_NOTIFICATION_OPTIONS} == {
        "wheels",
        "wheel_final_reminders",
        "wheel_draw_alerts",
    }
    assert len(SUMMARY_NOTIFICATION_OPTIONS) == 2
    assert len(ADMIN_NOTIFICATION_OPTIONS) == 3
    print("admin_panel_runtime_v33 compatibility self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV33().run()


if __name__ == "__main__":
    raise SystemExit(main())
