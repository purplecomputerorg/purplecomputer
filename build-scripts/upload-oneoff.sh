#!/usr/bin/env bash
# Host one commit's ISO for a single customer at oneoff/<name>.iso on R2,
# outside the release paths the website and /download*.iso redirects use.
#
# Usage: ./upload-oneoff.sh <commit> [name] [--debug|--standard|--backup]
#   commit  a built commit (archive from 'just build --ref', or the build of
#           it still in the output dir); the newest build of it is used
#   name    file name without .iso; asked for when omitted (default
#           <variant>-<short hash>)
#   variant which ISO of that build, default --debug (one-offs are for
#           troubleshooting)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
source "$SCRIPT_DIR/r2-helpers.sh"

COMMIT="" NAME="" VARIANT=debug
for arg in "$@"; do
    case "$arg" in
        --debug|--standard|--backup) VARIANT="${arg#--}" ;;
        -*) log_error "Unknown option: $arg"; exit 1 ;;
        *) [[ -z "$COMMIT" ]] && COMMIT="$arg" || NAME="${arg%.iso}" ;;
    esac
done
[[ -n "$COMMIT" ]] || { echo "usage: upload-oneoff.sh <commit> [name] [--debug|--standard|--backup]"; exit 1; }

use_build_of_ref "$COMMIT" || { log_error "Cannot resolve git commit '$COMMIT'"; exit 1; }
ISO="$(list_build_isos | filter_variant "$VARIANT" | head -1)"
if [[ -z "$ISO" ]]; then
    log_error "No $VARIANT ISO found $(build_source_label)."
    echo "Build it first with 'just build --ref $COMMIT'."
    exit 1
fi

short="$(git -C "$PROJECT_DIR" rev-parse --short "$COMMIT^{commit}")"
if [[ -z "$NAME" ]]; then
    read -p "File name (Enter for $VARIANT-$short): " NAME
    NAME="${NAME%.iso}"
    NAME="${NAME:-$VARIANT-$short}"
fi

r2_init
url="https://${R2_CUSTOM_DOMAIN:-files.purplecomputer.org}/oneoff/${NAME}.iso"
echo ""
echo "  $(basename "$ISO")  [$(cat "$ISO.version" 2>/dev/null || echo "commit $short")]"
echo "  -> $url"
echo ""
read -p "Upload? Type 'yes' to continue: " answer
[[ "$answer" == "yes" ]] || { log_info "Aborted."; exit 0; }

r2_upload "$ISO" "oneoff/${NAME}.iso" "application/octet-stream"
echo -e "${GREEN}Uploaded${NC} $url"
