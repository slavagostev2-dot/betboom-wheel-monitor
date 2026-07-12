from __future__ import annotations

import os
import sys

import requests


def main() -> int:
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("GitHub secret BOT_TOKEN is missing.", file=sys.stderr)
        return 2

    response = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        print(data, file=sys.stderr)
        return 1

    found: dict[int, str] = {}
    for update in data.get("result", []):
        message = update.get("message") or update.get("channel_post")
        if not message:
            continue

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            continue

        name = (
            chat.get("title")
            or " ".join(
                part
                for part in (chat.get("first_name"), chat.get("last_name"))
                if part
            )
            or chat.get("username")
            or "unknown"
        )
        found[int(chat_id)] = (
            f"BOT_CHAT_ID={chat_id} | "
            f"type={chat.get('type')} | name={name}"
        )

    if not found:
        print(
            "No messages found. Open your bot in Telegram, press Start, "
            "send any message, and run this workflow again."
        )
        return 0

    for chat_id in sorted(found):
        print(found[chat_id])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
