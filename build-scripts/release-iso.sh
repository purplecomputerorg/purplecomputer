#!/usr/bin/env bash
# Release Purple Computer ISOs to Cloudflare R2
#
# Usage:
#   ./release-iso.sh              # date-time version (v2026.03.30-1430)
#   ./release-iso.sh v1.0         # semver for major releases
#
# Uploads standard + debug ISOs with checksums, then updates
# the Cloudflare redirect rules so /download.iso and /download-debug.iso
# point to the new versioned paths (no re-upload needed).

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

# Version: argument or date-time
if [ -n "${1:-}" ]; then
    VERSION="$1"
else
    VERSION="v$(date +%Y.%m.%d-%H%M)"
fi

# Find ISOs (most recent by date)
# Reject fast builds (minimal compression, not for release)
# Public download stays the standard ISO; with-backup (second golden image
# copy) is only for flashed-and-shipped USBs. -fast dev builds never release.
STANDARD_ISO=$(list_build_isos | { grep -v -- "-fast" || true; } | filter_variant standard | head -1)
DEBUG_ISO=$(list_build_isos | { grep -v -- "-fast" || true; } | filter_variant debug | head -1)

if [ -z "$STANDARD_ISO" ]; then
    log_error "No standard ISO found in $ISO_DIR"
    echo "  Run the build first: just build-iso"
    exit 1
fi

if [ -z "$DEBUG_ISO" ]; then
    log_error "No debug ISO found in $ISO_DIR"
    echo "  Run the build first: just build-iso"
    exit 1
fi

# The ISOs must be one build, and that build must match this checkout. The
# .commit sidecar records the source commit baked into the image; older builds
# without one fall back to the hash inside a build-* version stamp.
STANDARD_STEM="${STANDARD_ISO%.iso}"
DEBUG_STEM="${DEBUG_ISO%.debug.iso}"
if [ "$STANDARD_STEM" != "$DEBUG_STEM" ]; then
    log_error "Standard and debug ISOs come from different builds:"
    echo "  $STANDARD_ISO"
    echo "  $DEBUG_ISO"
    exit 1
fi

ISO_VERSION="$(tr -d '[:space:]' < "${STANDARD_ISO}.version" 2>/dev/null || true)"
ISO_COMMIT="$(tr -d '[:space:]' < "${STANDARD_ISO}.commit" 2>/dev/null || true)"
if [ -z "$ISO_COMMIT" ] || [ "$ISO_COMMIT" = "unknown" ]; then
    [[ "$ISO_VERSION" =~ ^build-([0-9a-f]+)- ]] && ISO_COMMIT="${BASH_REMATCH[1]}" || ISO_COMMIT=""
fi
if [ -z "$ISO_COMMIT" ]; then
    log_error "Cannot tell which commit built $STANDARD_ISO; rebuild it before releasing."
    exit 1
fi
HEAD_COMMIT=$(git -C "$SCRIPT_DIR" rev-parse --short="${#ISO_COMMIT}" HEAD)
if [ "$ISO_COMMIT" != "$HEAD_COMMIT" ]; then
    log_error "This ISO was built from commit $ISO_COMMIT, but this checkout is at $HEAD_COMMIT."
    echo "  Rebuild from this checkout, or release from the checkout that built it."
    exit 1
fi

# A version stamped at build time is the release version; an argument may
# confirm it but not contradict it.
if [ -n "$ISO_VERSION" ] && [ "$ISO_VERSION" != "unknown" ] && [[ "$ISO_VERSION" != build-* ]]; then
    if [ -n "${1:-}" ] && [ "$1" != "$ISO_VERSION" ]; then
        log_error "This ISO is stamped $ISO_VERSION; it cannot be released as $1."
        exit 1
    fi
    VERSION="$ISO_VERSION"
fi

STANDARD_SIZE=$(du -h "$STANDARD_ISO" | cut -f1)
DEBUG_SIZE=$(du -h "$DEBUG_ISO" | cut -f1)

echo
echo "=========================================="
echo "  Purple Computer ISO Release"
echo "  Version: $VERSION"
echo "=========================================="
echo
log_info "Standard ISO: $STANDARD_ISO ($STANDARD_SIZE)"
log_info "Debug ISO:    $DEBUG_ISO ($DEBUG_SIZE)"
echo

# Confirm
read -p "Upload to R2 bucket '$R2_BUCKET' as $VERSION? [y/N] " -n 1 -r
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
log_step "1/4: Generating checksums..."
STANDARD_SHA256=$(sha256sum "$STANDARD_ISO" | cut -d' ' -f1)
DEBUG_SHA256=$(sha256sum "$DEBUG_ISO" | cut -d' ' -f1)
log_info "Standard: $STANDARD_SHA256"
log_info "Debug:    $DEBUG_SHA256"

# Step 2: Upload ISOs and checksums
log_step "2/4: Uploading standard ISO..."
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
log_step "3/4: Updating download redirect rules..."
"$SCRIPT_DIR/setup-cloudflare-rules.sh" "$VERSION"

# Step 4: Write latest.json
log_step "4/4: Writing latest.json..."
LATEST_JSON=$(cat <<ENDJSON
{
  "version": "${VERSION}",
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
if git -C "$SCRIPT_DIR" tag "$VERSION" 2>/dev/null; then
    log_info "Tagged $VERSION at $(git -C "$SCRIPT_DIR" rev-parse --short HEAD)"
else
    log_error "Could not create tag $VERSION (already exists?). Resolve manually: git tag $VERSION"
fi

log_info "Download links:"
log_info "  https://${R2_CUSTOM_DOMAIN}/download.iso"
log_info "  https://${R2_CUSTOM_DOMAIN}/download-debug.iso"
log_info "  https://${R2_CUSTOM_DOMAIN}/latest.json"
echo
