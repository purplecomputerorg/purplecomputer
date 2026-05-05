#!/usr/bin/env bash
set -euo pipefail

LANE="${1:-}"
ORIG="$LANE"

if [ -z "$LANE" ]; then
  echo "usage: merge-lane.sh <lane-name>"
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CURRENT="$(git branch --show-current)"

if [ "$CURRENT" = "$LANE" ]; then
  echo "Refusing to merge $LANE into itself. Switch to the target branch first."
  exit 1
fi

if [ -n "$(git status --short --untracked-files=no)" ]; then
  echo "Working tree has tracked modifications on $CURRENT. Commit or stash before merging."
  git status --short --untracked-files=no
  exit 1
fi

resolve_lane() {
  local name="$1"
  if git rev-parse --verify --quiet "refs/heads/$name" >/dev/null; then
    echo "$name"; return 0
  fi
  if git rev-parse --verify --quiet "refs/heads/worktree-$name" >/dev/null; then
    echo "worktree-$name"; return 0
  fi
  local match
  match="$(git worktree list --porcelain | awk -v n="$name" '
    /^worktree / { p=$2; b="" }
    /^branch /   { b=$2; sub("refs/heads/", "", b)
                   nb=p; sub(".*/","",nb)
                   if (nb==n || b==n) print b
                 }
  ' | head -n1)"
  if [ -n "$match" ]; then
    echo "$match"; return 0
  fi
  return 1
}

RESOLVED="$(resolve_lane "$LANE" || true)"
if [ -z "$RESOLVED" ]; then
  echo "Branch not found for lane: $LANE"
  echo "Available worktrees:"
  git worktree list
  exit 1
fi
LANE="$RESOLVED"

AHEAD="$(git rev-list --count "$CURRENT..$LANE" 2>/dev/null || echo 0)"
BEHIND="$(git rev-list --count "$LANE..$CURRENT" 2>/dev/null || echo 0)"

echo "Merging $LANE into $CURRENT"
echo "  $LANE is $AHEAD commit(s) ahead, $BEHIND behind."
echo
echo "Lane commits to be merged:"
git --no-pager log --oneline "$CURRENT..$LANE" || true
echo

if [ "$AHEAD" = "0" ]; then
  echo "No new commits on $LANE. Nothing to merge."
  exit 0
fi

SHORT="${ORIG#worktree-}"
git merge --no-ff -m "merge: $SHORT" "$LANE"

echo
echo "Merge complete on $CURRENT."
echo "Latest:"
git --no-pager log --oneline -5
echo
echo "Next: run your tests. Nothing has been pushed. The lane worktree/branch is untouched."
