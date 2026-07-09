#!/usr/bin/env bash
# Manually record a flashed build into the orders app's flashes table, for
# backfilling batches flashed before/outside `just flash-all` (which records
# automatically). Reads FLASH_LOG_URL and ADMIN_PASSWORD from build-scripts/.env,
# same convention as flash-all.sh and release-iso.sh. Never prints the password.
#
# Usage: just record-flash <commit-ish> [drive_count] [flashed_at]
#   just record-flash c0078cd 3
#   just record-flash HEAD 5 2026-07-09T13:00:00Z
# drive_count defaults to 1; flashed_at defaults to now (server side).

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
die() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

COMMITISH="${1:-}"
DRIVE_COUNT="${2:-1}"
FLASHED_AT="${3:-}"
[[ -n "$COMMITISH" ]] || die "Usage: just record-flash <commit-ish> [drive_count] [flashed_at]"
[[ "$DRIVE_COUNT" =~ ^[0-9]+$ ]] || die "drive_count must be a number, got: $DRIVE_COUNT"

# Resolve from the repo so a short hash, full sha, tag, or branch all work.
SHORT="$(git -C "$PROJECT_DIR" rev-parse --short "$COMMITISH" 2>/dev/null)" \
    || die "Not a known commit: $COMMITISH"
FULL="$(git -C "$PROJECT_DIR" rev-parse "$COMMITISH" 2>/dev/null)"

# Load the endpoint URL and admin password from .env without echoing them. Both
# live in build-scripts/.env so neither is hard-coded in this public repo.
[[ -f "$SCRIPT_DIR/.env" ]] && source "$SCRIPT_DIR/.env"
[[ -n "${FLASH_LOG_URL:-}" ]] || die "FLASH_LOG_URL not set in $SCRIPT_DIR/.env"
[[ -n "${ADMIN_PASSWORD:-}" ]] || die "ADMIN_PASSWORD not set in $SCRIPT_DIR/.env"

# Include flashed_at only when given, so the server defaults it to now().
PAYLOAD="{\"git_hash\":\"$SHORT\",\"git_full\":\"$FULL\",\"drive_count\":$DRIVE_COUNT"
[[ -n "$FLASHED_AT" ]] && PAYLOAD+=",\"flashed_at\":\"$FLASHED_AT\""
PAYLOAD+="}"

echo "Recording $SHORT ($DRIVE_COUNT drive(s))${FLASHED_AT:+ at $FLASHED_AT} to $FLASH_LOG_URL"
if curl -fsS --max-time 15 -u ":$ADMIN_PASSWORD" \
        -H 'Content-Type: application/json' \
        -X POST "$FLASH_LOG_URL" -d "$PAYLOAD" >/dev/null; then
    echo -e "${GREEN}Done. $SHORT now shows in the orders software dropdown.${NC}"
else
    die "POST failed (check ADMIN_PASSWORD and that the site is reachable)."
fi
