# BB V.G. — инвентаризация кода перед рефакторингом

Дата снимка: 2026-07-16
Ветка: `refactor/consolidate-runtime-v42`
Точка отката: `backup/v41-before-cleanup-2026-07-16`

## 1. Главные процессы

В рабочей системе два долгоживущих процесса:

- Telegram-панель: `.github/workflows/admin-bot.yml` → `admin_panel_runtime_v41.py`;
- монитор колёс: `.github/workflows/monitor.yml` и восстановительная смена → `bbvg_monitor_main.py`.

Нельзя создавать второй consumer Telegram `getUpdates` или параллельный монитор с другим состоянием.

## 2. Runtime панели

Обнаружено 40 файлов `admin_panel_runtime_v*.py`.

- 38 файлов входят в импортную цепочку текущей v41;
- `admin_panel_runtime_v23.py` и `admin_panel_runtime_v24.py` не входят в текущую цепочку;
- v41 наследует v40, v40 наследует v39, далее цепочка охватывает почти всю историю проекта;
- несколько старых классов импортируются напрямую тестами, `preflight.py` и `system_checks.py`.

Следствие: удаление старых runtime-файлов возможно только после создания одного цельного runtime и перевода всех тестов, workflow и проверок на новые предметные модули.

## 3. Acceptance-проверки

Корневые файлы:

- `chapter1_stability.py`;
- `chapter2_unified_logic.py`;
- `chapter3_acceptance.py`;
- `chapter4_acceptance.py`;
- `chapter5_acceptance.py`.

Все пять являются производственными проверками, а не runtime. Они объединяются в `tests/production_acceptance.py` с секциями:

- `stability`;
- `unified`;
- `ci`;
- `interface`;
- `lifecycle`.

Старые файлы удаляются только после замены всех ссылок в workflow, `preflight.py` и валидаторах.

## 4. Кандидаты на удаление

Автоматический аудит отметил как не имеющие внешних текстовых ссылок:

- `admin_panel_runtime_v24.py`;
- `monitor_resilience.py`;
- `normalize_source_ratings.py`.

Это только кандидаты, а не разрешение на удаление. Перед удалением проверяются динамические импорты, команды эксплуатации, история workflow, тесты и полный runtime-прогон.

## 5. Целевая структура

```text
bbvg/
  bot/
    runtime.py
    menus.py
    callbacks.py
    users.py
    reports.py
  monitor/
    runtime.py
    sources.py
    telegram_parser.py
    notifications.py
  domain/
    wheels.py
    lifecycle.py
    deduplication.py
    rating.py
  storage/
    state.py
    private_state.py
    migrations.py
  operations/
    health.py
    incidents.py
    commands.py

tests/
  unit/
  integration/
  scenarios/
  production_acceptance.py

docs/
.github/workflows/
```

Названия являются целевыми и могут уточняться после анализа ответственности существующих классов. Нельзя механически разложить файлы по папкам, сохранив прежнюю спутанную зависимость.

## 6. Порядок переноса

1. Объединить acceptance-проверки.
2. Зафиксировать публичные контракты панели тестами.
3. Составить список методов каждого runtime-слоя и определить владельца ответственности.
4. Собрать цельный runtime панели без номеров версий.
5. Перевести workflow и тесты на новый runtime.
6. Удалить старую runtime-цепочку небольшими группами с прогоном после каждой группы.
7. Перенести монитор, доменные правила, storage и operations в пакеты.
8. Удалить временные workflow и аудит-файлы.
9. Обновить `AGENTS.md`, журнал и карту кода.
10. Только после полного production-прогона переключить `main`.

## 7. Критерии завершения

- нет файлов production-кода с суффиксами версий;
- одна точка входа панели и одна точка входа монитора;
- workflow не содержит бизнес-логики;
- все значимые зависимости отражены в документации;
- полные тесты проходят;
- панель и монитор оставляют свежий heartbeat;
- проверяются все настроенные источники;
- откат к резервной ветке подтверждён и документирован.
