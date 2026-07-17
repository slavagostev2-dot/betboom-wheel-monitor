#!/usr/bin/env bash
set -euo pipefail

python .github/ch3-assemble.py
git apply --check /tmp/chapter3.patch
git apply /tmp/chapter3.patch
python .github/ch3-update-docs.py
python .github/ch3-cleanup.py

TEMP_WORKFLOW=/tmp/chapter3-audit.yml
if [[ -f .github/workflows/chapter3-audit.yml ]]; then
  mv .github/workflows/chapter3-audit.yml "$TEMP_WORKFLOW"
fi
restore_workflow() {
  if [[ -f "$TEMP_WORKFLOW" ]]; then
    mv "$TEMP_WORKFLOW" .github/workflows/chapter3-audit.yml
  fi
}
trap restore_workflow EXIT

python -m pip install -q -r requirements-dev.txt
python -m pip install -q PyYAML
python -m compileall -q .
python - <<'PY'
from pathlib import Path
import yaml
for path in sorted(Path('.github/workflows').glob('*.yml')):
    yaml.safe_load(path.read_text(encoding='utf-8'))
print('Workflow YAML parse passed')
PY
pytest -q tests/test_chapter3_contracts.py tests/test_lifecycle.py tests/test_recurring_event_hotfix.py tests/test_personal_wheel_voting.py tests/test_actions_security.py
pytest -q
python system_checks.py --self-test
python system_checks_v2.py --self-test
python preflight.py
python monitor_validation_v41.py
python tests/production_acceptance.py --section all

if git diff --name-only | grep -E '\.json$'; then
  echo 'Runtime JSON changed during chapter 3 validation' >&2
  exit 1
fi

restore_workflow
trap - EXIT
