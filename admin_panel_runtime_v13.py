from __future__ import annotations

import argparse

from admin_panel_runtime_v9 import TelegramPanelRuntimeV9
from bbvg.bot.foundation import PanelFoundationMixin, self_test as foundation_self_test


class TelegramPanelRuntimeV13(PanelFoundationMixin, TelegramPanelRuntimeV9):
    """Compatibility entrypoint for the consolidated panel foundation."""


def self_test() -> None:
    foundation_self_test()
    assert TelegramPanelRuntimeV13.__mro__[1:3] == (
        PanelFoundationMixin,
        TelegramPanelRuntimeV9,
    )
    print("admin_panel_runtime_v13 compatibility self-test passed")


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
