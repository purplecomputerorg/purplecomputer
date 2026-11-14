#!/usr/bin/env bash
# What reaches the image, and the version that follows from it.
# Source this file, don't run it directly.

# Paths the image build copies in, plus the scripts that build it: a commit
# touching none of these cannot change what a customer runs.
image_paths() {
    local repo="$1"
    grep -o '/purple-src/[^ "$)]*' "$repo/build-scripts/00-build-golden-image.sh" \
        | sed 's|/purple-src/||; s|/\*.*||'
    printf '%s\n' build-scripts/00-build-golden-image.sh build-scripts/01-remaster-iso.sh \
        build-scripts/build-all.sh build-scripts/build-in-docker.sh build-scripts/config.sh \
        build-scripts/Dockerfile build-scripts/install.sh build-scripts/image-lib.sh \
        purplecomputer/__init__.py
}

# v<major>.<minor>.<N> for a clean commit on main, N counting the main commits
# that touch image paths. Counted from the newest published v2.0.N tag so a
# later change to the path list can't renumber builds already out there.
# Prints nothing for anything else (dirty tree, lane branch, release/1.x,
# shallow clone).
image_version() {
    local repo="$1" tag base=0 range=HEAD major_minor n
    [ -z "$(git -C "$repo" status --porcelain)" ] || return 0
    [ "$(git -C "$repo" rev-parse --is-shallow-repository)" = false ] || return 0
    git -C "$repo" merge-base --is-ancestor HEAD main 2>/dev/null || return 0
    if tag=$(git -C "$repo" describe --tags --abbrev=0 --match 'v[0-9].[0-9]*.[0-9]*' HEAD 2>/dev/null); then
        base="${tag##*.}"
        range="$tag..HEAD"
    fi
    n=$(git -C "$repo" rev-list --count --first-parent "$range" -- $(image_paths "$repo" | sort -u))
    major_minor=$(sed -n 's/^__version__ = "\([0-9]*\.[0-9]*\).*/\1/p' "$repo/purplecomputer/__init__.py")
    echo "v$major_minor.$((base + n))"
}

# True for a version image_version stamps (vX.Y.N), false for dev builds.
is_release_version() {
    [[ "$1" =~ ^v[0-9]+(\.[0-9]+)+$ ]]
}
