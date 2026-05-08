#!/usr/bin/env bash
# Upload only the early-access landing page (HTML) to R2 and purge cache.
#
# Usage:
#   ./upload-early-access-html.sh
#   just upload-early-access-html

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/r2-helpers.sh"

r2_init

r2_upload "$SCRIPT_DIR/early-access.html" "index.html" "text/html"
echo -e "${GREEN}Uploaded${NC} early-access.html → index.html"

purge_cache "/" "/index.html"
