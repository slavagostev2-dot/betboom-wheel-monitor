from __future__ import annotations

import argparse
from urllib.parse import quote

from admin_panel_runtime_v17 import TelegramPanelRuntimeV17

MINIAPP_V3_FALLBACK = (
    "https://raw.githack.com/slavagostev2-dot/"
    "betboom-wheel-monitor/main/docs/index.html"
)


class TelegramPanelRuntimeV18(TelegramPanelRuntimeV17):
    """Panel v18: serve Mini App v3 immediately, then prefer confirmed Cloudflare v3."""

    def miniapp_url_for_chat(self) -> str:
        deployment = self.miniapp_deployment()
        status = str(deployment.get("status") or "")
        version = int(deployment.get("version") or 0)
        cloudflare_url = str(deployment.get("url") or "").strip()
        if status == "deployed" and version >= 3 and cloudflare_url.startswith("https://"):
            base = cloudflare_url
        else:
            base = MINIAPP_V3_FALLBACK

        params = ["v=3.0.0"]
        username = self.bot_username()
        if username:
            params.append(f"bot={quote(username)}")
        separator = "&" if "?" in base else "?"
        return base + separator + "&".join(params)


def self_test() -> None:
    assert MINIAPP_V3_FALLBACK.startswith("https://raw.githack.com/")
    assert MINIAPP_V3_FALLBACK.endswith("docs/index.html")
    print("admin_panel_runtime_v18 Mini App fallback self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV18().run()


if __name__ == "__main__":
    raise SystemExit(main())
