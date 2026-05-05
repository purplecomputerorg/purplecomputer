#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-main}"

git worktree list --porcelain | awk '
  /^worktree / { path=$2 }
  /^branch / {
    branch=$2
    sub("refs/heads/", "", branch)
    print path "|" branch
  }
' | while IFS='|' read -r path branch; do
  short="${path##*/}"
  echo "========================================"
  echo "Lane: $short    (branch: $branch)"
  echo "Path: $path"
  echo

  echo "Status:"
  git -C "$path" status --short || true
  echo

  echo "Commits ahead of $BASE:"
  git -C "$path" rev-list --count "$BASE..HEAD" || true
  echo

  echo "Latest lane commits:"
  git -C "$path" --no-pager log --oneline "$BASE..HEAD" -5 || true
  echo
done
