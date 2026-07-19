from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "intelligence_state.json"
PUBLIC_PATH = ROOT / "public_sources.txt"

# Do not auto-promote channels whose own username is explicitly branded by a
# competing bookmaker. A candidate is otherwise eligible only after the
# intelligence scanner has found a real BetBoom wheel link in that channel.
COMPETING_BOOKMAKER_RE = re.compile(
    r"(?:fonbet|betcity|pari|ligastavok|liga_stavok|winline|leon|melbet|"
    r"xbet|1xbet|olimp|marathonbet|marathon)",
    re.IGNORECASE,
)


def _clean(value: Any) -> str:
    return str(value or "").strip().lstrip("@")


def load_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def read_sources() -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    try:
        lines = PUBLIC_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        source = _clean(line)
        if not source or source.startswith("#"):
            continue
        key = source.casefold()
        if key not in seen:
            seen.add(key)
            result.append(source)
    return result


def eligible_candidates(state: dict[str, Any], known: set[str]) -> list[str]:
    candidates = state.get("candidates")
    candidates = candidates if isinstance(candidates, dict) else {}
    result: list[str] = []
    for key, raw in candidates.items():
        if not isinstance(raw, dict):
            continue
        source = _clean(raw.get("source") or key)
        folded = source.casefold()
        if not source or folded in known or source.casefold().endswith("bot"):
            continue
        if COMPETING_BOOKMAKER_RE.search(source):
            continue
        if not bool(raw.get("public")):
            continue
        if int(raw.get("wheel_links_found", 0) or 0) <= 0:
            continue
        samples = raw.get("sample_wheels")
        samples = samples if isinstance(samples, list) else []
        has_betboom_wheel = any(
            isinstance(item, dict)
            and "betboom.ru/freestream/" in str(item.get("url") or "").casefold()
            for item in samples
        )
        if not has_betboom_wheel:
            continue
        result.append(source)
    return sorted(set(result), key=str.casefold)


def promote() -> list[str]:
    state = load_state()
    current = read_sources()
    known = {source.casefold() for source in current}
    additions = eligible_candidates(state, known)
    if not additions:
        return []

    text = PUBLIC_PATH.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n".join(additions) + "\n"
    PUBLIC_PATH.write_text(text, encoding="utf-8")
    return additions


def self_test() -> None:
    state = {
        "candidates": {
            "good": {
                "source": "GoodChannel",
                "public": True,
                "wheel_links_found": 1,
                "sample_wheels": [
                    {"url": "https://betboom.ru/freestream/GOOD"}
                ],
            },
            "competitor": {
                "source": "FonbetEsports",
                "public": True,
                "wheel_links_found": 1,
                "sample_wheels": [
                    {"url": "https://betboom.ru/freestream/MIXED"}
                ],
            },
            "generic": {
                "source": "GenericBetChannel",
                "public": True,
                "wheel_links_found": 0,
                "sample_wheels": [],
            },
        }
    }
    assert eligible_candidates(state, set()) == ["GoodChannel"]
    print("BetBoom candidate promotion self-test passed")


def main() -> int:
    additions = promote()
    print(
        "Promoted BetBoom candidates: "
        + (", ".join("@" + source for source in additions) if additions else "none")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
