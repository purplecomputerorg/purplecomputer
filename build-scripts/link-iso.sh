#!/usr/bin/env bash
# Symlink a built ISO into ~/isos so it can be pulled to another machine with
# a short scp line or picked up in Cyberduck, without browsing /opt.
#
# Usage: ./link-iso.sh [--debug|--no-backup] [--ref <commit>] [iso-path]
# Same ISO picker as flash-to-usb.sh; without flags it asks which of the
# newest build's ISOs to link. Links whose build has since been deleted are
# removed on every run.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"

LINK_DIR="$HOME/isos"
ISO_ACTION=Link
SKIP_CONFIRM=false
iso_kind=""
while [[ -n "${1:-}" ]]; do
    case "$1" in
        --debug|-d)  iso_kind=debug; shift ;;
        --no-backup) iso_kind=standard; shift ;;
        --ref)       use_build_of_ref "$2" || { log_error "Cannot resolve git commit '$2'"; exit 1; }; shift 2 ;;
        --help|-h)   sed -n '2,8p' "$0" | cut -c3-; exit 0 ;;
        -*)          log_error "Unknown option: $1"; exit 1 ;;
        *)           break ;;
    esac
done

if [[ -n "${1:-}" ]]; then
    ISO_PATH="$1"
    [[ -f "$ISO_PATH" ]] || { log_error "ISO not found: $ISO_PATH"; exit 1; }
elif [[ -n "$iso_kind" ]]; then
    resolve_variant "$iso_kind"
else
    select_iso
fi

mkdir -p "$LINK_DIR"
for f in "$LINK_DIR"/*.iso; do
    [[ -L "$f" && ! -e "$f" ]] && rm -f "$f" && log_info "Removed $(basename "$f"): its build is gone"
done
ln -sfn "$ISO_PATH" "$LINK_DIR/$(basename "$ISO_PATH")"
log_info "Linked $(basename "$ISO_PATH") [$(cat "$ISO_PATH.version" 2>/dev/null || echo "no version stamp")]"
echo ""
echo "  scp $(hostname -s):isos/$(basename "$ISO_PATH") ~/Downloads/"
echo ""
