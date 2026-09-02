#!/usr/bin/env bash
# Release Purple Computer ISOs to Cloudflare R2
#
# Usage:
#   ./release-iso.sh                  # version from the build time (v2026.03.30-1430)
#   ./release-iso.sh v1.0             # semver for major releases
#   ./release-iso.sh --commit abc1234 # an earlier commit on the current branch
#
# Releases the commit checked out in the current directory (just ship runs
# this inside the release worktree), or with --commit an ancestor of it whose
# build is still around; the script and .env come from main.
#
# Uploads standard + debug ISOs with checksums, updates the Cloudflare
# redirect rules so /download.iso and /download-debug.iso point to the new
# versioned paths (no re-upload needed), then deletes every older release
# except the one just replaced, which stays as a rollback.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
ISO_DIR="$OUTPUT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load .env
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    log_error "Missing $ENV_FILE"
    echo "  Copy the template and fill in your R2 credentials:"
    echo "  cp $SCRIPT_DIR/.env.template $SCRIPT_DIR/.env"
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

# Validate required vars
MISSING=()
[ -z "${R2_BUCKET:-}" ] && MISSING+=("R2_BUCKET")
[ -z "${R2_ACCOUNT_ID:-}" ] && MISSING+=("R2_ACCOUNT_ID")
[ -z "${R2_ACCESS_KEY_ID:-}" ] && MISSING+=("R2_ACCESS_KEY_ID")
[ -z "${R2_SECRET_ACCESS_KEY:-}" ] && MISSING+=("R2_SECRET_ACCESS_KEY")
[ -z "${CF_API_TOKEN:-}" ] && MISSING+=("CF_API_TOKEN")
[ -z "${CF_ZONE_ID:-}" ] && MISSING+=("CF_ZONE_ID")
[ -z "${R2_CUSTOM_DOMAIN:-}" ] && MISSING+=("R2_CUSTOM_DOMAIN")

if [ ${#MISSING[@]} -gt 0 ]; then
    log_error "Missing required values in .env: ${MISSING[*]}"
    exit 1
fi

R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

VERSION_ARG=""
COMMIT_ARG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --commit) COMMIT_ARG="${2:?--commit needs a hash}"; shift 2 ;;
        --commit=*) COMMIT_ARG="${1#--commit=}"; shift ;;
        -*) log_error "Unknown option: $1"; exit 1 ;;
        *) VERSION_ARG="$1"; shift ;;
    esac
done

# The source commit baked into an ISO: the .commit sidecar, or for older
# builds the hash inside a build-* version stamp.
iso_commit() {
    local c v
    c="$(tr -d '[:space:]' < "$1.commit" 2>/dev/null || true)"
    v="$(tr -d '[:space:]' < "$1.version" 2>/dev/null || true)"
    if [ -z "$c" ] || [ "$c" = "unknown" ]; then
        [[ "$v" =~ ^build-([0-9a-f]+)- ]] && c="${BASH_REMATCH[1]}" || c=""
    fi
    echo "$c"
}

# stdin: ISO paths; keeps the ones built from the release commit.
built_from_commit() {
    local iso c
    while read -r iso; do
        c="$(iso_commit "$iso")"
        [ -n "$c" ] && [[ "$RELEASE_COMMIT" == "$c"* ]] && echo "$iso"
    done
    true
}

# Release the newest build of the release commit; newer builds of other
# commits (usually main) are ignored. Public download stays the standard ISO;
# with-backup (second golden image copy) is only for flashed-and-shipped USBs.
# -fast dev builds never release.
BRANCH=$(git rev-parse --abbrev-ref HEAD)
RELEASE_COMMIT=$(git rev-parse --verify --quiet "${COMMIT_ARG:-HEAD}^{commit}") \
    || { log_error "Not a commit: $COMMIT_ARG"; exit 1; }
