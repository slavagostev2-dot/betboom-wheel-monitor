from __future__ import annotations

import argparse
from urllib.parse import quote

from admin_panel_runtime_v20 import TelegramPanelRuntimeV20

MINIAPP_REFERENCE_URL = (
    "https://raw.githack.com/slavagostev2-dot/"
    "betboom-wheel-monitor/main/docs/index.html"
)


class TelegramPanelRuntimeV21(TelegramPanelRuntimeV20):
    """Panel v21: BB V.G. reference Mini App interface."""

    def miniapp_url_for_chat(self) -> str:
        params = ["v=5.0.0"]
        username = self.bot_username()
        if username:
            params.append(f"bot={quote(username)}")
        return MINIAPP_REFERENCE_URL + "?" + "&".join(params)


def self_test() -> None:
    assert MINIAPP_REFERENCE_URL.endswith("docs/index.html")
    assert "v=5.0.0" in TelegramPanelRuntimeV21.miniapp_url_for_chat.__code__.co_consts
    print("admin_panel_runtime_v21 reference UI self-test passed")


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
