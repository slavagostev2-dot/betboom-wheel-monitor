from __future__ import annotations

import argparse
import html
import math
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from admin_panel_runtime_v38 import ACTIVE_PAGE_SIZE, TelegramPanelRuntimeV38


UTC = timezone.utc
WHEEL_COLOR_EMOJIS = ("🔵", "🟢", "🟡", "🟣", "🟠", "🔴")


class TelegramPanelRuntimeV39(TelegramPanelRuntimeV38):
    """Color-linked wheel actions, concise home screen and rated completion."""

    RUNTIME_VERSION = 39

    @staticmethod
    def wheel_color(index: int) -> str:
        position = max(1, int(index)) - 1
        return WHEEL_COLOR_EMOJIS[position % len(WHEEL_COLOR_EMOJIS)]

    def show_menu(self, *, clear_stack: bool = True) -> None:
        if clear_stack:
            self.navigation[str(self.current_user_id or "guest")] = ["menu"]
        role = self.role_for(self.current_user_id)
        admin = role in {"owner", "admin"}
        text = (
            "🎡 <b>BB V.G.</b>\n\n"
            "Находит колёса BetBoom, показывает время прокрутки и хранит отметки участия.\n\n"
            f"Ваша роль: <b>{html.escape(self.role_name(role))}</b>\n\n"
            "Выберите раздел."
        )
        self.send(
            text,
            reply_markup={"inline_keyboard": self.compact_menu_rows(admin)},
        )

    def show_active(self, page: int = 0) -> None:
        snap = self.snapshot(force=True)
        items = self._collect_current_wheels()
        participating = self._joined_wheel_keys(snap)
        monitor_status = self._monitor_status()
        checked_at = monitor_status.get("last_successful_iteration_at")
        state_line = (
            f"🟢 обновлено {self.fmt_dt(checked_at)} ({self.age_text(checked_at)})"
            if checked_at
            else "⚪ ожидаются данные проверки"
        )
        if not items:
            self.send(
                "🔥 <b>Активных колёс сейчас нет.</b>\n\n"
                f"Состояние: {state_line}",
                reply_markup=self.with_nav(
                    [[{"text": "🔄 Обновить", "callback_data": "refresh:active:0"}]]
                ),
            )
            return

        pages = max(1, math.ceil(len(items) / ACTIVE_PAGE_SIZE))
        page = max(0, min(int(page), pages - 1))
        start = page * ACTIVE_PAGE_SIZE
        visible = items[start : start + ACTIVE_PAGE_SIZE]
        admin = self.is_admin()
        lines = [
            f"🔥 <b>Активные колёса: {len(items)}</b>",
            f"Состояние: {state_line}",
        ]
        if pages > 1:
            lines.append(f"Страница: <b>{page + 1} из {pages}</b>")
        lines.append("")
        buttons: list[list[dict[str, str]]] = []

        for offset, item in enumerate(visible):
            index = start + offset + 1
            color = self.wheel_color(index)
            identifier = str(item.get("identifier") or item.get("_key") or "колесо")
            key = str(item.get("_key") or identifier).casefold()
            deadline = self.parse_dt(item.get("deadline"))
            available_at = self.parse_dt(item.get("available_at"))
            joined = identifier.casefold() in participating or key in participating
            sources = self._sources_for_item(snap, key, item)
            shown_sources = sources[:3]
            source_text = ", ".join(f"@{source}" for source in shown_sources)
            if len(sources) > len(shown_sources):
                source_text += f" и ещё {len(sources) - len(shown_sources)}"
            source_text = source_text or "источник неизвестен"
            if available_at and available_at > datetime.now(UTC):
                timing = f"🟡 Участие откроется через {self.remaining(available_at)}"
            elif available_at and item.get("availability_status") == "available":
                timing = "🟢 Доступно сейчас · 🔴 время прокрутки неизвестно"
            else:
                timing = self.remaining(deadline) if deadline else "🔴 Время прокрутки неизвестно"
            joined_text = "✅ участвуете" if joined else "❌ участие не отмечено"
            shown_identifier = identifier if len(identifier) <= 90 else identifier[:87] + "…"
            lines.extend(
                [
                    f"<b>{index}. <code>{html.escape(shown_identifier)}</code> {color}</b>",
                    f"{html.escape(timing)}",
                    f"📡 {html.escape(source_text)} · {joined_text}",
                    "",
                ]
            )

            url = str(item.get("url") or "")
            if url:
                buttons.append(
                    [{"text": f"{color} 🎡 {index} · Открыть колесо", "url": url}]
                )
            if not joined:
                buttons.append(
                    [
                        {
                            "text": f"{color} ✅ {index} · Участвую",
                            "callback_data": self._wheel_callback("part", key),
                        }
                    ]
                )
            if admin:
                buttons.append(
                    [
                        {
                            "text": f"{color} 🏁 {index} · Завершено",
                            "callback_data": self._wheel_callback("finished", key),
                        },
                        {
                            "text": f"{color} 🚫 {index} · Неактивное",
                            "callback_data": self._wheel_callback("inactive", key),
                        },
                    ]
                )
                time_label = "Изменить время" if deadline else "Указать время"
                buttons.append(
                    [
                        {
                            "text": f"{color} ⏱ {index} · {time_label}",
                            "callback_data": self._wheel_callback("time", key),
                        }
                    ]
                )
            else:
                buttons.append(
                    [
                        {
                            "text": f"{color} 🙈 {index} · Скрыть у меня",
                            "callback_data": self._wheel_callback("inactive", key),
                        }
                    ]
                )

        pager: list[dict[str, str]] = []
        if page > 0:
            pager.append(
                {"text": "◀️ Назад", "callback_data": f"page:active:{page - 1}"}
            )
        if page < pages - 1:
            pager.append(
                {"text": "Вперёд ▶️", "callback_data": f"page:active:{page + 1}"}
            )
        if pager:
            buttons.append(pager)
        buttons.append(
            [{"text": "🔄 Обновить", "callback_data": f"refresh:active:{page}"}]
        )
        self.send("\n".join(lines).rstrip(), reply_markup=self.with_nav(buttons))


