from __future__ import annotations

import daily_report
import monitor
import notification_router

notification_router.install(monitor)

if __name__ == "__main__":
    raise SystemExit(daily_report.main())
