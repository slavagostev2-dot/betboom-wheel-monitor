from __future__ import annotations

import bbvg_monitor_runtime as runtime


monitor = runtime.monitor
_original_recover_deadline = runtime.base_runtime._recover_deadline
_original_markup = monitor.wheel_reply_markup


def recover_deadline_manual_first(state: dict, key: str, entry: dict):
    normalized = str(key or "").casefold()
    manual = state.get("manual_deadlines", {}).get(normalized)
    if isinstance(manual, dict):
        deadline = monitor.parse_datetime(manual.get("deadline"))
        if deadline:
            return deadline
    if str(entry.get("deadline_source") or "") == "manual":
        deadline = monitor.parse_datetime(entry.get("deadline"))
        if deadline:
            return deadline
    return _original_recover_deadline(state, normalized, entry)


def wheel_markup_with_direct_key(state, message, link, **kwargs):
    markup = _original_markup(state, message, link, **kwargs)
    key = monitor.wheel_key(link)
    for row in markup.get("inline_keyboard", []):
        for button in row:
            callback = str(button.get("callback_data") or "")
            if callback.startswith("bb:x:"):
                button["callback_data"] = f"bb:x:{key}"
            elif callback.startswith("bb:t:"):
                button["callback_data"] = f"bb:t:{key}"
    return markup


runtime.base_runtime._recover_deadline = recover_deadline_manual_first
monitor.wheel_reply_markup = wheel_markup_with_direct_key


if __name__ == "__main__":
    raise SystemExit(monitor.main())
