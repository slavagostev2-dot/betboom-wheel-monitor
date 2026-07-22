from __future__ import annotations

import re
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one marker, found {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


# Preserve the static contract used by the user-card renderer.
path = "auto_participation_notifications.py"
text = read(path)
pattern = re.compile(
    r'''    if callable\(original_options\):\n'''
    r'''        def notification_options_for_role\(self: Any, role: str\) -> tuple:\n'''
    r'''            values = list\(original_options\(role\)\)\n'''
    r'''(?P<body>.*?)'''
    r'''        panel_class\._notification_options_for_role = notification_options_for_role\n''',
    flags=re.S,
)
match = pattern.search(text)
if match is None:
    raise SystemExit("auto_participation_notifications.py: notification wrapper marker not found")
body = match.group("body")
replacement = (
    "    if callable(original_options):\n"
    "        def notification_options_for_role(role: str) -> tuple:\n"
    "            values = list(original_options(role))\n"
    + body
    + "        panel_class._notification_options_for_role = staticmethod(\n"
    "            notification_options_for_role\n"
    "        )\n"
)
write(path, text[: match.start()] + replacement + text[match.end() :])

# Ensure changes to the additional-account module restart the Control Center.
replace_once(
    ".github/workflows/admin-bot.yml",
    '      - "auto_participation_notifications.py"\n',
    '      - "auto_participation_notifications.py"\n'
    '      - "betboom_account_participation.py"\n',
)

# Replace the obsolete UI-screen expectation with the new redirect contract.
path = "tests/test_button_matrix.py"
text = read(path)
start = text.find(
    "    def test_settings_secondary_pages_open_their_real_screens(self) -> None:\n"
)
end = text.find(
    "    def test_active_list_button_from_notifications_is_routable(self) -> None:\n",
    start,
)
if start < 0 or end < 0:
    raise SystemExit("tests/test_button_matrix.py: obsolete settings test boundaries not found")
replacement = '''    def test_removed_settings_callbacks_return_to_settings(self) -> None:
        panel, calls = self.panel(admin=True)
        panel.load_access = lambda force=False: {  # type: ignore[method-assign]
            "settings": {"monitor_interval_minutes": 5}
        }
        for callback in ("page:wheelmode", "page:disabled_features"):
            panel.handle_callback(self.query(callback))
            sent = [row for row in calls if row[0] == "send"][-1]
            self.assertIn("⚙️ <b>Настройки</b>", sent[1])
            self.assertNotIn("API — активный production-режим", sent[1])
            self.assertNotIn("Ручное указание времени", sent[1])

'''
write(path, text[:start] + replacement + text[end:])

# Direct regression check for the TypeError that occurred in user details.
path = "notification_button_recovery.py"
text = read(path)
marker = '    options = panel._notification_options_for_role("owner")\n'
if marker not in text:
    raise SystemExit("notification_button_recovery.py: notification options regression marker missing")

print("xFLARXx cleanup finalization applied")
