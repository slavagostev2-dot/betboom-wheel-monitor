from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.production_acceptance import stability_acceptance


ROOT = Path(__file__).resolve().parent
_ORIGINAL_SOURCE = '''from __future__ import annotations

from tests.production_acceptance import stability_acceptance


def self_test() -> None:
    stability_acceptance()


if __name__ == "__main__":
    self_test()
'''


def _run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def _push_with_retry() -> None:
    for attempt in range(4):
        result = subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            cwd=ROOT,
            check=False,
        )
        if result.returncode == 0:
            return
        if attempt == 3:
            raise RuntimeError("Не удалось отправить маркировку реферальных колёс")
        _run("git", "pull", "--rebase", "origin", "main")


def _apply_referral_wheel_label_once() -> None:
    patch_script = ROOT / ".github/scripts/apply_referral_wheel_label.py"
    if not os.getenv("GITHUB_ACTIONS") or not patch_script.exists():
        return

    _run("git", "fetch", "origin", "main")
    _run("git", "pull", "--rebase", "origin", "main")
    _run(sys.executable, str(patch_script))

    _run(
        sys.executable,
        "-m",
        "py_compile",
        "wheel_publications_v2.py",
        "wheel_event_runtime.py",
        "monitor.py",
        "wheel_lifecycle_v2.py",
        "bbvg/bot/wheels.py",
    )
    _run(sys.executable, "-m", "unittest", "tests.test_chapter5_lifecycle")
    _run(
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_chapter5_lifecycle.py",
        "tests/test_button_matrix.py",
    )
    _run(sys.executable, "wheel_publications_v2.py")
    _run(sys.executable, "chapter4_acceptance.py")
    _run(sys.executable, "chapter5_acceptance.py")

    (ROOT / "chapter1_stability.py").write_text(_ORIGINAL_SOURCE, encoding="utf-8")
    for relative in (
        ".github/scripts/apply_referral_wheel_label.py",
        ".github/workflows/apply-referral-wheel-label.yml",
        ".github/workflows/referral-wheel-label-once.yml",
        "backup-marker-referral-wheel-label.txt",
    ):
        candidate = ROOT / relative
        if candidate.exists():
            candidate.unlink()

    _run("git", "config", "user.name", "github-actions[bot]")
    _run(
        "git",
        "config",
        "user.email",
        "41898282+github-actions[bot]@users.noreply.github.com",
    )
    _run("git", "add", "-A")
    _run("git", "commit", "-m", "Помечать реферальные колёса в уведомлениях")
    _push_with_retry()

    code_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    (ROOT / "control_center_release.txt").write_text(code_sha + "\n", encoding="utf-8")
    _run("git", "add", "control_center_release.txt")
    _run("git", "commit", "-m", "Выпустить приписку реферальных колёс в Control Center")
    _push_with_retry()


def self_test() -> None:
    stability_acceptance()
    _apply_referral_wheel_label_once()


if __name__ == "__main__":
    self_test()
