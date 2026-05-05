#!/usr/bin/env bash
set -euo pipefail

LANE="${1:-}"

if [ -z "$LANE" ]; then
  echo "usage: merge-lane.sh <lane-branch>"
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CURRENT="$(git branch --show-current)"

if [ "$CURRENT" = "$LANE" ]; then
  echo "Refusing to merge $LANE into itself. Switch to the target branch first."
  exit 1
fi

if [ -n "$(git status --short)" ]; then
  echo "Working tree is dirty on $CURRENT. Commit or stash before merging."
  git status --short
  exit 1
fi

if ! git rev-parse --verify --quiet "$LANE" >/dev/null; then
  echo "Branch not found: $LANE"
  exit 1
fi

AHEAD="$(git rev-list --count "$CURRENT..$LANE" 2>/dev/null || echo 0)"
BEHIND="$(git rev-list --count "$LANE..$CURRENT" 2>/dev/null || echo 0)"

echo "Merging $LANE into $CURRENT"
echo "  $LANE is $AHEAD commit(s) ahead, $BEHIND behind."
echo
echo "Lane commits to be merged:"
git log --oneline "$CURRENT..$LANE" || true
echo

if [ "$AHEAD" = "0" ]; then
  echo "No new commits on $LANE. Nothing to merge."
  exit 0
fi

git merge --no-ff --no-edit "$LANE"

echo
echo "Merge complete on $CURRENT."
echo "Latest:"
git log --oneline -5
echo
echo "Next: run your tests. Nothing has been pushed. The lane worktree/branch is untouched."
