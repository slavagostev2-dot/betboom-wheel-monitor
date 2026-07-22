from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Повторная публикация уже прошедшего полный набор тестов кода.


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, found {count}")
    return text.replace(old, new, 1)


def replace_first(text: str, old: str, new: str, label: str) -> str:
    position = text.find(old)
    if position < 0:
        raise RuntimeError(f"{label}: marker not found")
    return text[:position] + new + text[position + len(old):]


def prepare_workflow() -> None:
    path = Path(".github/workflows/auto-participation.yml")
    text = path.read_text(encoding="utf-8")

    text = replace_first(
        text,
        """          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}
          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}
          BETBOOM_ACCOUNT2_LABEL: \"Аккаунт 2\"
""",
        """          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}
          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}
          BETBOOM_STORAGE_STATE_JSON_PART5: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART5 }}
          BETBOOM_STORAGE_STATE_JSON_PART6: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART6 }}
          BETBOOM_ACCOUNT2_LABEL: \"Аккаунт 2\"
""",
        "validation environment",
    )
    preflight = """          if not betboom_account_participation.configured():
              raise SystemExit(\"Vyacheslav second BetBoom session PART3/PART4 is not configured\")
"""
    text = replace_once(
        text,
        preflight,
        preflight
        + """          if not betboom_account_participation.xflarxx_configured():
              raise SystemExit(\"xFLARXx BetBoom session PART5/PART6 is not configured\")
""",
        "xFLARXx preflight",
    )
    text = replace_once(
        text,
        '          print("Auto participation preflight OK for both BetBoom accounts")\n',
        '          print("Auto participation preflight OK for all configured BetBoom accounts")\n',
        "preflight message",
    )
    text = replace_once(
        text,
        "      - name: Run second BetBoom account for Vyacheslav\n",
        "      - name: Run additional BetBoom accounts\n",
        "additional-account step",
    )
    text = replace_once(
        text,
        """          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}
          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}
          BETBOOM_ACCOUNT2_LABEL: \"Аккаунт 2\"
          BETBOOM_ACCOUNT2_TELEGRAM_USER: \"Вячеслав\"
""",
        """          BETBOOM_STORAGE_STATE_JSON_PART3: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART3 }}
          BETBOOM_STORAGE_STATE_JSON_PART4: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART4 }}
          BETBOOM_STORAGE_STATE_JSON_PART5: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART5 }}
          BETBOOM_STORAGE_STATE_JSON_PART6: ${{ secrets.BETBOOM_STORAGE_STATE_JSON_PART6 }}
          BETBOOM_ACCOUNT2_LABEL: \"Аккаунт 2\"
          BETBOOM_ACCOUNT2_TELEGRAM_USER: \"Вячеслав\"
          BETBOOM_ACCOUNT3_LABEL: \"xFLARXx\"
          BETBOOM_ACCOUNT3_TELEGRAM_USER: \"xFLARXx\"
""",
        "additional-account runtime environment",
    )
    path.write_text(text, encoding="utf-8")


def strip_workflow_section(installer: Path) -> Path:
    text = installer.read_text(encoding="utf-8")
    start = text.find(
        "# 2. Run PART5/PART6 in the normal serialized auto-participation workflow."
    )
    end = text.find("# 3. Fix the TypeError in owner user details", start)
    if start < 0 or end < 0:
        raise RuntimeError("installer workflow section boundaries not found")
    prepared = installer.with_name("prepared_" + installer.name)
    prepared.write_text(text[:start] + text[end:], encoding="utf-8")
    return prepared


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_xflarxx_patch.py APPLY_SCRIPT FINALIZER_SCRIPT")
    installer = Path(sys.argv[1])
    finalizer = Path(sys.argv[2])
    prepare_workflow()
    prepared = strip_workflow_section(installer)
    subprocess.run([sys.executable, str(prepared)], check=True)
    subprocess.run([sys.executable, str(finalizer)], check=True)
    print("xFLARXx patch runner completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
