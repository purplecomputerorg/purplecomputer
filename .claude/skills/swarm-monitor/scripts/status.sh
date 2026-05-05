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

  echo "Changed files vs $BASE:"
  git -C "$path" diff --name-status "$BASE...HEAD" || true
  echo

  echo "Latest commits:"
  git -C "$path" --no-pager log --oneline "$BASE..HEAD" -5 || true
  echo

  if [ -f "$path/.claude-lane-status.md" ]; then
    echo "Handoff:"
    sed -n '1,180p' "$path/.claude-lane-status.md"
    echo
  else
    echo "Handoff: none"
    echo
  fi
done
