#!/usr/bin/env bash
# Build PurpleOS installer in Docker (Initramfs injection architecture)
# Usage: ./build-in-docker.sh [step]
#   step: optional step number to start from (0-1, default: 0)
#     0 = build golden image (pre-built Ubuntu system)
#     1 = remaster Ubuntu Server ISO (inject hook into initramfs)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
IMAGE_NAME="purple-installer-builder"
FAST_BUILD=0

# Parse arguments
START_STEP=0
for arg in "$@"; do
    case "$arg" in
        --fast) FAST_BUILD=1 ;;
        *) START_STEP="$arg" ;;
    esac
done

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

main() {
    cd "$SCRIPT_DIR"

    # Build Docker image
    log_step "Building Docker image..."
    docker build -t "$IMAGE_NAME" .

    # Run build in container
    log_info "Running build in container (starting from step $START_STEP)..."
    log_info "Architecture: Initramfs Injection"
    log_info "  - We download official Ubuntu Server ISO"
    log_info "  - We inject a hook script into the initramfs"
    log_info "  - Squashfs and boot stack remain untouched"

    # Mount the entire project directory (parent of build-scripts) as /purple-src
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

    # Resolve version on the host where git works (container hits safe.directory errors)
    if [ -z "${PURPLE_VERSION:-}" ]; then
        local git_hash
        git_hash=$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
        PURPLE_VERSION="build-${git_hash}-$(date +%Y%m%d)"
    fi

    docker run --rm --privileged \
        -v "$SCRIPT_DIR:/build" \
        -v "$PROJECT_DIR:/purple-src" \
        -v "$INSTALLER_BASE:$INSTALLER_BASE" \
        -e "PURPLE_VERSION=${PURPLE_VERSION}" \
        -e "FAST_BUILD=${FAST_BUILD}" \
        -e "PURPLE_NO_BACKUP_ISO=${PURPLE_NO_BACKUP_ISO:-}" \
        "$IMAGE_NAME" \
        /build/build-all.sh "$START_STEP"

    log_info "Build complete!"
    log_info "Output in: $OUTPUT_DIR/"
}

main "$@"
