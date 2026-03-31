#!/usr/bin/env bash
# Upload the early-access landing page to R2 as index.html
#
# Usage:
#   ./upload-early-access.sh
#   just upload-early-access

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML_FILE="$SCRIPT_DIR/early-access.html"

GREEN='\033[0;32m'
NC='\033[0m'

# Load .env
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE (need R2 credentials)"
    exit 1
fi
set -a
source "$ENV_FILE"
set +a

MISSING=()
[ -z "${R2_BUCKET:-}" ] && MISSING+=("R2_BUCKET")
[ -z "${R2_ACCOUNT_ID:-}" ] && MISSING+=("R2_ACCOUNT_ID")
[ -z "${R2_ACCESS_KEY_ID:-}" ] && MISSING+=("R2_ACCESS_KEY_ID")
[ -z "${R2_SECRET_ACCESS_KEY:-}" ] && MISSING+=("R2_SECRET_ACCESS_KEY")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Missing required values in .env: ${MISSING[*]}"
    exit 1
fi

R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"

aws s3 cp "$HTML_FILE" "s3://${R2_BUCKET}/index.html" \
    --endpoint-url "$R2_ENDPOINT" \
    --content-type "text/html" \
    --no-progress

echo -e "${GREEN}Uploaded${NC} early-access.html → downloads.purplecomputer.org"