SHORT_COMMIT=${RELEASE_COMMIT:0:7}
# The branch gets pushed as the shipped commit's home, so it has to contain it
git merge-base --is-ancestor "$RELEASE_COMMIT" HEAD \
    || { log_error "$SHORT_COMMIT is not on $BRANCH; only commits already on the shipping branch release"; exit 1; }
BEHIND=$(git rev-list --count "$RELEASE_COMMIT..HEAD")
STANDARD_ISO=$(list_build_isos | { grep -v -- "-fast" || true; } | filter_variant standard | built_from_commit | head -1)
DEBUG_ISO=$(list_build_isos | { grep -v -- "-fast" || true; } | filter_variant debug | built_from_commit | head -1)

if [ -z "$STANDARD_ISO" ] || [ -z "$DEBUG_ISO" ]; then
    log_error "No standard + debug ISO built from $SHORT_COMMIT in $ISO_DIR"
    echo "  Build this checkout first: purple-build --release"
    echo "  Or release an earlier commit that is built: just ship --commit <hash>"
    exit 1
fi

# The two ISOs must be one build
STANDARD_STEM="${STANDARD_ISO%.iso}"
DEBUG_STEM="${DEBUG_ISO%.debug.iso}"
if [ "$STANDARD_STEM" != "$DEBUG_STEM" ]; then
    log_error "Standard and debug ISOs come from different builds:"
    echo "  $STANDARD_ISO"
    echo "  $DEBUG_ISO"
    exit 1
fi

ISO_VERSION="$(tr -d '[:space:]' < "${STANDARD_ISO}.version" 2>/dev/null || true)"

# Version: argument, else the ISO's build time in UTC, the clock its filename date uses
VERSION="${VERSION_ARG:-v$(date -u -r "$STANDARD_ISO" +%Y.%m.%d-%H%M)}"

# A version stamped at build time is the release version; an argument may
# confirm it but not contradict it.
if [ -n "$ISO_VERSION" ] && [ "$ISO_VERSION" != "unknown" ] && [[ "$ISO_VERSION" != build-* ]]; then
    if [ -n "$VERSION_ARG" ] && [ "$VERSION_ARG" != "$ISO_VERSION" ]; then
        log_error "This ISO is stamped $ISO_VERSION; it cannot be released as $VERSION_ARG."
        exit 1
    fi
    VERSION="$ISO_VERSION"
fi

STANDARD_SIZE=$(du -h "$STANDARD_ISO" | cut -f1)
DEBUG_SIZE=$(du -h "$DEBUG_ISO" | cut -f1)

echo
log_info "Release $VERSION: commit $SHORT_COMMIT ($BRANCH)"
if [ "$BEHIND" -gt 0 ]; then
    log_info "$BEHIND newer commits on $BRANCH stay unshipped:"
    git log --format='  %h %<(72,trunc)%s' "$RELEASE_COMMIT..HEAD"
fi
log_info "ISO: $(basename "$STANDARD_STEM") standard + debug ($STANDARD_SIZE each)"
LAST_TAG=$(git describe --tags --abbrev=0 "$RELEASE_COMMIT" 2>/dev/null || true)
[ -n "$LAST_TAG" ] && log_info "$(git rev-list --count "$LAST_TAG..$RELEASE_COMMIT") commits since $LAST_TAG"
echo
read -p "Upload to the downloads as $VERSION? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"

s3_upload() {
    local src="$1"
    local dest="$2"
    local content_type="${3:-application/octet-stream}"
    local disposition="${4:-}"

    local extra_args=()
    if [ -n "$disposition" ]; then
        extra_args+=(--content-disposition "$disposition")
    fi

    aws s3 cp "$src" "s3://${R2_BUCKET}/${dest}" \
        --endpoint-url "$R2_ENDPOINT" \
        --content-type "$content_type" \
        --no-progress \
        "${extra_args[@]}"
}

echo

