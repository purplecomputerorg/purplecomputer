#!/usr/bin/env bash
# What customers have, what ships next, and what on main still needs a pick decision.
#
# Usage:
#   release-status.sh          # the decisions view
#   release-status.sh --all    # also list every hidden commit with its marker
#
# Markers: = picked onto release/1.x, + unpicked and reaches an ISO (decide),
# . docs or tooling that never reaches an ISO, ~ canvas UI only (next major
# release), w decided to wait (listed in build-scripts/release-waits).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
all=${1:-}

# The public download's latest.json records the shipped commit; offline, the newest tag.
check=$(bash build-scripts/release-check.sh 2>/dev/null || true)
shipped=$(sed -n 's/^Commit: *\([0-9a-f]\{40\}\).*/\1/p' <<<"$check")
if [ -n "$shipped" ]; then
    where=$(sed -n 's/^Download: *//p' <<<"$check")", from latest.json"
else
    tag=$(git describe --tags --abbrev=0 release/1.x)
    shipped=$(git rev-parse "${tag}^{commit}")
    where="$tag, newest tag (latest.json unreachable)"
fi
echo "Customers have:  $(git rev-parse --short "$shipped")  ($where)"

unshipped=$(git log --oneline "$shipped..release/1.x")
echo
if [ -n "$unshipped" ]; then
    echo "On release/1.x since then, unshipped ($(wc -l <<<"$unshipped")):"
    sed 's/^/  /' <<<"$unshipped"
else
    echo "Nothing on release/1.x since then."
fi

# Paths the image build copies in, plus the scripts that build it: a commit
# touching none of these cannot change what a customer runs.
ships=$(grep -o '/purple-src/[^ "$)]*' build-scripts/00-build-golden-image.sh \
    | sed 's|/purple-src/||; s|/\*.*||' | sort -u)
ships+=$'\n'"build-scripts/00-build-golden-image.sh
build-scripts/01-remaster-iso.sh
build-scripts/build-all.sh
build-scripts/build-in-docker.sh
build-scripts/config.sh
build-scripts/Dockerfile
build-scripts/install.sh"

reaches_iso() {
    local path prefix
    while read -r path; do
        case "$path" in purple_tui/canvas/*) continue ;; esac
        while read -r prefix; do
            [ "$path" = "$prefix" ] || [[ "$path" == "$prefix"/* ]] && return 0
        done <<<"$ships"
    done <<<"$(git diff-tree --no-commit-id --name-only -r "$1")"
    return 1
}

canvas_only() {
    local paths
    paths=$(git diff-tree --no-commit-id --name-only -r "$1")
    [ -n "$paths" ] && ! grep -qvE '^(purple_tui|tests)/canvas/' <<<"$paths"
}

picked=$(git log release/1.x --format=%b | sed -n 's/.*(cherry picked from commit \([0-9a-f]*\)).*/\1/p')
waits=$(grep -v '^\s*#' build-scripts/release-waits 2>/dev/null | awk 'NF{print $1}' || true)
decided_wait() {
    local w
    for w in $waits; do [[ "$1" == "$w"* ]] && return 0; done
    return 1
}

classified=$(git log --format='%h %H %as %s' --no-merges release/1.x..main | while read -r short full date rest; do
    if grep -q "$full" <<<"$picked"; then mark="="
    elif decided_wait "$full"; then mark="w"
    elif canvas_only "$full"; then mark="~"
    elif reaches_iso "$full"; then mark="+"
    else mark="."
    fi
    echo "$mark $short $date $rest"
done)

decide=$(grep '^+' <<<"$classified" || true)
echo
if [ -n "$decide" ]; then
    echo "On main, unpicked, reaches an ISO: decide fix or wait ($(wc -l <<<"$decide")):"
    sed 's/^+ /  /' <<<"$decide"
else
    echo "Nothing on main needs a pick decision."
fi
count() { grep -c "^$1" <<<"$classified" || true; }
echo
echo "Hidden: $(count '\.') docs and tooling, $(count '~') canvas only, $(count 'w') decided to wait, $(count '=') already picked (--all lists them)."
[ "$all" = "--all" ] && { echo; grep -v '^+' <<<"$classified"; }
exit 0
