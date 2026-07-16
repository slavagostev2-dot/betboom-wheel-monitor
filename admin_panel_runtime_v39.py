from __future__ import annotations

import argparse
import html
from typing import Any

from admin_panel_runtime_v31 import SUMMARY_PERIODS
from admin_panel_runtime_v38 import TelegramPanelRuntimeV38


class TelegramPanelRuntimeV39(TelegramPanelRuntimeV38):
    """Stable v38 control center with direct in-process summary delivery."""

    RUNTIME_VERSION = 39

    def handle_callback(self, query: dict[str, Any]) -> None:
        data = str(query.get("data") or "")
        if data == "summary:send" or data.startswith("summary:send:") or data == "control:daily":
            self._prepare_callback_user(query)
            query_id = str(query.get("id") or "")
            if not self.is_admin():
                self.answer(query_id, "Недоступно")
                return
            if data == "summary:send":
                self.answer(query_id, "Выберите период")
                self.show_send_summary_menu()
                return

            period = "daily" if data == "control:daily" else data.rsplit(":", 1)[1]
            if period not in SUMMARY_PERIODS:
                self.answer(query_id, "Неизвестный период")
                return

            days, label = SUMMARY_PERIODS[period]
            self.answer(query_id, "Сводка сформирована")
            self.send(
                f"📨 <b>{html.escape(label)} сводка</b>\n\n"
                "Сводка сформирована непосредственно ботом без отдельного технического запуска.",
                reply_markup=self.with_nav(),
            )
            self.show_period_report(days)
            return
        super().handle_callback(query)


def self_test() -> None:
    panel = TelegramPanelRuntimeV39()
    assert panel.RUNTIME_VERSION == 39
    assert issubclass(TelegramPanelRuntimeV39, TelegramPanelRuntimeV38)
    assert SUMMARY_PERIODS["daily"][0] == 1
    assert SUMMARY_PERIODS["weekly"][0] == 7
    assert SUMMARY_PERIODS["monthly"][0] == 30
    print("BB V.G. v39 stable direct summary delivery self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV39().run()


if __name__ == "__main__":
    raise SystemExit(main())
