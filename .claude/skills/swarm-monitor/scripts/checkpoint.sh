#!/usr/bin/env bash
set -euo pipefail

MSG="${1:-}"

if [ -z "$MSG" ]; then
  echo "usage: checkpoint.sh \"commit message\""
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
BRANCH="$(git branch --show-current)"

cd "$ROOT"

if git diff --check; then
  true
else
  echo "Diff check failed. Fix whitespace/conflict markers before committing."
  exit 1
fi

if git diff --name-only --diff-filter=U | grep -q .; then
  echo "Unresolved merge conflicts present. Not committing."
  git diff --name-only --diff-filter=U
  exit 1
fi

if [ -z "$(git status --short)" ]; then
  echo "No changes to checkpoint on $BRANCH."
  exit 0
fi

git add -A

git commit -m "$MSG"

echo
echo "Checkpoint created on $BRANCH"
echo
git --no-pager log --oneline -5
