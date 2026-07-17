#!/usr/bin/env bash
set -euo pipefail

rm -f .github/ch3-commit-push.sh
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A
git commit -m "Глава 3: закрепить контракты и достоверный health"
git push origin "HEAD:${GITHUB_HEAD_REF}"
