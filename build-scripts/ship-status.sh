#!/usr/bin/env bash
# One line per thing families or visitors get (the ISO build, both downloads, Studio, purplecomputer.org):
# what's there, whether it's behind main, and what to run. Run by just ship-2 and just studio-deploy too.
#
# Usage: ship-status.sh [-v]    -v lists the commits each one is missing
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PROJECT_DIR=$PWD
source build-scripts/config.sh
source build-scripts/flash-lib.sh
source build-scripts/image-lib.sh
verbose=${1:-}

# What reaches Studio's deploy: Studio and the Purple it bundles (scripts/studio_bundle.py).
STUDIO_PATHS=(studio purple_tui packs scripts/studio_bundle.py scripts/voice_model.sh)
# Purple itself, as both the 2.0 download and Studio's live Purple run it.
PURPLE_PATHS=(purple_tui packs scripts/voice_model.sh)
IMAGE_PATHS=($(image_paths . | sort -u))
LANDING=${LANDING_DIR:-$HOME/landing}

git fetch -q origin main release/1.x 2>/dev/null || echo "(GitHub unreachable: using the last fetch)"
main=$(git rev-parse origin/main)
fetch_json() { curl -fsS --max-time 10 "$1?t=$(date +%s)" 2>/dev/null; }
field() { sed -n "s/.*\"$2\": *\"\([^\"]*\)\".*/\1/p" <<<"$1" | head -1; }
known() { [ -n "$1" ] && git cat-file -e "$1^{commit}" 2>/dev/null; }
short() { known "$1" && git rev-parse --short=8 "$1"; }
# behind <commit> <tip> <paths...>: commits on tip since commit that touch the paths.
behind() { git rev-list --count --no-merges "$1..$2" -- "${@:3}"; }
details=""
# row <name> <commit> <version> <ok?> <state> [fix] [commits to list with -v]
row() {
    printf '%-14s %-9s %-17s %s %-36s %s\n' "$1" "$(short "$2")" "$3" "$([ "$4" = 1 ] && echo ✓ || echo ✗)" "$5" "${6:-}"
    [ -z "${7:-}" ] || details+=$'\n'"$1:"$'\n'"$7"
}
# log_since <commit> <paths...>: main's commits since commit that touch the paths, for -v.
log_since() { git log --oneline --no-merges "$1..$main" -- "${@:2}" | cut -c1-100 | sed 's/^/  /'; }

# The ISO build: the newest one built here from main.
build_iso=$(BUILD_BRANCH_FILTER=main list_build_isos | filter_variant | head -1)
build=$([ -n "$build_iso" ] && iso_commit "$build_iso")
if known "$build"; then
    n=$(behind "$build" "$main" "${IMAGE_PATHS[@]}")
    [ "$n" = 0 ] && row "ISO build" "$build" "$(cat "$build_iso.version" 2>/dev/null)" 1 "has main" \
        || row "ISO build" "$build" "$(cat "$build_iso.version" 2>/dev/null)" 0 "$n behind main" "just build" "$(log_since "$build" "${IMAGE_PATHS[@]}")"
else
    row "ISO build" "" "" 0 "none from main here" "just build"
fi

