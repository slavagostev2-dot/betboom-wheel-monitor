from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TARGET_URL = os.getenv("BETBOOM_PROBE_URL", "https://betboom.ru/freestream/zonertg11").strip()
RESULT_PATH = Path("auto_participation_probe_result.json")
BUTTON_RE = re.compile(r"^\s*(?:участвую|участвовать|принять\s+участие)\s*$", re.IGNORECASE)
SUCCESS_RE = re.compile(
    r"(?:участие\s+(?:принято|подтверждено|зарегистрировано)|"
    r"вы\s+(?:уже\s+)?участвуете|уже\s+участвуете|участие\s+отмечено)",
    re.IGNORECASE,
)


def _storage_state() -> dict[str, Any] | None:
    raw = os.getenv("BETBOOM_STORAGE_STATE_JSON", "").strip()
    if not raw:
        raw = os.getenv("BETBOOM_STORAGE_STATE_JSON_PART1", "") + os.getenv(
            "BETBOOM_STORAGE_STATE_JSON_PART2", ""
        )
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _text(locator: Any, timeout: int = 3000) -> str:
    try:
        return str(locator.inner_text(timeout=timeout) or "").strip()
    except Exception:
        return ""


def main() -> int:
    result: dict[str, Any] = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "target_url": TARGET_URL,
        "status": "started",
        "steps": [],
    }
    storage_state = _storage_state()
    if storage_state is None:
        result["status"] = "session_not_configured"
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        result["status"] = "playwright_missing"
        result["error"] = str(exc)
        RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel=os.getenv("BETBOOM_BROWSER_CHANNEL", "chrome"))
            context = browser.new_context(storage_state=storage_state, viewport={"width": 1440, "height": 1200})
            page = context.new_page()
            page.set_default_timeout(15000)
            response = page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
            result["http_status"] = response.status if response else None
            result["final_url"] = page.url
            result["title"] = page.title()
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            time.sleep(2)

            body_before = _text(page.locator("body"), 5000)
            result["body_before_excerpt"] = body_before[:5000]
            result["already_success"] = bool(SUCCESS_RE.search(body_before))

            buttons: list[dict[str, Any]] = []
            for i in range(min(page.locator("button").count(), 100)):
                locator = page.locator("button").nth(i)
                try:
                    buttons.append({
                        "index": i,
                        "text": _text(locator),
                        "visible": locator.is_visible(),
                        "enabled": locator.is_enabled(),
                        "html": locator.evaluate("el => el.outerHTML.slice(0, 1200)"),
                    })
                except Exception as exc:
                    buttons.append({"index": i, "error": f"{type(exc).__name__}: {exc}"[:300]})
            result["buttons"] = buttons

            frames: list[dict[str, Any]] = []
            for idx, frame in enumerate(page.frames):
                frame_info: dict[str, Any] = {"index": idx, "url": frame.url, "name": frame.name}
                try:
                    frame_info["body_excerpt"] = _text(frame.locator("body"))[:2000]
                    frame_buttons = []
                    for j in range(min(frame.locator("button").count(), 50)):
                        loc = frame.locator("button").nth(j)
                        frame_buttons.append({"index": j, "text": _text(loc), "visible": loc.is_visible()})
                    frame_info["buttons"] = frame_buttons
                except Exception as exc:
                    frame_info["error"] = f"{type(exc).__name__}: {exc}"[:300]
                frames.append(frame_info)
            result["frames"] = frames

            strategies = []
            clicked = False
            clicked_strategy = ""

            candidates = [
                ("role_button", lambda: page.get_by_role("button", name=BUTTON_RE)),
                ("button_filter_text", lambda: page.locator("button").filter(has_text=BUTTON_RE)),
                ("text_exact", lambda: page.get_by_text("Принять участие", exact=True)),
                ("css_has_text", lambda: page.locator("button:has-text('Принять участие')")),
            ]

            for name, factory in candidates:
                try:
                    loc = factory()
                    count = loc.count()
                    visible_count = sum(1 for i in range(count) if loc.nth(i).is_visible())
                    strategies.append({"name": name, "count": count, "visible_count": visible_count})
                    for i in range(count):
                        item = loc.nth(i)
                        if item.is_visible() and item.is_enabled():
                            item.scroll_into_view_if_needed()
                            item.click(timeout=10000)
                            clicked = True
                            clicked_strategy = name
                            break
                    if clicked:
                        break
                except Exception as exc:
                    strategies.append({"name": name, "error": f"{type(exc).__name__}: {exc}"[:500]})

            if not clicked:
                for frame_index, frame in enumerate(page.frames):
                    try:
                        loc = frame.get_by_role("button", name=BUTTON_RE)
                        count = loc.count()
                        strategies.append({"name": f"frame_role_{frame_index}", "count": count})
                        for i in range(count):
                            item = loc.nth(i)
                            if item.is_visible() and item.is_enabled():
                                item.scroll_into_view_if_needed()
                                item.click(timeout=10000)
                                clicked = True
                                clicked_strategy = f"frame_role_{frame_index}"
                                break
                        if clicked:
                            break
                    except Exception as exc:
                        strategies.append({"name": f"frame_role_{frame_index}", "error": f"{type(exc).__name__}: {exc}"[:500]})

            result["strategies"] = strategies
            result["clicked"] = clicked
            result["clicked_strategy"] = clicked_strategy

            if clicked:
                time.sleep(3)
            body_after = _text(page.locator("body"), 5000)
            result["body_after_excerpt"] = body_after[:5000]
            result["success_detected"] = bool(SUCCESS_RE.search(body_after))
            result["final_url_after_click"] = page.url
            result["status"] = (
                "participated_or_already" if result["success_detected"] or result["already_success"]
                else "clicked_unconfirmed" if clicked
                else "button_not_found"
            )
            browser.close()
    except Exception as exc:
        result["status"] = "probe_error"
        result["error"] = f"{type(exc).__name__}: {exc}"[:1000]

    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"participated_or_already", "clicked_unconfirmed", "button_not_found"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
