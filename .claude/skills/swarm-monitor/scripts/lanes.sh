#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-main}"

echo "Repo: $(git rev-parse --show-toplevel)"
echo "Base: $BASE"
echo

echo "Worktrees:"
git worktree list
echo

echo "Branches likely related to local lanes:"
git branch --format='%(refname:short)' \
  | grep -E '^(worktree-|ai/|feat-|fix-|chore-|lane-)' \
  || true
