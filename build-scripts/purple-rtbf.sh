#!/usr/bin/env bash
# purple-rtbf: release Test, Build, Flash, in one command.
#
#   1. Runs the release worktree's lint and tests (just release-test).
#   2. Builds its ISOs, full build with the with-backup variant, the same as
#      purple-build --release.
#   3. Looks for whitelisted USB drives at that moment and, if any are
#      plugged in, runs flash-all on them with no confirmation prompt.
#      Drives are only looked for after the build, so plug them in any time
#      before it finishes; with none plugged in it just says so.
#
# Usage: purple-rtbf [--no-flash] [--fast] [--force]
#   --no-flash  stop after the build
#   --fast      minimal compression (dev iteration only, not for shipping)
#   --force     build even if the release commit is already built
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
RELEASE_DIR="${PURPLE_RELEASE_DIR:-$HOME/purplecomputer-release}"

FLASH=true
BUILD_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --no-flash) FLASH=false ;;
        --fast|--force) BUILD_ARGS+=("$arg") ;;
        --help|-h) sed -n '2,15p' "$0" | cut -c3-; exit 0 ;;
        *) log_error "Unknown option: $arg"; exit 1 ;;
    esac
done

step() { echo; echo -e "${BOLD}==> $1${NC}"; }

branch="$(git -C "$RELEASE_DIR" rev-parse --abbrev-ref HEAD)"
[[ "$branch" == "release/1.x" ]] || { log_error "$RELEASE_DIR is on $branch, not release/1.x"; exit 1; }

echo -e "${BOLD}purple-rtbf${NC}: test, build, then flash release/1.x ($(git -C "$RELEASE_DIR" rev-parse --short HEAD))"
echo "  1. lint and tests in $RELEASE_DIR"
echo "  2. full ISO build of it, with-backup variant included${BUILD_ARGS[*]:+ (${BUILD_ARGS[*]})}"
if [[ "$FLASH" == true ]]; then
    echo "  3. flash every whitelisted drive plugged in by then, no prompt (plug them in any time before the build ends)"
else
    echo "  3. no flashing (--no-flash)"
fi

step "1/3 Testing release/1.x"
(cd "$RELEASE_DIR" && just test)

step "2/3 Building release/1.x"
PURPLE_WITH_BACKUP_ISO=1 "$RELEASE_DIR/build-scripts/build-in-docker.sh" 0 "${BUILD_ARGS[@]}"

[[ "$FLASH" == true ]] || { step "Done (no flash requested)"; exit 0; }

step "3/3 Flashing"
load_whitelist
find_whitelisted_drives
if [[ ${#FOUND_DRIVES[@]} -eq 0 ]]; then
    log_info "No whitelisted drives plugged in. Build is done; run 'just flash-all' when they are."
    exit 0
fi
log_info "${#FOUND_DRIVES[@]} whitelisted drive(s) plugged in, flashing them all."
exec "$SCRIPT_DIR/flash-all.sh" --yes
