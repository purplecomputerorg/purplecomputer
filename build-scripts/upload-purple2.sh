#!/usr/bin/env bash
# Publish a main build to the customer download (downloads.purplecomputer.org),
# under the purple2/ prefix on R2 (named for when it was the 2.0 preview). Never
# touches the v1 paths: releases/, latest.json, or the /download*.iso
# redirects. Tags the commit with its v2.0.N version.
#
# Usage: ./upload-purple2.sh [commit]   (default: HEAD of the main checkout; just ship)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
source "$SCRIPT_DIR/r2-helpers.sh"
source "$SCRIPT_DIR/image-lib.sh"

PREFIX=purple2
REF="${1:-HEAD}"
use_build_of_ref "$REF" || { log_error "Cannot resolve git commit '$REF'"; exit 1; }
# Cards come from the commit asked for, even when an older build ships
CARDS_COMMIT="$(git -C "$PROJECT_DIR" rev-parse "$REF^{commit}")"

find_isos() {
    local isos
    isos="$(list_build_isos | { grep -v -- "-fast" || true; })"
    STANDARD_ISO="$(filter_variant standard <<< "$isos" | head -1)"
    DEBUG_ISO="$(filter_variant debug <<< "$isos" | head -1)"
}
find_isos
if [[ -z "$STANDARD_ISO" || -z "$DEBUG_ISO" ]]; then
    log_error "No standard + debug ISO $(build_source_label)."
    # With no commit given, offer the newest main build instead
    BUILT=""
    if [[ -z "${1:-}" ]]; then
        BUILD_COMMIT_FILTER=""
        use_newest_build_on --main
        find_isos
        [[ -n "$DEBUG_ISO" ]] && BUILT="$(iso_commit "$DEBUG_ISO")"
    fi
    if [[ -n "$BUILT" ]]; then
        echo "Newest main build: $(git -C "$PROJECT_DIR" log -1 --format='%h %s' "$BUILT")"
        echo "  ($(git -C "$PROJECT_DIR" rev-list --count "$BUILT..HEAD") commits behind HEAD)"
        read -p "Ship that one instead? [y/N] " answer
        [[ "$answer" == [yY]* ]] || exit 1
        REF="$BUILT"
    else
        echo "Build it first: just build (or just build --ref $(git -C "$PROJECT_DIR" rev-parse --short "$REF"))"
        exit 1
    fi
fi
COMMIT="$(git -C "$PROJECT_DIR" rev-parse "$REF^{commit}")"
SHORT="${COMMIT:0:7}"
if [[ "${STANDARD_ISO%.iso}" != "${DEBUG_ISO%.debug.iso}" ]]; then
    log_error "Standard and debug ISOs come from different builds:"
    echo "  $STANDARD_ISO"; echo "  $DEBUG_ISO"
    exit 1
fi

VERSION="$(tr -d '[:space:]' < "$STANDARD_ISO.version" 2>/dev/null || true)"
# The Pi image ships only when it carries the same version stamp as the ISOs
PI_IMG="$(pi_image_for_commit "$(iso_commit "$STANDARD_ISO")")"
if [[ -n "$PI_IMG" && "$(tr -d '[:space:]' < "$PI_IMG.version" 2>/dev/null)" != "$VERSION" ]]; then
    echo "Note: $(basename "$PI_IMG") has a different version stamp than the ISOs, so it won't ship."
    PI_IMG=""
fi

# The page links the commit on GitHub
git -C "$PROJECT_DIR" fetch -q origin main 2>/dev/null || true
git -C "$PROJECT_DIR" merge-base --is-ancestor "$COMMIT" origin/main 2>/dev/null \
    || echo "Note: $SHORT is not on origin/main yet; the page's commit link 404s until it's pushed."

r2_init
STANDARD_SHA="$(sha256sum "$STANDARD_ISO" | cut -d' ' -f1)"
DEBUG_SHA="$(sha256sum "$DEBUG_ISO" | cut -d' ' -f1)"
# Read before latest.json is overwritten: the previous version is kept as the rollback
LIVE="$(aws s3 cp "s3://${R2_BUCKET}/${PREFIX}/latest.json" - --endpoint-url "$R2_ENDPOINT" 2>/dev/null || echo '{}')"
PREVIOUS="$(jq -r '.version // empty' <<< "$LIVE")"
# Same ISOs already live: keep their version and only refresh the cards
ISOS_LIVE=false
if [[ "$(jq -r '"\(.standard.sha256) \(.debug.sha256)"' <<< "$LIVE")" == "$STANDARD_SHA $DEBUG_SHA" ]]; then
    ISOS_LIVE=true VERSION="$PREVIOUS"
fi
# Uploaded unless this exact image is already live; with the ISOs live and no
# local image, the live one stays listed
PI_SHA="" PI_UPLOAD=false PI_JSON=null
[[ -z "$PI_IMG" ]] || PI_SHA="$(sha256sum "$PI_IMG" | cut -d' ' -f1)"
if [[ -n "$PI_SHA" ]] && ! { $ISOS_LIVE && [[ "$(jq -r '.pi.sha256 // empty' <<< "$LIVE")" == "$PI_SHA" ]]; }; then
    PI_UPLOAD=true
elif $ISOS_LIVE; then
    PI_JSON="$(jq -c '.pi // null' <<< "$LIVE")"
