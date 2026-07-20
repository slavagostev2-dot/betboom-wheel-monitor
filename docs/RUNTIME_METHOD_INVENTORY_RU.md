# Инвентарь runtime и точек входа BB V.G.

> Статус: этапы 1, 2A и 2B завершены; production Control Center перенесён в стабильный модуль.
> Снимок `main`: `e91f7608b4377bd8bbdf539d75c266c1278084db`.

Документ отвечает на вопрос: **что реально запускается сейчас, через какую цепочку и какие исторические слои всё ещё удерживаются CI/compatibility-контрактами**.

## 1. Telegram Control Center

### Production

`.github/workflows/admin-bot.yml`
→ `python admin_panel_runtime_v41.py` (тонкий compatibility entrypoint)
→ `bbvg.bot.control_center.TelegramPanelRuntimeV41`
→ `bbvg.bot.runtime.TelegramPanelRuntime`
→ stable mixin/runtime слои `bbvg/bot/*`.

`bbvg.bot.runtime.TelegramPanelRuntime` не имеет `admin_panel_runtime_v*` в MRO.

### Результат этапа 2B

Уникальный production-слой бывшего `v41` перенесён без изменения поведения в устойчивый модуль `bbvg/bot/control_center.py`. Корневой `admin_panel_runtime_v41.py` оставлен только как тонкий compatibility entrypoint для неизменной production-команды workflow.

Regression-тест `tests/test_control_center_stable.py` фиксирует, что wrapper не владеет `show_*`/`handle_callback`, а также точный порядок callback-строк пользовательского и административного меню.

## 2. Legacy panel runtime maps

### Mini App-era

Подтверждённая текущая цепочка:

`v16 ← v17 ← v18 ← v19 ← v20 ← v21 ← v22 ← v23 ← v24`.

Она содержит старые Mini App URL/fallback и интерфейсные решения. `v25` от `v24` не наследуется.

### Bot-only compatibility

Подтверждённая chain:

`PrivateStateRuntime → v25 → v26 → v28 → v29 → v30 → v31 → v32 → v36 → v37 → v38`.

Текущий stable runtime вынесен из этой MRO-chain. В этапе 2B `v22-checks.yml`, `bot-recovery-smoke.yml`, `validate-private-state.yml` и `scripts/validate_control_center.sh` переведены на стабильный Control Center и больше не компилируют всю старую лестницу. До физического удаления файлов в этапе 2C необходимо снять оставшиеся статические ссылки System Health/preflight и повторно проверить внутренние импорты versioned-файлов.

## 3. Wheel monitor

`.github/workflows/monitor.yml`
→ repository preflight/self-tests
→ long-running shell loop
→ каждая итерация `python bbvg_monitor_main.py`.

Runtime composition включает:

`monitor.py`
+ `bbvg_monitor_runtime.py`
+ `telegram_transport.py`
+ `telegram_post_links_v2.py`
+ `recurring_wheel_events.py`
+ `wheel_event_runtime.py`
+ `wheel_metadata_quality.py`
+ `wheel_publications_v2.py`
+ `wheel_lifecycle_v2.py`
+ `personal_reminder_filter.py`
+ notification/rating modules.

Workflow прямо проверяет `__module__` установленных функций. Порядок install/patch является текущим runtime-контрактом.

## 4. System Health

`.github/workflows/system-health.yml`
→ `python system_checks_v3.py --self-test`
→ `python system_checks_v3.py`.

Chain:

`system_checks_v3.py`
→ `import system_checks_v2 as current`
→ `system_checks_v2.py`
→ `import system_checks as legacy`.

`v2` и `v3` присваивают новые функции в namespace нижнего слоя.

Целевое состояние: один стабильный модуль health checks с явными функциями без import-order monkey-patch.

## 5. Source runtime

Source change из Control Center:

`admin_runtime.RuntimeAdminBot.set_source_mode()`
→ save source change
→ `refresh_source_runtime()`
→ dispatch:

1. `monitor.yml` с replace/continuous;
2. `activate-66-sources.yml`;
3. `source-registry.yml`.

Поэтому `activate-66-sources.yml` нельзя переименовать без синхронного изменения `admin_runtime` и тестов.

Nightly discovery после успешного изменения tiers должен обновлять transport/registry согласно действующему source contract.

## 6. Source-tier audit

`.github/workflows/source-tier-maintenance.yml`
→ compile `source_tier_maintenance.py` и `source_tier_maintenance_v2.py`
→ self-test `v2`
→ production audit `python source_tier_maintenance_v2.py`
→ commit только `source_tier_state.json`.

Это audit, а не автоматический demotion writer production source lists.

## 7. Telegram transport validation

`.github/workflows/telegram-resilience-check.yml`
→ `telegram_transport.py`
→ `telegram_post_links_v2.py`
→ recurring/event/metadata modules
→ live public preview smoke.

Versioned `telegram_post_links_v2.py` сейчас production/validation dependency.

