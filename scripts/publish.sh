#!/usr/bin/env bash
# Publish the built site as ONE fresh orphan commit on gh-pages, force-pushed.
#
# CLAUDE.md rule 2: gh-pages must never accumulate price history, so the
# branch is replaced every build instead of getting a new commit on top.
#
# Refuses to publish a partial or rule-breaking build:
# - the hub and all 933 pages must be there,
# - no .json or .csv file may be in the tree (SeatGeek data lives only in HTML),
# - no github.io URL may appear (canonicals are hoopsmatic.com).
# PUBLISH_CHECK_ONLY=1 runs the checks and stops before touching git.
set -euo pipefail

SITE_DIR="${1:-site}"
BRANCH="${2:-gh-pages}"
EXPECTED="${EXPECTED_PAGES:-933}"

if [ ! -f "$SITE_DIR/index.html" ]; then
  echo "publish: $SITE_DIR/index.html is missing, refusing to publish" >&2
  exit 1
fi
PAGES=$(find "$SITE_DIR" -name index.html -type f | wc -l | tr -d ' ')
if [ "$PAGES" -ne "$EXPECTED" ]; then
  echo "publish: expected $EXPECTED pages, found $PAGES, refusing to publish" >&2
  exit 1
fi
DATA_FILES=$(find "$SITE_DIR" -type f \( -name '*.json' -o -name '*.csv' \) | head -5)
if [ -n "$DATA_FILES" ]; then
  echo "publish: data files in the site, refusing to publish:" >&2
  echo "$DATA_FILES" >&2
  exit 1
fi
if grep -rlq 'github\.io' "$SITE_DIR"; then
  echo "publish: a github.io URL leaked into the site, refusing to publish" >&2
  exit 1
fi
echo "publish: $PAGES pages, checks passed"

if [ "${PUBLISH_CHECK_ONLY:-}" = "1" ]; then
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -a "$SITE_DIR/." "$WORK/"
cd "$WORK"
git init -q
git checkout -q --orphan "$BRANCH"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A
git commit -q -m "Publish tickets $(date -u +'%Y-%m-%d %H:%M UTC')"
# PUBLISH_REMOTE lets a test push to a local repository instead.
REMOTE="${PUBLISH_REMOTE:-https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git}"
git push -q --force "$REMOTE" "$BRANCH"
echo "publish: pushed $PAGES pages to $BRANCH as a single commit"
