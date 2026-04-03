#!/usr/bin/env bash
# Upload the early-access landing page + PDFs to R2 and purge cache.
#
# Usage:
#   ./upload-early-access.sh
#   just upload-early-access

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/r2-helpers.sh"

r2_init

# Upload landing page
r2_upload "$SCRIPT_DIR/early-access.html" "index.html" "text/html"
echo -e "${GREEN}Uploaded${NC} early-access.html → index.html"

# Extract and upload PDFs
upload_pdfs

purge_cache "/" "/index.html" "/purple-installation.pdf" "/purple-guide.pdf"
