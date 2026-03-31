#!/usr/bin/env bash
# Delete old releases from Cloudflare R2, keeping only the current version.
#
# Usage:
#   ./clean-old-releases.sh           # interactive: lists old releases, asks before deleting
#   ./clean-old-releases.sh --dry-run # just show what would be deleted

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=true
fi

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

if [ ${#MISSING[@]} -gt 0 ]; then
    log_error "Missing required values in .env: ${MISSING[*]}"
    exit 1
fi

R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"

S3_ARGS="--endpoint-url $R2_ENDPOINT"

# Get current version from latest.json
log_info "Fetching current version from latest.json..."
LATEST_JSON=$(aws s3 cp "s3://${R2_BUCKET}/latest.json" - $S3_ARGS 2>/dev/null) || {
    log_error "Could not fetch latest.json from R2. No releases found?"
    exit 1
}

CURRENT_VERSION=$(echo "$LATEST_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['version'])")
log_info "Current version: $CURRENT_VERSION"
echo

# List all release versions
log_info "Listing all releases..."
ALL_VERSIONS=$(aws s3 ls "s3://${R2_BUCKET}/releases/" $S3_ARGS 2>/dev/null \
    | awk '{print $NF}' \
    | sed 's|/$||' \
    | sort)

if [ -z "$ALL_VERSIONS" ]; then
    log_info "No releases found in bucket."
    exit 0
fi

# Find old versions (everything except current)
OLD_VERSIONS=()
while IFS= read -r version; do
    if [ "$version" != "$CURRENT_VERSION" ]; then
        OLD_VERSIONS+=("$version")
    fi
done <<< "$ALL_VERSIONS"

if [ ${#OLD_VERSIONS[@]} -eq 0 ]; then
    log_info "No old releases to clean up. Only the current version ($CURRENT_VERSION) exists."
    exit 0
fi

# Show what will be deleted
echo "=========================================="
echo "  Releases to delete:"
echo "=========================================="
for version in "${OLD_VERSIONS[@]}"; do
    echo -e "  ${RED}DELETE${NC}  releases/$version/"
done
echo
echo -e "  ${GREEN}KEEP${NC}    releases/$CURRENT_VERSION/ (current)"
echo
echo "  ${#OLD_VERSIONS[@]} old release(s) will be removed."
echo

if [ "$DRY_RUN" = true ]; then
    log_warn "Dry run: nothing was deleted."
    exit 0
fi

# Confirm
read -p "Are you sure you want to delete these releases? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo

# Delete each old version
for version in "${OLD_VERSIONS[@]}"; do
    log_info "Deleting releases/$version/..."
    aws s3 rm "s3://${R2_BUCKET}/releases/${version}/" \
        $S3_ARGS \
        --recursive \
        --quiet
done

echo
log_info "Done! Deleted ${#OLD_VERSIONS[@]} old release(s). Current version ($CURRENT_VERSION) preserved."
