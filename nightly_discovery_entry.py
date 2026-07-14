from __future__ import annotations

import html

import monitor
import nightly_discovery
import notification_router
import telegram_transport

notification_router.install(monitor)
telegram_transport.install(monitor)

_original_fetch_page = nightly_discovery.fetch_public_channel_page


def fetch_page_on_primary_domain(
    username: str,
    before: int | None = None,
    *,
    attempts: int = 2,
    timeout: int | None = None,
):
    messages = _original_fetch_page(
        username, before, attempts=attempts, timeout=timeout
    )
    return [
        monitor.Message(
            source=message.source,
            message_id=message.message_id,
            date=message.date,
            text=telegram_transport.rewrite_telegram_text(message.text),
            message_url=telegram_transport.public_message_url(
                message.source or username, message.message_id
            ),
        )
        for message in messages
    ]


nightly_discovery.fetch_public_channel_page = fetch_page_on_primary_domain


def main() -> int:
    manual_run = nightly_discovery.MANUAL_RUN

    # Discovery only recommends candidates. All 66 configured sources remain in
    # the permanent monitor and are never moved to a separate night-only list.
    def keep_lists_unchanged(path, values, header):
        print(f"Candidate recommendations collected; {path.name} remains unchanged.")

    nightly_discovery.write_sources = keep_lists_unchanged
    nightly_discovery.MANUAL_RUN = False

    result = nightly_discovery.main()

    state = nightly_discovery.load_discovery_state()
    recommended = [str(value) for value in state.get("promoted", []) if str(value)]
    state["recommended_for_primary"] = recommended
    state["promoted"] = []
    state["catalog_size"] = len(
        nightly_discovery.unique(monitor.read_list(nightly_discovery.CATALOG_PATH))
    )
    state["active_size"] = len(
        nightly_discovery.unique(monitor.read_list(nightly_discovery.ACTIVE_PATH))
    )
    state["telegram_domain"] = telegram_transport.PRIMARY_DOMAIN
    nightly_discovery.save_discovery_state(state)

    if manual_run:
        recommended_text = ", ".join(f"@{value}" for value in recommended) or "нет"
        monitor.send_message(
            "✅ <b>Поиск новых источников завершён</b>\n\n"
            f"Постоянных источников: {state.get('active_size', 0)}\n"
            f"Новых кандидатов: {html.escape(recommended_text)}\n"
            f"Новых уведомлений о колёсах: {state.get('notifications', 0)}\n"
            f"Повторов подавлено: {state.get('duplicate_wheels', 0)}\n"
            f"Ошибок: {state.get('error_count', 0)}\n\n"
            f"Проверка выполнена через {telegram_transport.PRIMARY_DOMAIN}."
        )

    return result


if __name__ == "__main__":
    raise SystemExit(main())
