#!/usr/bin/env bash
# Where main, the 2.0 download and live Purple Studio stand, and what each is missing, so nothing on main
# is forgotten. 1.x has its own view: just release-status. Run by just ship-2 and just studio-deploy too.
#
# Usage: ship-status.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source build-scripts/image-lib.sh

# What reaches Studio's deploy: Studio and the Purple it bundles (scripts/studio_bundle.py).
STUDIO_PATHS=(studio purple_tui packs scripts/studio_bundle.py scripts/voice_model.sh)
# Purple itself, as both the 2.0 download and Studio's live Purple run it.
PURPLE_PATHS=(purple_tui packs scripts/voice_model.sh)
SHOWN=12

git fetch -q origin main 2>/dev/null || echo "(Couldn't reach GitHub: comparing against the last fetch.)"
fetch_json() { curl -fsS --max-time 10 "$1?t=$(date +%s)" 2>/dev/null; }
field() { sed -n "s/.*\"$2\": *\"\([^\"]*\)\".*/\1/p" <<<"$1" | head -1; }
known() { [ -n "$1" ] && git cat-file -e "$1^{commit}" 2>/dev/null; }
describe() { git log -1 --format='%h %as %s' "$1" | cut -c1-90; }

iso_json=$(fetch_json https://files.purplecomputer.org/purple2/latest.json)
studio_json=$(fetch_json https://studio.purplecomputer.org/version.json)
iso=$(field "$iso_json" commit)
studio=$(field "$studio_json" commit)
main=$(git rev-parse origin/main)

echo "main on GitHub: $(describe "$main")"
ahead=$(git rev-list --count origin/main..main 2>/dev/null || echo 0)
[ "$ahead" = 0 ] || echo "  local main has $ahead commit(s) not on GitHub: push them"
known "$iso" && echo "2.0 download:   $(field "$iso_json" version), $(describe "$iso")" \
    || echo "2.0 download:   unknown (purple2/latest.json unreachable, or its commit isn't in this clone)"
known "$studio" && echo "Studio live:    $(describe "$studio")" \
    || echo "Studio live:    unknown (version.json unreachable, or its commit isn't in this clone)"
grep -q '"dirty": *true' <<<"$studio_json" && echo "  Studio was deployed with uncommitted changes"
known "$studio" && ! git merge-base --is-ancestor "$studio" "$main" && echo "  Studio was deployed from a commit that isn't on main"

# missing <from> <title> <what to run> <paths...>: main's commits since <from> that touch the paths.
missing() {
    local from=$1 title=$2 run=$3 list n
    shift 3
    known "$from" || return 0
    list=$(git log --oneline --no-merges "$from..$main" -- "$@" | cut -c1-100)
    echo
    if [ -z "$list" ]; then
        echo "$title: nothing."
        return 0
    fi
    n=$(wc -l <<<"$list")
    echo "$title ($n): $run"
    head -"$SHOWN" <<<"$list" | sed 's/^/  /'
    [ "$n" -le "$SHOWN" ] || echo "  ...and $((n - SHOWN)) more"
}

missing "$iso" "On main, not in the 2.0 download" "just build, then just ship-2" $(image_paths . | sort -u)
missing "$studio" "On main, not live in Studio" "just studio-deploy --prod" "${STUDIO_PATHS[@]}"

# Studio's live Purple running ahead of the download: its demo, and the packs it makes, show Purple that
# families can't get yet.
if known "$iso" && known "$studio" && git merge-base --is-ancestor "$iso" "$studio"; then
    ahead=$(git rev-list --count --no-merges "$iso..$studio" -- "${PURPLE_PATHS[@]}")
    echo
    if [ "$ahead" = 0 ]; then
        echo "Studio runs the same Purple as the 2.0 download."
    else
        echo "Studio runs $ahead Purple change(s) the 2.0 download doesn't have: its demo and packs are ahead of"
        echo "what families can download. just ship-2 catches the download up; just compat-check confirms the"
        echo "builds families already have can open what Studio makes."
    fi
fi

landing=${LANDING_DIR:-$HOME/landing}
if [ -d "$landing/.git" ]; then
    git -C "$landing" fetch -q origin main 2>/dev/null
    unpushed=$(git -C "$landing" rev-list --count origin/main..main 2>/dev/null || echo 0)
    echo
    [ "$unpushed" = 0 ] && echo "purplecomputer.org: main is pushed (pushing deploys it)." \
        || echo "purplecomputer.org: $unpushed commit(s) on main not pushed, so not live."
    (cd "$landing" && node scripts/check-studio.mjs 2>&1 | sed 's/^ *//' | grep . | sed 's/^/  /')
fi

echo
echo "1.x download: just release-status"