# The 2.0 download (purple2.purplecomputer.org, from purple2/latest.json).
json=$(fetch_json https://files.purplecomputer.org/purple2/latest.json)
iso=$(field "$json" commit)
if known "$iso"; then
    n=$(behind "$iso" "$main" "${IMAGE_PATHS[@]}")
    fix=$(known "$build" && [ "$(behind "$build" "$main" "${IMAGE_PATHS[@]}")" = 0 ] && echo "just ship-2" || echo "just build, then just ship-2")
    [ "$n" = 0 ] && row "2.0 download" "$iso" "$(field "$json" version)" 1 "has main" \
        || row "2.0 download" "$iso" "$(field "$json" version)" 0 "$n behind main" "$fix" "$(log_since "$iso" "${IMAGE_PATHS[@]}")"
else
    row "2.0 download" "$iso" "" 0 "couldn't read purple2/latest.json"
fi

# The 1.x download (purplecomputer.org's download page), against release/1.x.
check=$(bash build-scripts/release-check.sh 2>/dev/null)
v1=$(sed -n 's/^Commit: *\([0-9a-f]\{40\}\).*/\1/p' <<<"$check")
if known "$v1"; then
    n=$(git rev-list --count "$v1..origin/release/1.x")
    version=$(sed -n 's/^Download: *\([^,]*\).*/\1/p' <<<"$check")
    [ "$n" = 0 ] && row "1.x download" "$v1" "$version" 1 "has release/1.x" \
        || row "1.x download" "$v1" "$version" 0 "$n unshipped on release/1.x" "just release-status"
else
    row "1.x download" "" "" 0 "couldn't read latest.json" "just release-status"
fi

# Studio (studio.purplecomputer.org, from its version.json).
json=$(fetch_json https://studio.purplecomputer.org/version.json)
studio=$(field "$json" commit)
if known "$studio"; then
    n=$(behind "$studio" "$main" "${STUDIO_PATHS[@]}")
    note=$(grep -q '"dirty": *true' <<<"$json" && echo ", uncommitted build")
    [ "$n" = 0 ] && row "Studio" "$studio" "" 1 "has main$note" \
        || row "Studio" "$studio" "" 0 "$n behind main$note" "just studio-deploy --prod" "$(log_since "$studio" "${STUDIO_PATHS[@]}")"
    # Studio's demo and packs running Purple the 2.0 download doesn't have yet.
    if known "$iso" && git merge-base --is-ancestor "$iso" "$studio"; then
        n=$(behind "$iso" "$studio" "${PURPLE_PATHS[@]}")
        [ "$n" = 0 ] && row "Studio vs 2.0" "" "" 1 "same Purple as the download" \
            || row "Studio vs 2.0" "" "" 0 "Purple $n ahead of the download" "just ship-2 (just compat-check)"
    fi
else
    row "Studio" "" "" 0 "couldn't read version.json"
fi

# purplecomputer.org: main on GitHub, Vercel's production deploy of it, and the Studio it needs.
if [ -d "$LANDING/.git" ]; then
    git -C "$LANDING" fetch -q origin main 2>/dev/null
    site=$(git -C "$LANDING" rev-parse origin/main)
    unpushed=$(git -C "$LANDING" rev-list --count origin/main..main)
    repo=$(git -C "$LANDING" remote get-url origin | sed 's|.*github.com[:/]\(.*\)\.git$|\1|; s|.*github.com[:/]||')
    deploy=$(gh api "repos/$repo/deployments?sha=$site&environment=Production&per_page=1" -q '.[0].id' 2>/dev/null)
    state=$([ -n "$deploy" ] && gh api "repos/$repo/deployments/$deploy/statuses?per_page=1" -q '.[0].state' 2>/dev/null)
    short_site=$(git -C "$LANDING" rev-parse --short=8 "$site")
    case "$state:$unpushed" in
        success:0) printf '%-14s %-9s %-17s ✓ %s\n' "Landing" "$short_site" "" "live" ;;
        success:*) printf '%-14s %-9s %-17s ✗ %-36s %s\n' "Landing" "$short_site" "" "live, $unpushed local commit(s) unpushed" "git push (in ~/landing)" ;;
        *) printf '%-14s %-9s %-17s ✗ %-36s %s\n' "Landing" "$short_site" "" "Vercel: ${state:-no production deploy}" "check Vercel" ;;
    esac
    if needs=$(cd "$LANDING" && node scripts/check-studio.mjs 2>&1); then
        printf '%-14s %-9s %-17s ✓ %s\n' "Landing/Studio" "" "" "Studio has what the site needs"
    else
        printf '%-14s %-9s %-17s ✗ %-36s %s\n' "Landing/Studio" "" "" "needs a Studio change not live" "just studio-deploy --prod"
    fi
fi

if [ "$verbose" = -v ] && [ -n "$details" ]; then
    echo "$details"
elif [ -n "$details" ]; then
    echo "(-v lists the missing commits)"
fi
