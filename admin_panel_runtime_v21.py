from __future__ import annotations

import argparse

from bbvg.bot.users import (
    ADMIN_NOTIFICATION_OPTIONS,
    MINIAPP_RELEASE,
    MINIAPP_URL,
    USER_NOTIFICATION_OPTIONS,
    UserManagementRuntime,
    self_test as users_self_test,
)

TelegramPanelRuntimeV21 = UserManagementRuntime


def self_test() -> None:
    users_self_test()
    assert TelegramPanelRuntimeV21 is UserManagementRuntime
    print("admin_panel_runtime_v21 compatibility alias self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV21().run()


if __name__ == "__main__":
    raise SystemExit(main())
