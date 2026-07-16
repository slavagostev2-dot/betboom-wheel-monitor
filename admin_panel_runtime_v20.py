from __future__ import annotations

import argparse

from bbvg.bot.wheels import (
    DEADLINE_GRACE_MINUTES,
    HIDDEN_WHEEL_DAYS,
    WheelInteractionRuntime,
    self_test as wheels_self_test,
)


class TelegramPanelRuntimeV20(WheelInteractionRuntime):
    """Compatibility entrypoint for the consolidated wheel interaction subsystem."""


def self_test() -> None:
    wheels_self_test()
    print("admin_panel_runtime_v20 compatibility self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV20().run()


if __name__ == "__main__":
    raise SystemExit(main())
