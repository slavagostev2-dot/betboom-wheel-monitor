from __future__ import annotations

import argparse

from admin_panel_runtime_v21 import TelegramPanelRuntimeV21
from admin_panel_v22_access import TelegramPanelAccessV22Mixin
from admin_panel_v22_callbacks import TelegramPanelCallbacksV22Mixin
from admin_panel_v22_views import TelegramPanelViewsV22Mixin


class TelegramPanelRuntimeV22(
    TelegramPanelCallbacksV22Mixin,
    TelegramPanelViewsV22Mixin,
    TelegramPanelAccessV22Mixin,
    TelegramPanelRuntimeV21,
):
    """BB V.G. v22 unified source and rating control center."""


def self_test() -> None:
    labels = [button["text"] for row in TelegramPanelRuntimeV22.compact_menu_rows(True) for button in row]
    assert "🌙 Ночное наблюдение" not in labels
    assert "🏆 Рейтинг источников" in labels
    assert "⚠️ Ошибки источников" not in str(labels)
    print("admin_panel_runtime_v22 unified sources self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV22().run()


if __name__ == "__main__":
    raise SystemExit(main())