## 8. Auto-participation

`.github/workflows/auto-participation.yml` normal path:

`betboom_auto_participation.py` preflight/core
→ `auto_participation_worker.py`
→ update `state.json`.

Dispatch state обслуживается `auto_participation_dispatch.py`.

### Broken optional path

При `probe=true` workflow вызывает `auto_participation_probe.py`, но файл отсутствует. Trigger/result paths также отсутствуют. Этот optional runtime path не является рабочим.

## 9. VK

Отдельные business entrypoints:

- wheel notification workflow → `vk_wheel_notifications.py`;
- welcome workflow → `vk_start_welcome.py`;
- subscriber resolution → `vk_dynamic_subscribers.py`.

Будущий refactor может выделить общий transport/client, но не должен смешивать бизнес-сценарии.

## 10. Backup

`.github/workflows/bot-state-backup.yml`
→ verify encrypted state
→ artifact backup
→ `backup_rotation.py` для ordinary `backup/*` refs.

Rotation:

1. получить inventory;
2. выбрать newly created/latest backup;
3. проверить каждый ref;
4. подтвердить ancestry/no unique commits;
5. retained = 3;
6. удалить obsolete только после всех проверок;
7. повторно проверить inventory.

## 11. Monitor watchdog

`.github/workflows/monitor-watchdog.yml`
→ `monitor_health.py check`
→ при stale состоянии проверить, нет ли уже queued monitor run
→ dispatch `monitor.yml` без destructive cancellation.

Workflow является operational recovery и не дублирует основной монитор.

## 12. Admin action

Control Center/stable runtime
→ `admin_action_queue.enqueue_remote()`
→ `admin_action_queue.json` CAS
→ основной monitor применяет action.

`.github/workflows/admin-action.yml` предоставляет ручной workflow-dispatch для постановки действия в ту же очередь.

Старые `admin_action_v2.py` / `admin_action_v3.py` всё ещё участвуют recovery/validation и требуют отдельной консолидации.

## 13. Summaries

Текущий Telegram runtime умеет формировать сводку in-process.

Отдельно существует `.github/workflows/daily-report.yml`, но он запускается только вручную и вызывает `daily_report_entry.py`.

Статус: compatibility/review. Перед удалением проверить, используется ли ручной workflow как отдельный operator fallback.

## 14. Mini App / State API archive

- `cloudflare-pages.yml` — archived/disabled;
- `state-api.yml` — archived/disabled;
- `migrate-private-state.yml` — archived/disabled;
- `monitor-66-live.yml` — archived legacy monitor с `if: false`;
- `miniapp-archive-guard.yml` — защита архива.

Telegram bot runtime от State API/Mini App workflows не зависит.

### Исправление этапа 1

Archive guard раньше срабатывал на любой `docs/**`, поэтому блокировал новые технические Markdown-документы. В ветке аудита Markdown исключён из guard; static files и State API остаются frozen.

## 15. Preflight

`preflight.py` запускается production/validation workflows и потому является блокирующим dependency owner.

Подтверждённый stale contract: preflight требует frozen Mini App static assets, хотя deployment/state API архивированы. Следующий cleanup должен вынести archive verification из production preflight.

## 16. Validation map

### `validate-current.yml`

- exact event SHA;
- compile active Python;
- `preflight.py`;
- chapter acceptance;
- full pytest + coverage gate.

### `v22-checks.yml`

Историческое имя. Сейчас выполняет consolidated runtime/state validation и компилирует старые panel runtime `v25–v38`.

### `bot-recovery-smoke.yml`

Recovery validation stable runtime + old compatibility files + monitor patches.

### `validate-private-state.yml`

Encrypted state, privacy, roles, delivery invariants и archive markers.

### `telegram-resilience-check.yml`

Transport/runtime composition и live Telegram preview.

## 17. Runtime-state writers

- monitor → `state.json`, `source_health.json`, `source_stats.json`, `unknown_timer_samples.json`, `monitor_status.json`, notification ledger;
- control center → encrypted state / panel status / moderation/queue по соответствующим CAS-контрактам;
- system health → incident/system/AI diagnostic state;
- nightly discovery → discovery state и разрешённые tier changes;
- source intelligence → intelligence state;
- source registry → cache;
- source transport → transport diagnostic;
- source-tier maintenance → audit diagnostic;
- auto participation → participation state/dispatch state.

Высокочастотные state commits объясняют шумную историю `main`; перенос требует отдельной persistence architecture.

## 18. Приоритет после PDF

После фиксации PDF пользователь отдельно выберет продолжение cleanup. Технически рекомендуемый порядок:

1. Control Center `v41` → stable modules.
2. System Health chain consolidation.
3. Legacy panel runtime removal.
4. Broken auto-participation probe cleanup.
5. Mini App archive removal from production preflight.
6. Workflow renames.
7. Остальные versioned module consolidations.
8. Runtime-state storage architecture.
