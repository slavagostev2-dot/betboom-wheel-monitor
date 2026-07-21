from __future__ import annotations

import json
from typing import Any

import bbvg_monitor_runtime as runtime
import betboom_auto_participation


def _defer_failure_notification(monitor: Any, entry: dict[str, Any], result: Any) -> tuple[bool, str]:
    """The independent recovery step must get the final chance before alarming the user."""

    return False, "deferred_to_recovery"


def main() -> int:
    monitor = runtime.monitor
    state = runtime.load_state_without_pending()

    # The event worker is only the first browser path. A failure here is not final:
    # auto_participation_recovery.py runs immediately afterwards with an independent
    # scanner/browser. Do not send a false manual-action alert before that recovery
    # path has had its chance (the hooch07 incident exposed this race).
    original_notify = betboom_auto_participation._notify_manual_participation
    betboom_auto_participation._notify_manual_participation = _defer_failure_notification
    try:
        result = betboom_auto_participation.process_new_wheel_events(state, monitor)
    finally:
        betboom_auto_participation._notify_manual_participation = original_notify

    result["debug_active_wheels"] = len(state.get("active_wheels", {}))
    result["debug_events"] = len(state.get("auto_participation_events", {}))
    result["debug_configured"] = betboom_auto_participation.configured()
    result["failure_alert_policy"] = "deferred_to_recovery"
    if bool(result.get("changed")):
        monitor.save_state(state)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
