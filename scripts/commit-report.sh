#!/usr/bin/env bash
# Commit the build report and the page-hash state to main with [skip ci].
# Nothing else is ever committed by the build: no SeatGeek data, no site files.
set -euo pipefail

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add reports/last-build.md state/page-hashes.json
if git diff --cached --quiet; then
  echo "commit-report: nothing changed"
  exit 0
fi
git commit -q -m "Build report $(date -u +'%Y-%m-%d %H:%M UTC') [skip ci]"
for attempt in 1 2 3; do
  if git pull -q --rebase origin main && git push -q origin HEAD:main; then
    echo "commit-report: pushed"
    exit 0
  fi
  sleep $((attempt * 5))
done
echo "commit-report: could not push the report" >&2
exit 1
