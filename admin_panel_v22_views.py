from __future__ import annotations

import html
from typing import Any

from admin_panel_runtime_v20 import BRAND_NAME


class TelegramPanelViewsV22Mixin:
    def show_stats(self, days: int = 1) -> None:
        totals = self.period_totals(self.snapshot().stats, days)
        summary = self.load_registry().get("summary", {})
        title = "сегодня" if days == 1 else f"за {days} дней"
        text = (
            f"📊 <b>{BRAND_NAME}: статистика {title}</b>\n\n"
            f"Проверок источников: {totals.get('checks', 0)}\n"
            f"Просмотрено сообщений: {totals.get('messages_scanned', 0)}\n"
            f"Найдено публикаций с колёсами: {totals.get('wheel_posts', 0)}\n"
            f"Повторные уведомления подавлены: {totals.get('duplicates_suppressed', 0)}\n\n"
            f"Всего источников: {summary.get('total_sources', 0)}\n"
            f"Проверено: {summary.get('checked_sources', 0)}\n"
            f"Доступно: {summary.get('available_sources', 0)}\n"
            f"Недоступно: {summary.get('unavailable_sources', 0)}"
        )
        rows = [[{"text": "Сегодня", "callback_data": "page:stats:1"}, {"text": "7 дней", "callback_data": "page:stats:7"}, {"text": "30 дней", "callback_data": "page:stats:30"}], [{"text": "🏆 Рейтинг источников", "callback_data": "page:ranking"}]]
        self.send(text, reply_markup=self.with_nav(rows))

    def show_active(self) -> None:
        admin = self.is_admin()
        items = self._collect_current_wheels()
        if not admin:
            items = [x for x in items if str(x.get("admin_verdict") or "") == "active"]
        personal = {str(x).casefold() for x in self.personal_wheels()}
        if not items:
            self.send("🔥 <b>Подтверждённых активных колёс сейчас нет.</b>", reply_markup=self.with_nav([[{"text": "🔄 Обновить", "callback_data": "refresh:active"}]]))
            return
        lines = [f"🔥 <b>{BRAND_NAME}: колёса — {len(items)}</b>", ""]
        buttons: list[list[dict[str, str]]] = []
        for index, item in enumerate(items[:25], 1):
            key = str(item.get("_key") or item.get("identifier") or "").casefold()
            verdict = str(item.get("admin_verdict") or "pending")
            deadline = self.parse_dt(item.get("deadline"))
            lines += [
                f"<b>{index}. <code>{html.escape(str(item.get('identifier') or key))}</code></b>",
                "✅ подтверждено администратором" if verdict == "active" else "🟣 ожидает решения администратора",
                f"⏳ {html.escape(self.remaining(deadline) if deadline else 'время не определено')}",
                f"📡 @{html.escape(str(item.get('source') or 'неизвестно'))}",
            ]
            url = str(item.get("url") or "")
            if url:
                buttons.append([{"text": f"🎡 Открыть {index}", "url": url}])
            if admin:
                row = []
                if verdict != "active":
                    row.append({"text": "✅ Участвую", "callback_data": f"wheel:part:{key}"})
                row.append({"text": "🚫 Неактивное", "callback_data": f"wheel:inactive:{key}"})
                buttons.append(row)
                if not deadline:
                    buttons.append([{"text": "⏱ Указать время", "callback_data": f"wheel:time:{key}"}])
            else:
                buttons.append([{"text": "✅ Отмечено" if key in personal else "✅ Я участвую", "callback_data": f"wheel:part:{key}"}, {"text": "Скрыть", "callback_data": f"wheel:inactive:{key}"}])
        self.send("\n".join(lines)[:4096], reply_markup=self.with_nav(buttons))

    def show_sources(self) -> None:
        summary = self.load_registry().get("summary", {})
        text = (
            "📡 <b>Источники</b>\n\n"
            f"Всего: <b>{summary.get('total_sources', 0)}</b>\n"
            f"Проверено: <b>{summary.get('checked_sources', 0)}</b>\n"
            f"Доступно: <b>{summary.get('available_sources', 0)}</b>\n"
            f"Недоступно: <b>{summary.get('unavailable_sources', 0)}</b>\n"
            f"Ожидают проверки: <b>{summary.get('not_checked_sources', 0)}</b>\n\n"
            "Все источники показаны единым списком."
        )
        rows = [[{"text": "📋 Открыть список", "callback_data": "source_list:0"}]]
        if self.is_admin():
            rows.append([{"text": "➕ Добавить источник", "callback_data": "source:add"}])
        self.send(text, reply_markup=self.with_nav(rows))

    def show_source_list(self, page: int = 0) -> None:
        rows = sorted(self.load_registry().get("sources", {}).items(), key=lambda x: str(x[0]).casefold())
        per_page = 10
        page = max(0, min(page, max(0, (len(rows) - 1) // per_page)))
        part = rows[page * per_page:(page + 1) * per_page]
        marks = {"available": "🟢", "unavailable": "🔴", "not_checked": "🟡", "excluded": "⚫"}
        lines = [f"📡 <b>Все источники: {len(rows)}</b>", ""]
        keyboard = []
        for source, entry in part:
            status = str(entry.get("status") or "not_checked")
            lines.append(f"{marks.get(status, '⚪')} @{html.escape(str(source))} — {html.escape(str(entry.get('status_label') or status))}")
            keyboard.append([{"text": f"@{source}", "callback_data": f"source_detail:{source}"}])
        nav = []
        if page > 0:
            nav.append({"text": "◀️", "callback_data": f"source_list:{page - 1}"})
        if (page + 1) * per_page < len(rows):
            nav.append({"text": "▶️", "callback_data": f"source_list:{page + 1}"})
        if nav:
            keyboard.append(nav)
        self.send("\n".join(lines), reply_markup=self.with_nav(keyboard))

    def show_source_detail(self, source: str) -> None:
        actual, entry = self._case(self.load_registry().get("sources", {}), source)
        reputation = self.load_reputation()
        _, rating = self._case(reputation.get("sources", {}), actual)
        place = next((x.get("place") for x in reputation.get("ranking", []) if str(x.get("source") or "").casefold() == actual.casefold()), "—")
        lines = [
            f"📡 <b>@{html.escape(actual)}</b>", "",
            f"Состояние: <b>{html.escape(str(entry.get('status_label') or 'нет данных'))}</b>",
            f"Причина: {html.escape(str(entry.get('reason') or 'нет данных'))}",
            f"Последняя проверка: {self.fmt_dt(entry.get('last_checked_at'))}", "",
            f"Место: {place}", f"Оценка: <b>{rating.get('score', 0)}</b>",
            f"Подтверждено: {rating.get('confirmed_wheels', 0)}", f"Неактивных: {rating.get('inactive_wheels', 0)}",
            f"Успешность: {rating.get('success_rate', 0)}%", f"Динамика: {int(rating.get('trend', 0) or 0):+d}", "", "<b>История начислений и списаний</b>"
        ]
        history = [x for x in rating.get("events", []) if isinstance(x, dict)][:10]
        lines += [f"• {int(x.get('delta', 0) or 0):+d} — {html.escape(str(x.get('reason') or x.get('signal') or 'событие'))}" for x in history]
        if not history:
            lines.append("• история ещё не сформирована")
        self.send("\n".join(lines)[:4096], reply_markup=self.with_nav([[{"text": "Открыть Telegram", "url": f"https://t.me/{actual}"}]]))

    def show_ranking(self) -> None:
        ranking = [x for x in self.load_reputation().get("ranking", []) if isinstance(x, dict)]
        lines = ["🏆 <b>Рейтинг источников</b>", ""]
        buttons = []
        for item in ranking[:20]:
            place, source = int(item.get("place", 0) or 0), str(item.get("source") or "")
            lines.append(f"{place}. <b>@{html.escape(source)}</b> — {int(item.get('score', 0) or 0)} балл.\n   подтверждено {int(item.get('confirmed_wheels', 0) or 0)}, неактивных {int(item.get('inactive_wheels', 0) or 0)}, успешность {item.get('success_rate', 0)}%, динамика {int(item.get('trend', 0) or 0):+d}")
            buttons.append([{"text": f"{place}. @{source}", "callback_data": f"source_detail:{source}"}])
        if not ranking:
            lines.append("Рейтинг сформируется после первых административных решений.")
        self.send("\n".join(lines)[:4096], reply_markup=self.with_nav(buttons))

    def show_reports(self) -> None:
        self.show_stats(1)

    def show_settings(self) -> None:
        enabled = bool(self._user_record().get("notifications_enabled", True))
        lines = ["🔔 <b>Уведомления</b>", "", f"Обычные пользовательские уведомления: {'включены' if enabled else 'отключены' }."]
        rows = [[{"text": f"Уведомления {'✅' if enabled else '❌'}", "callback_data": "setting:notifications"}]]
        if self.is_admin():
            lines += ["Административные уведомления включены автоматически по роли.", "Отключить их отдельно нельзя."]
            rows += [[{"text": "⏱ Интервал проверки", "callback_data": "page:interval"}], [{"text": "🛠 Управление системой", "callback_data": "page:control"}]]
            if self.is_owner():
                rows.append([{"text": "👥 Доступ и администраторы", "callback_data": "page:access"}])
        self.send("\n".join(lines), reply_markup=self.with_nav(rows))