fi
# Families see this version in the Parent Menu; only a clean commit on main is stamped v2.0.N
if ! $ISOS_LIVE && ! is_release_version "$VERSION"; then
    log_error "$(basename "$STANDARD_ISO") is a dev build (${VERSION:-no version}): the tree wasn't a clean main when it was built."
    echo "Build from a clean main checkout: just rtbf, or PURPLE_WITH_BACKUP_ISO=1 just build"
    exit 1
fi

echo ""
echo "  $(basename "${STANDARD_ISO%.iso}")  standard + debug, commit $SHORT"
if $ISOS_LIVE; then
    echo "  ISOs already live as $VERSION: updating the rest, cards from ${CARDS_COMMIT:0:7}"
else
    echo "  -> downloads.purplecomputer.org as $VERSION"
fi
if $PI_UPLOAD; then
    echo "  Raspberry Pi image: $(basename "$PI_IMG")"
elif [[ "$PI_JSON" == null ]]; then
    echo "  No Raspberry Pi image for this build, so the page won't list one (just build-pi adds it)."
fi
echo ""
read -p "Upload? Type 'yes' to continue: " answer
[[ "$answer" == "yes" ]] || { log_info "Aborted."; exit 0; }

# upload_file <local> <name on R2> <sha256> <filename the browser saves>
upload_file() {
    local key="${PREFIX}/${VERSION}/$2"
    aws s3 cp "$1" "s3://${R2_BUCKET}/${key}" --endpoint-url "$R2_ENDPOINT" \
        --content-type application/octet-stream --no-progress \
        --content-disposition "attachment; filename=\"$4\""
    echo "$3  $2" | r2_upload - "${key}.sha256" text/plain
}
if ! $ISOS_LIVE; then
    upload_file "$STANDARD_ISO" standard.iso "$STANDARD_SHA" "purple-computer-${VERSION}.iso"
    upload_file "$DEBUG_ISO" debug.iso "$DEBUG_SHA" "purple-computer-${VERSION}-debug.iso"
fi
if $PI_UPLOAD; then
    upload_file "$PI_IMG" pi.img.xz "$PI_SHA" "purple-computer-${VERSION}-raspberry-pi-experimental.img.xz"
    PI_JSON="$(jq -nc --arg p "$PREFIX/$VERSION/pi.img.xz" --arg s "$PI_SHA" --arg z "$(du -h "$PI_IMG" | cut -f1)" \
        '{path: $p, sha256: $s, size: $z}')"
fi

CARDS='[]' CARD_PATHS=()
for card in "Start:start" "Rooms:rooms" "Code:code" "Grown-ups:grown-ups"; do
    label="${card%%:*}" src="$CARDS_COMMIT:cards/v2/out/${card#*:}.pdf" key="${PREFIX}/${VERSION}/cards/${card#*:}.pdf"
    git -C "$PROJECT_DIR" cat-file -e "$src" 2>/dev/null || { echo "No $label card at ${CARDS_COMMIT:0:7}, skipped"; continue; }
    git -C "$PROJECT_DIR" show "$src" | r2_upload - "$key" application/pdf
    CARDS="$(jq -c --arg l "$label" --arg p "$key" '. + [{label: $l, path: $p}]' <<< "$CARDS")"
    CARD_PATHS+=("/$key")
done

jq -n --arg v "$VERSION" --arg c "$COMMIT" --arg p "$PREFIX/$VERSION" \
    --arg ss "$STANDARD_SHA" --arg ds "$DEBUG_SHA" \
    --arg sz "$(du -h "$STANDARD_ISO" | cut -f1)" --arg dz "$(du -h "$DEBUG_ISO" | cut -f1)" \
    --argjson cards "$CARDS" --argjson pi "$PI_JSON" \
    '{version: $v, commit: $c, released: (now | todate),
      standard: {path: "\($p)/standard.iso", sha256: $ss, size: $sz},
      debug: {path: "\($p)/debug.iso", sha256: $ds, size: $dz},
      cards: $cards} + if $pi then {pi: $pi} else {} end' \
    | r2_upload - "${PREFIX}/latest.json" application/json
purge_cache "/${PREFIX}/latest.json" "${CARD_PATHS[@]}"
if $ISOS_LIVE; then
    echo -e "${GREEN}Updated${NC} $VERSION: https://downloads.purplecomputer.org"
    exit 0
fi

# Keep this version and the one it replaced
for old in $(aws s3 ls "s3://${R2_BUCKET}/${PREFIX}/" --endpoint-url "$R2_ENDPOINT" | awk '$1 == "PRE" {print $2}' | tr -d /); do
    [[ "$old" == "$VERSION" || "$old" == "$PREVIOUS" ]] && continue
    aws s3 rm "s3://${R2_BUCKET}/${PREFIX}/${old}/" --recursive --endpoint-url "$R2_ENDPOINT" --quiet
    echo "Removed old $PREFIX/$old"
done

# The tag anchors image_version's count, so later builds keep this numbering
if [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    if git -C "$PROJECT_DIR" tag "$VERSION" "$COMMIT" 2>/dev/null; then
        git -C "$PROJECT_DIR" push -q origin "$VERSION" || echo "Could not push tag $VERSION; push it by hand: git push origin $VERSION"
    else
        echo "Tag $VERSION already exists (same image as an earlier upload); left as is."
    fi
fi

echo -e "${GREEN}Published${NC} $VERSION: https://downloads.purplecomputer.org"
