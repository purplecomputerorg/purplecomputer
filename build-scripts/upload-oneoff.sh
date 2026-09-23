#!/usr/bin/env bash
# Upload one ISO to R2 under oneoff/<name>.iso: a link for a single customer,
# outside the release paths the website and /download*.iso redirects use.
#
# Usage: ./upload-oneoff.sh <iso> <name>      -> https://<files host>/oneoff/<name>.iso
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/r2-helpers.sh"

ISO="${1:?usage: upload-oneoff.sh <iso> <name>}"
NAME="${2:?usage: upload-oneoff.sh <iso> <name>}"
[ -f "$ISO" ] || { echo "No such file: $ISO"; exit 1; }

r2_init
r2_upload "$ISO" "oneoff/${NAME}.iso" "application/octet-stream"
echo -e "${GREEN}Uploaded${NC} https://${R2_CUSTOM_DOMAIN:-files.purplecomputer.org}/oneoff/${NAME}.iso"
