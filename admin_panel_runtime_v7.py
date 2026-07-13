from __future__ import annotations

import argparse
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import monitor
from admin_panel_runtime_v6 import (
    ADMIN_KEYBOARD_V6,
    BTN_INTELLIGENCE,
    BTN_NIGHTLY,
    TelegramPanelRuntimeV6,
)

UTC = monitor.UTC
MINI_APP_URL = "https://slavagostev2-dot.github.io/betboom-wheel-monitor/"

ADMIN_KEYBOARD_V7 = {
    "keyboard": [
        [{"text": "📊 Статистика"}, {"text": "🔥 Активные колёса"}],
        [{"text": "📡 Источники"}, {"text": "🏆 Рейтинг каналов"}],
        [{"text": "📅 Отчёты"}, {"text": BTN_NIGHTLY}],
        [{"text": BTN_INTELLIGENCE}, {"text": "✅ Проверка работы"}],
        [{"text": "🛠 Управление"}, {"text": "⚙️ Настройки"}],
        [{"text": "📱 Открыть приложение", "web_app": {"url": MINI_APP_URL}}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Панель BetBoom Monitor",
}

USER_KEYBOARD_V7 = {
    "keyboard": [
        [{"text": "📊 Статистика"}, {"text": "🔥 Активные колёса"}],
        [{"text": "📡 Источники"}, {"text": "🏆 Рейтинг каналов"}],
        [{"text": "📅 Отчёты"}, {"text": "✅ Проверка работы"}],
        [{"text": "📱 Открыть приложение", "web_app": {"url": MINI_APP_URL}}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "BetBoom Monitor",
}


class TelegramPanelRuntimeV7(TelegramPanelRuntimeV6):
    """Panel v7: deterministic routing, correct scheduled wheels and Mini App entry."""

    def show_menu(self, *, clear_stack: bool = True) -> None:
        if clear_stack:
            self.navigation[str(self.current_user_id or "guest")] = ["menu"]
        role = self.role_for(self.current_user_id)
        keyboard = ADMIN_KEYBOARD_V7 if role in {"owner", "admin"} else USER_KEYBOARD_V7
        title = "панель управления" if role in {"owner", "admin"} else "информационная панель"
        self.send(
            f"🎡 <b>BetBoom Monitor — {title}</b>\n\n"
            f"Ваш доступ: <b>{self.role_name(role)}</b>\n"
            "Можно пользоваться обычными кнопками или открыть отдельное приложение.",
            reply_markup=keyboard,
        )

    def _collect_current_wheels(self) -> list[dict[str, Any]]:
        snap = self.snapshot()
        state = snap.state
        combined: dict[str, dict[str, Any]] = {}
        for key, raw in state.get("active_wheels", {}).items():
            if isinstance(raw, dict):
                item = dict(raw)
                item["_key"] = str(key)
                item["_stored_state"] = "active"
                combined[self._entry_key(str(key), item)] = item
        for raw in state.get("pending_posts", {}).values():
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            identity = self._entry_key(str(item.get("url") or ""), item)
            if not identity:
                continue
            item.setdefault("_key", identity)
            item.setdefault("_stored_state", "pending")
            # Prefer the record containing a future Telegram deadline.
            existing = combined.get(identity)
            self._restore_telegram_deadline(item)
            if existing is None:
                combined[identity] = item
            else:
                self._restore_telegram_deadline(existing)
                existing_deadline = self.parse_dt(existing.get("deadline"))
                item_deadline = self.parse_dt(item.get("deadline"))
                if item_deadline and (not existing_deadline or item_deadline > existing_deadline):
                    combined[identity] = item

        now = datetime.now(UTC)
        for item in combined.values():
            self._restore_telegram_deadline(item)

        results: dict[str, tuple[str, Any]] = {}
        inspectable = {key: item for key, item in combined.items() if item.get("url")}
        if inspectable:
            with ThreadPoolExecutor(max_workers=min(6, len(inspectable))) as pool:
                futures = {pool.submit(self._inspect_entry, item): key for key, item in inspectable.items()}
                for future in as_completed(futures):
                    results[futures[future]] = future.result()

        visible: list[dict[str, Any]] = []
        for identity, item in combined.items():
            deadline = self.parse_dt(item.get("deadline"))
            if deadline and deadline <= now:
                continue
            status, inspection = results.get(identity, ("unknown", None))

            # A reliable future Telegram draw time has priority over an incomplete
            # public BetBoom page. The page check is still authoritative after the
            # Telegram deadline expires.
            if deadline and deadline > now:
                item["_live_state"] = "scheduled"
                if status == "active":
                    item["_live_state"] = "active"
                    if inspection and inspection.deadline:
                        item["deadline"] = inspection.deadline.isoformat()
                visible.append(item)
                continue

            if status == "inactive":
                continue
            if status == "active":
                item["_live_state"] = "active"
                if inspection and inspection.deadline:
                    item["deadline"] = inspection.deadline.isoformat()
            else:
                first_seen = self.parse_dt(item.get("first_seen_at") or item.get("message_date"))
                if not first_seen or now - first_seen > timedelta(minutes=30):
                    continue
                item["_live_state"] = "checking"
            visible.append(item)

        visible.sort(
            key=lambda item: (
                self.parse_dt(item.get("deadline")) is None,
                self.parse_dt(item.get("deadline")) or datetime.max.replace(tzinfo=UTC),
                str(item.get("message_date") or ""),
            )
        )
        return visible

    def handle_message(self, message: dict[str, Any]) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        self.set_context(chat.get("id"), sender.get("id"))
        text = str(message.get("text") or "").strip()
        command = text.split("@", 1)[0].split(maxsplit=1)[0].casefold() if text else ""

        if command in {"/start", "/menu"}:
            self.pending_input.pop(int(self.current_user_id), None)
            self.show_menu(clear_stack=True)
            return

        direct_pages = {
            "📊 Статистика": "stats:1",
            "🔥 Активные колёса": "active",
            "📡 Источники": "sources",
            "🏆 Рейтинг каналов": "ranking",
            "📅 Отчёты": "reports",
            "✅ Проверка работы": "status",
            "🛠 Управление": "control",
            "⚙️ Настройки": "settings",
            BTN_NIGHTLY: "discovery",
            BTN_INTELLIGENCE: "intelligence",
        }
        command_pages = {
            "/stats": "stats:1",
            "/active": "active",
            "/wheels": "active",
            "/sources": "sources",
            "/ranking": "ranking",
            "/reports": "reports",
            "/status": "status",
        }
        page = direct_pages.get(text) or command_pages.get(command)
        if page:
            self.navigation[str(self.current_user_id)] = ["menu"]
            self.open_page(page)
            return
        super().handle_message(message)


def self_test() -> None:
    bot = TelegramPanelRuntimeV7()
    assert len(ADMIN_KEYBOARD_V7["keyboard"]) == 6
    assert "📡 Источники" in str(ADMIN_KEYBOARD_V7)
    assert MINI_APP_URL.startswith("https://")
    message_date = datetime.now(UTC) - timedelta(hours=1)
    item = {"message_date": message_date.isoformat(), "message_text": "ИТОГИ ЧЕРЕЗ 10 ЧАСОВ"}
    deadline = bot._restore_telegram_deadline(item)
    assert deadline and deadline > datetime.now(UTC)
    print("admin_panel_runtime_v7 self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return TelegramPanelRuntimeV7().run()


if __name__ == "__main__":
    raise SystemExit(main())
