from __future__ import annotations

import argparse

from admin_panel_runtime_v10 import TelegramPanelRuntimeV10
from bbvg.bot.foundation import (
    CLOUDFLARE_APP_URL,
    DEPLOYMENT_PATH,
    FALLBACK_APP_URL,
    self_test as foundation_self_test,
)


class TelegramPanelRuntimeV11(TelegramPanelRuntimeV10):
    """Compatibility entrypoint for the consolidated panel foundation."""


def self_test() -> None:
    foundation_self_test()
    assert CLOUDFLARE_APP_URL.endswith(".pages.dev/")
    assert FALLBACK_APP_URL.startswith("https://raw.githack.com/")
    assert DEPLOYMENT_PATH == "miniapp_deployment.json"
    print("admin_panel_runtime_v11 compatibility self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV11().run()


if __name__ == "__main__":
    raise SystemExit(main())
