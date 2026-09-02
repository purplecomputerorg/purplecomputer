#!/usr/bin/env bash
# What ships vs what waits: compares release/1.x against main.
# Everything through the base commit is on both branches. After that,
# = means cherry-picked onto release/1.x (ships), + means main only (waits),
# ~ means canvas UI only (never ships from 1.x: it waits for the next major release).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

base=$(git rev-parse --short "$(git merge-base release/1.x main)")
echo "Base: $base (all history through here ships)"
echo "After the base: = ships, + stays on main for the next major release, ~ canvas only (never ships from 1.x)"
echo

canvas_only() {
    local paths
    paths=$(git diff-tree --no-commit-id --name-only -r "$1")
    [ -n "$paths" ] && ! grep -qvE '^(purple_tui|tests)/canvas/' <<<"$paths"
}

picked=$(git log release/1.x --format=%b | sed -n 's/.*(cherry picked from commit \([0-9a-f]*\)).*/\1/p')
git log --oneline --no-merges release/1.x..main | while read -r sha rest; do
    if grep -q "$(git rev-parse "$sha")" <<<"$picked"; then
        echo "= $sha $rest"
    elif canvas_only "$sha"; then
        echo "~ $sha $rest"
    else
        echo "+ $sha $rest"
    fi
done
