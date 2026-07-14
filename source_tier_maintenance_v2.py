from __future__ import annotations

import argparse

import bot_notification_state
import source_tier_maintenance as legacy

legacy.notification_recipients = bot_notification_state.admin_recipients


def self_test() -> None:
    recipients = legacy.notification_recipients()
    assert isinstance(recipients, list)
    print("BB V.G. source tier bot-only notification self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    return legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
