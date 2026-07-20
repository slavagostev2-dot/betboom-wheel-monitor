# BB V.G. — мониторинг колёс BetBoom

BB V.G. — автоматизированный проект для мониторинга утверждённых источников, обнаружения колёс BetBoom, управления lifecycle событий, уведомлений, персонального участия, рейтинга источников и администрирования через Telegram Control Center.

Перед изменениями обязательно прочитать [`AGENTS.md`](AGENTS.md).

## Текущий production-контур

### Telegram Control Center

Production workflow: `.github/workflows/admin-bot.yml`.

Текущая команда запуска: `python admin_panel_runtime_v41.py`.

Стабильная архитектура находится в `bbvg/bot/`: `control_center.py`, `runtime.py`, `foundation.py`, `interface.py`, `users.py`, `sources.py`, `source_requests.py`, `storage.py`, `wheels.py`, `profile.py`, `natural_language_admin.py`.

После этапа 2B `admin_panel_runtime_v41.py` является тонким compatibility entrypoint. Фактический production-слой Control Center находится в `bbvg/bot/control_center.py`; прежняя команда запуска сохранена для совместимости workflow.

## Мониторинг колёс

Production workflow: `.github/workflows/monitor.yml`.

Фактический цикл запускает `bbvg_monitor_main.py`.

Ключевые компоненты: `monitor.py`, `bbvg_monitor_runtime.py`, `monitor_data.py`, `monitor_health.py`, `telegram_transport.py`, `telegram_post_links_v2.py`, `wheel_event_runtime.py`, `wheel_metadata_quality.py`, `wheel_publications_v2.py`, `wheel_lifecycle_v2.py`, `personal_reminder_filter.py`, `personal_wheel_voting.py`.

Часть текущего runtime собирается install/patch-модулями. Versioned-имя само по себе не означает, что файл можно удалить.

## Источники

- `public_sources.txt` — основной утверждённый production tier;
- `source_catalog.txt` — вручную утверждённый nightly tier;
- `partners_catalog.json` — партнёрские metadata;
- `identifier_sources.json` — mappings.

Discovery не должен автоматически превращать произвольные найденные кандидаты в production-источники. Правила изменения source tiers описаны в `AGENTS.md`.

## System Health

Production workflow: `.github/workflows/system-health.yml`.

На момент завершения этапа 1 используется цепочка `system_checks_v3.py → system_checks_v2.py → system_checks.py`. Она является подтверждённым кандидатом на последующую консолидацию, но не на прямое удаление.

## Auto-participation

Основные компоненты: `.github/workflows/auto-participation.yml`, `betboom_auto_participation.py`, `auto_participation_dispatch.py`, `auto_participation_worker.py`.

В ходе этапа 1 обнаружен неработающий optional probe path: workflow ссылается на отсутствующий `auto_participation_probe.py` и связанные trigger/result-файлы. Обычный production path от probe не зависит.

## Mini App и State API

Mini App и State API находятся в состоянии frozen archive. Связанные deployment/migration workflows отключены и оставлены только как архивные контракты. Telegram-бот от них не зависит.

## Резервное копирование

Критические компоненты: `.github/workflows/bot-state-backup.yml` и `backup_rotation.py`.

Ordinary `backup/*` ограничены тремя. Перед удалением старых backup проверяются ancestry и отсутствие unique commits; при ошибке проверок удаление не выполняется.

## Runtime state

Ownership отслеживаемых JSON описан в `monitor_data.JSON_STATE_CONTRACTS`.

State разделён на authoritative, diagnostic, config, cache, compatibility и archive. Высокочастотные runtime commits в `main` являются отдельным архитектурным вопросом; state нельзя удалять без проекта миграции и восстановления.

## Документация

- [`AGENTS.md`](AGENTS.md) — обязательные правила проекта;
- [`docs/PROJECT_CHANGELOG_RU.md`](docs/PROJECT_CHANGELOG_RU.md) — история изменений;
- [`docs/REFACTOR_PLAN_RU.md`](docs/REFACTOR_PLAN_RU.md) — план глобальной очистки;
- [`docs/CODE_INVENTORY_RU.md`](docs/CODE_INVENTORY_RU.md) — инвентарь структуры;
- [`docs/RUNTIME_METHOD_INVENTORY_RU.md`](docs/RUNTIME_METHOD_INVENTORY_RU.md) — runtime map;
- [`docs/CHAT_CONTEXT_RU.md`](docs/CHAT_CONTEXT_RU.md) — контекст для нового чата.

## Глобальная ревизия 20.07.2026

Этап 1 — полная инвентаризация — завершён в рабочей ветке `cleanup/global-repository-audit-2026-07-20`.

Исходная rollback-точка: `backup/before-global-repository-cleanup-2026-07-20`, созданная от SHA `1da3115319305fa5e237cd90124186c12ab98753`.

Следующий шаг по решению пользователя — сформировать новый самодостаточный PDF по текущему проекту и результатам этапа 1. Дальнейший крупный рефакторинг продолжится после PDF.