def self_test() -> None:
    panel = TelegramPanelRuntimeV39()
    captured: list[tuple[str, dict[str, Any]]] = []
    panel.current_user_id = "1"
    panel.current_role = "admin"
    panel.navigation = {"1": ["menu"]}
    panel.role_for = lambda user_id: "admin"  # type: ignore[method-assign]
    panel.role_name = lambda role: "Администратор"  # type: ignore[method-assign]
    panel.is_admin = lambda: True  # type: ignore[method-assign]
    panel.send = lambda text, **kwargs: captured.append((text, kwargs)) or {}  # type: ignore[method-assign]

    panel.show_menu()
    menu_text = captured[-1][0]
    assert "Находит колёса BetBoom" in menu_text
    assert "Ваша роль: <b>Администратор</b>" in menu_text

    panel.snapshot = lambda force=False: SimpleNamespace(  # type: ignore[method-assign]
        state={"active_wheels": {}},
        stats={"sources": {}, "daily": {}},
        health={"sources": {}},
        discovery={"sources": {}},
        fast=[],
        nightly=[],
    )
    panel._monitor_status = lambda: {}  # type: ignore[method-assign]
    panel._joined_wheel_keys = lambda snap: set()  # type: ignore[method-assign]
    panel._sources_for_item = lambda snap, key, item: ["mechanogun"]  # type: ignore[method-assign]
    panel._collect_current_wheels = lambda: [  # type: ignore[method-assign]
        {
            "_key": "wheel-a",
            "identifier": "wheel-a",
            "source": "mechanogun",
            "url": "https://betboom.ru/freestream/wheel-a",
        }
    ]
    panel.show_active()
    active_text, kwargs = captured[-1]
    assert "1. <code>wheel-a</code> 🔵" in active_text
    wheel_buttons = [
        button
        for row in kwargs["reply_markup"]["inline_keyboard"]
        for button in row
        if "wheel-a" in str(button.get("url") or "")
        or str(button.get("callback_data") or "").startswith("wheel:")
    ]
    assert wheel_buttons
    assert all("🔵" in str(button.get("text") or "") for button in wheel_buttons)
    print("admin panel v39 color-linked controls self-test passed")


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
