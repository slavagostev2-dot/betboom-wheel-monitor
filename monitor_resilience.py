"""Compatibility shim for the retired dual-domain Telegram transport.

All production traffic now goes through :mod:`telegram_transport`, whose sole
outbound web domain is ``telegram.me``.  Keeping this module prevents old
imports from breaking without ever probing the blocked legacy domain.
"""

from __future__ import annotations

from typing import Any

import telegram_transport

WEB_DOMAINS = (telegram_transport.PRIMARY_DOMAIN,)
PRIMARY_DOMAIN = telegram_transport.PRIMARY_DOMAIN

is_transient_transport_error = telegram_transport.is_transient_transport_error
public_source_url = telegram_transport.public_source_url
public_message_url = telegram_transport.public_message_url
profile_url = telegram_transport.profile_url
rewrite_telegram_url = telegram_transport.rewrite_telegram_url
rewrite_telegram_text = telegram_transport.rewrite_telegram_text


def alternate_telegram_url(value: str) -> str:
    """Normalize a historical Telegram URL to the only supported domain."""

    return telegram_transport.rewrite_telegram_url(value)


def install(monitor_module: Any) -> None:
    telegram_transport.install(monitor_module)


def self_test() -> None:
    assert WEB_DOMAINS == (PRIMARY_DOMAIN,)
    assert public_source_url("test") == f"https://{PRIMARY_DOMAIN}/s/test"
    assert alternate_telegram_url("https://t.me/s/test") == f"https://{PRIMARY_DOMAIN}/s/test"
    print("monitor_resilience compatibility self-test passed")


if __name__ == "__main__":
    self_test()
