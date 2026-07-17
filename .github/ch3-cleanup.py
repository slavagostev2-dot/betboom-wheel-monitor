from pathlib import Path

for path in [
    Path('.github/chapter3-patch-00.b64'),
    Path('.github/apply-ch3-00.part'),
    Path('.github/ch3-final-patch-00.part'),
]:
    path.unlink(missing_ok=True)

for pattern in (
    'ch3-code-patch-*.part',
    'ch3-agents-block.txt',
    'ch3-changelog-block.txt',
    'ch3-assemble.py',
    'ch3-update-docs.py',
    'ch3-cleanup.py',
    'ch3-apply-test.sh',
):
    for path in Path('.github').glob(pattern):
        path.unlink(missing_ok=True)