# Step 1: Generate checksums
log_step "1/5: Generating checksums..."
STANDARD_SHA256=$(sha256sum "$STANDARD_ISO" | cut -d' ' -f1)
DEBUG_SHA256=$(sha256sum "$DEBUG_ISO" | cut -d' ' -f1)
log_info "Standard: $STANDARD_SHA256"
log_info "Debug:    $DEBUG_SHA256"

# Step 2: Upload ISOs and checksums
log_step "2/5: Uploading standard ISO..."
s3_upload "$STANDARD_ISO" "releases/${VERSION}/standard.iso" \
    "application/octet-stream" "attachment; filename=\"purple-computer-${VERSION}.iso\""

log_step "      Uploading debug ISO..."
s3_upload "$DEBUG_ISO" "releases/${VERSION}/debug.iso" \
    "application/octet-stream" "attachment; filename=\"purple-computer-${VERSION}-debug.iso\""

log_step "      Uploading checksums..."
echo "$STANDARD_SHA256  standard.iso" | s3_upload - "releases/${VERSION}/standard.iso.sha256" "text/plain"
echo "$DEBUG_SHA256  debug.iso" | s3_upload - "releases/${VERSION}/debug.iso.sha256" "text/plain"

# Step 3: Update Cloudflare redirect rules
# /download.iso and /download-debug.iso redirect (302) to the versioned paths.
# This replaces re-uploading the full ISOs to pointer paths.
log_step "3/5: Updating download redirect rules..."
"$SCRIPT_DIR/setup-cloudflare-rules.sh" "$VERSION"

# Step 4: Write latest.json, remembering which release it replaces
log_step "4/5: Writing latest.json..."
PREVIOUS_VERSION=$(aws s3 cp "s3://${R2_BUCKET}/latest.json" - --endpoint-url "$R2_ENDPOINT" 2>/dev/null | jq -r '.version // empty' || true)
LATEST_JSON=$(cat <<ENDJSON
{
  "version": "${VERSION}",
  "commit": "${RELEASE_COMMIT}",
  "released": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "standard": {
    "path": "releases/${VERSION}/standard.iso",
    "sha256": "${STANDARD_SHA256}",
    "size": "${STANDARD_SIZE}"
  },
  "debug": {
    "path": "releases/${VERSION}/debug.iso",
    "sha256": "${DEBUG_SHA256}",
    "size": "${DEBUG_SIZE}"
  }
}
ENDJSON
)

echo "$LATEST_JSON" | s3_upload - "latest.json" "application/json"

echo
log_info "Release $VERSION uploaded successfully!"
echo

# Tag the shipped commit; tags are the record mapping a shipped ISO to a commit
if git tag "$VERSION" "$RELEASE_COMMIT" 2>/dev/null; then
    log_info "Tagged $VERSION at $SHORT_COMMIT"
else
    log_error "Could not create tag $VERSION (already exists?). Resolve manually: git tag $VERSION $SHORT_COMMIT"
fi

# The download page links the shipped commit on GitHub, so the branch has to be there
if git push -q -u origin "$BRANCH" $(git tag -l "$VERSION"); then
    log_info "Pushed $BRANCH and $VERSION to GitHub"
else
    log_error "Push failed; the release is fine but the download page's commit link will 404 until you run: git push -u origin $BRANCH $VERSION"
fi

# Step 5: keep the replaced release as a rollback, delete everything older
log_step "5/5: Cleaning old releases..."
"$SCRIPT_DIR/clean-old-releases.sh" --yes ${PREVIOUS_VERSION:+--keep "$PREVIOUS_VERSION"} \
    || log_error "Cleanup failed; the release is fine. Run: just clean-releases"
echo

log_info "Download links:"
log_info "  https://${R2_CUSTOM_DOMAIN}/download.iso"
log_info "  https://${R2_CUSTOM_DOMAIN}/download-debug.iso"
log_info "  https://${R2_CUSTOM_DOMAIN}/latest.json"
echo
