#!/usr/bin/env bash
# Publish a main (Purple 2.0) build for purple2.purplecomputer.org, under the
# purple2/ prefix on R2. Never touches the 1.x paths: releases/, latest.json,
# the /download*.iso redirects, or tags.
#
# Usage: ./upload-purple2.sh [commit]   (default: HEAD of the main checkout)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
source "$SCRIPT_DIR/r2-helpers.sh"

PREFIX=purple2
REF="${1:-HEAD}"
use_build_of_ref "$REF" || { log_error "Cannot resolve git commit '$REF'"; exit 1; }

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

# A version stamped at build time wins; otherwise the build time in UTC
VERSION="$(tr -d '[:space:]' < "$STANDARD_ISO.version" 2>/dev/null || true)"
if [[ -z "$VERSION" || "$VERSION" == unknown || "$VERSION" == build-* ]]; then
    VERSION="v$(date -u -r "$STANDARD_ISO" +%Y.%m.%d-%H%M)"
fi

# The page links the commit on GitHub
git -C "$PROJECT_DIR" fetch -q origin main 2>/dev/null || true
git -C "$PROJECT_DIR" merge-base --is-ancestor "$COMMIT" origin/main 2>/dev/null \
    || echo "Note: $SHORT is not on origin/main yet; the page's commit link 404s until it's pushed."

r2_init
echo ""
echo "  $(basename "${STANDARD_ISO%.iso}")  standard + debug, commit $SHORT"
echo "  -> purple2.purplecomputer.org as $VERSION"
echo ""
read -p "Upload? Type 'yes' to continue: " answer
[[ "$answer" == "yes" ]] || { log_info "Aborted."; exit 0; }

# Remembered before latest.json is overwritten, kept as the rollback
PREVIOUS="$(aws s3 cp "s3://${R2_BUCKET}/${PREFIX}/latest.json" - --endpoint-url "$R2_ENDPOINT" 2>/dev/null | jq -r '.version // empty' || true)"

upload_variant() {
    local iso="$1" name="$2" sha="$3" key="${PREFIX}/${VERSION}/$2.iso"
    aws s3 cp "$iso" "s3://${R2_BUCKET}/${key}" --endpoint-url "$R2_ENDPOINT" \
        --content-type application/octet-stream --no-progress \
        --content-disposition "attachment; filename=\"purple-computer-2-${VERSION}${4:-}.iso\""
    echo "$sha  $name.iso" | r2_upload - "${key}.sha256" text/plain
}
STANDARD_SHA="$(sha256sum "$STANDARD_ISO" | cut -d' ' -f1)"
DEBUG_SHA="$(sha256sum "$DEBUG_ISO" | cut -d' ' -f1)"
upload_variant "$STANDARD_ISO" standard "$STANDARD_SHA"
upload_variant "$DEBUG_ISO" debug "$DEBUG_SHA" -debug

jq -n --arg v "$VERSION" --arg c "$COMMIT" --arg p "$PREFIX/$VERSION" \
    --arg ss "$STANDARD_SHA" --arg ds "$DEBUG_SHA" \
    --arg sz "$(du -h "$STANDARD_ISO" | cut -f1)" --arg dz "$(du -h "$DEBUG_ISO" | cut -f1)" \
    '{version: $v, commit: $c, released: (now | todate),
      standard: {path: "\($p)/standard.iso", sha256: $ss, size: $sz},
      debug: {path: "\($p)/debug.iso", sha256: $ds, size: $dz}}' \
    | r2_upload - "${PREFIX}/latest.json" application/json
purge_cache "/${PREFIX}/latest.json"

# Keep this version and the one it replaced
for old in $(aws s3 ls "s3://${R2_BUCKET}/${PREFIX}/" --endpoint-url "$R2_ENDPOINT" | awk '$1 == "PRE" {print $2}' | tr -d /); do
    [[ "$old" == "$VERSION" || "$old" == "$PREVIOUS" ]] && continue
    aws s3 rm "s3://${R2_BUCKET}/${PREFIX}/${old}/" --recursive --endpoint-url "$R2_ENDPOINT" --quiet
    echo "Removed old $PREFIX/$old"
done

echo -e "${GREEN}Published${NC} $VERSION: https://purple2.purplecomputer.org"
