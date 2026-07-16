from __future__ import annotations

import argparse

from bbvg.bot.interface import PanelInterfaceRuntime
from bbvg.bot.interface import self_test as interface_self_test


class TelegramPanelRuntimeV16(PanelInterfaceRuntime):
    """Compatibility entrypoint for the consolidated panel interface."""


def self_test() -> None:
    interface_self_test()
    print("admin_panel_runtime_v16 compatibility self-test passed")


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
