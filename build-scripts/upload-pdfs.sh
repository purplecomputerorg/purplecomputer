#!/usr/bin/env bash
# Upload just the PDFs to R2 and purge cache.
#
# Usage:
#   ./upload-pdfs.sh
#   just upload-pdfs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/r2-helpers.sh"

r2_init
upload_pdfs
purge_cache "/purple-installation.pdf" "/purple-guide.pdf"
