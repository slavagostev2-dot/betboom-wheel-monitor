from pathlib import Path

path = Path("tests/test_button_matrix.py")
text = path.read_text(encoding="utf-8")
start = text.find(
    "    def test_settings_secondary_pages_open_their_real_screens(self) -> None:\n"
)
end = text.find(
    "    def test_active_list_button_from_notifications_is_routable(self) -> None:\n",
    start,
)
if start < 0 or end < 0:
    raise SystemExit("settings secondary page test boundaries not found")
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
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
