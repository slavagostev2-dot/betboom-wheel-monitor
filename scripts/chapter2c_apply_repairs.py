from __future__ import annotations

from pathlib import Path


changed: list[str] = []


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected one exact anchor in {path}, found {count}: {old!r}"
        )
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    changed.append(path)


replace_once(
    "monitor_data.py",
    '''    "admin_panel_status.json": {
        "category": "diagnostic",
        "owner": "control-center-status",
        "schema": ("heartbeat_version", (1,)),
    },
    "bot_access.json": {''',
    '''    "admin_panel_status.json": {
        "category": "diagnostic",
        "owner": "control-center-status",
        "schema": ("heartbeat_version", (1,)),
    },
    "ai_runtime_state.json": {
        "category": "diagnostic",
        "owner": "ai-health-inspector",
        "schema": ("version", (1,)),
    },
    "bot_access.json": {''',
)

replace_once(
    "bbvg/bot/natural_language_admin.py",
    '''        ("удал", "бэкап", "delete_backups"),
        ("удал", "backup", "delete_backups"),''',
    '''        ("удал", "бэкап", "backup", "delete_backups"),
        ("удал", "backup", "backup", "delete_backups"),''',
)

replace_once(
    "tests/test_concurrency_and_ci.py",
    "self.assertEqual(len(monitor_data.JSON_STATE_CONTRACTS), 28)",
    "self.assertEqual(len(monitor_data.JSON_STATE_CONTRACTS), 29)",
)
replace_once(
    "tests/test_concurrency_and_ci.py",
    '''        self.assertIn("files=(bot_private_state.enc.json)", panel)
        self.assertNotIn("notification_integrity_v2.py --prune", panel)''',
    '''        self.assertIn("git diff --quiet -- bot_private_state.enc.json", panel)
        self.assertIn("git add bot_private_state.enc.json", panel)
        self.assertNotIn("notification_integrity_v2.py --prune", panel)''',
)

replace_once(
    "tests/test_nightly_idle_policy.py",
    '''    def test_catalog_change_does_not_trigger_nightly_workflow(self) -> None:
        workflow = (ROOT / ".github/workflows/nightly-discovery.yml").read_text(
            encoding="utf-8"
        )
        push_paths = workflow.split("workflow_dispatch:", 1)[0]
        self.assertNotIn('"source_catalog.txt"', push_paths)
        self.assertNotIn('"public_sources.txt"', push_paths)''',
    '''    def test_catalog_change_triggers_nightly_inventory_synchronization(self) -> None:
        workflow = (ROOT / ".github/workflows/nightly-discovery.yml").read_text(
            encoding="utf-8"
        )
        push_paths = workflow.split("workflow_dispatch:", 1)[0]
        self.assertIn('"source_catalog.txt"', push_paths)
        self.assertIn('"public_sources.txt"', push_paths)''',
)

replace_once(
    "tests/test_ui_chapter4.py",
    '''            {"page:active", "page:analytics", "page:sources", "page:settings", "page:status"},''',
    '''            {"page:active", "page:analytics", "page:sources", "page:settings", "page:status", "page:profile"},''',
)

replace_once("AGENTS.md", "всех 28 JSON", "всех 29 JSON")
replace_once(
    "AGENTS.md",
    '''| `admin_panel_status.json` | diagnostic | control-center workflow |
| `bot_access.json` | compatibility | encrypted private state |''',
    '''| `admin_panel_status.json` | diagnostic | control-center workflow |
| `ai_runtime_state.json` | diagnostic | AI health inspector / system health |
| `bot_access.json` | compatibility | encrypted private state |''',
)

changelog = Path("docs/PROJECT_CHANGELOG_RU.md")
changelog_text = changelog.read_text(encoding="utf-8")
heading = (
    "## 2026-07-21 — Глава 2C: удалена историческая цепочка "
    "Telegram-панели v25–v40"
)
if heading not in changelog_text:
    anchor = "---\n\n"
    if changelog_text.count(anchor) != 1:
        raise SystemExit("Unexpected changelog header structure")
    entry = '''## 2026-07-21 — Глава 2C: удалена историческая цепочка Telegram-панели v25–v40

После переноса production-поведения в `bbvg/bot/*` файлы
`admin_panel_runtime_v25.py`–`admin_panel_runtime_v40.py` образовывали замкнутую
историческую лестницу. Production MRO их не использовал; внешние ссылки
оставались только в устаревших preflight, CI и recovery-контрактах.

Удалены 16 versioned-файлов и 5 394 строки. `preflight.py`, Control Center
validation, current checks, recovery smoke, private-state validation и System
Health переведены на `bbvg/bot/*`, `admin_panel_v2.py` и совместимую production-
команду `admin_panel_runtime_v41.py`. Добавлен отрицательный regression-контракт,
запрещающий возврат v25–v40. Callback-данные, порядок кнопок, JSON-state и
логика колёс не изменялись.

Одновременно восстановлен зелёный baseline: `ai_runtime_state.json` внесён в
машинный ownership-inventory как 29-й JSON; исправлена четырёхполевая таблица
критических natural-language команд; тесты синхронизированы с текущим запуском
nightly discovery, профилем пользователя и CAS-сохранением encrypted state.

Pre-update backup:
`backup/before-chapter-2c-legacy-panel-removal-2026-07-21` →
`ebd84b148a8b0aa6457106d729d86925a3a77393`.
Safety-точка после физического удаления:
`safety/chapter-2c-deletion-head-2026-07-21` →
`ef2a7661b7c70b8c26951079223f4a7c990a7651`.

Откат: вернуть merge главы целиком либо восстановить pre-update backup; не
восстанавливать отдельные versioned-файлы вручную поверх нового runtime.

'''
    changelog.write_text(
        changelog_text.replace(anchor, anchor + entry, 1), encoding="utf-8"
    )
    changed.append(str(changelog))

print("Changed files:", ", ".join(changed) if changed else "none")
