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
BUILD_REF=""
while [ $# -gt 0 ]; do
    case "$1" in
        --fast) FAST_BUILD=1 ;;
        --ref) BUILD_REF="$2"; shift ;;
        *) START_STEP="$1" ;;
    esac
    shift
done

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Build an old commit without touching current state: check it out into a
# temp worktree and point every mount at archive/<hash>, which holds its own
# golden image and output dir. Flash the result with 'just flash --ref <hash>'.
setup_ref_build() {
    HOST_INSTALLER_DIR="$(archive_dir_for_ref "$BUILD_REF")" || exit 1
    local hash="${HOST_INSTALLER_DIR##*/}" main_repo="$PROJECT_DIR"
    WORKTREE_DIR="$HOST_INSTALLER_DIR/src"
    # /opt/purple-installer is root-owned (normally only docker writes there),
    # so the host-side prep needs sudo and a user-owned archive dir.
    sudo install -d -o "$(id -u)" -g "$(id -g)" \
        "$HOST_INSTALLER_DIR" "$HOST_INSTALLER_DIR/build"
    if [ -e "$WORKTREE_DIR" ]; then
        git -C "$main_repo" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
        git -C "$main_repo" worktree prune
    fi
    git -C "$main_repo" worktree add --detach "$WORKTREE_DIR" "$hash"
    trap "git -C '$main_repo' worktree remove --force '$WORKTREE_DIR' 2>/dev/null || true" EXIT
    # Reuse the already-downloaded Ubuntu ISO instead of fetching it again
    if [ -f "$BUILD_DIR/$UBUNTU_ISO_NAME" ] && [ ! -e "$HOST_INSTALLER_DIR/build/$UBUNTU_ISO_NAME" ]; then
        sudo ln "$BUILD_DIR/$UBUNTU_ISO_NAME" "$HOST_INSTALLER_DIR/build/$UBUNTU_ISO_NAME" 2>/dev/null || \
            sudo cp "$BUILD_DIR/$UBUNTU_ISO_NAME" "$HOST_INSTALLER_DIR/build/$UBUNTU_ISO_NAME"
    fi
    PROJECT_DIR="$WORKTREE_DIR"
    BUILD_CTX="$WORKTREE_DIR/build-scripts"
    IMAGE_NAME="$IMAGE_NAME-$hash"
    OUTPUT_DIR="$HOST_INSTALLER_DIR/output"
    log_info "Building commit $hash in isolation under $HOST_INSTALLER_DIR"
}

main() {
    cd "$SCRIPT_DIR"

    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    HOST_INSTALLER_DIR="$INSTALLER_BASE"
    BUILD_CTX="$SCRIPT_DIR"
    if [ -n "$BUILD_REF" ]; then
        setup_ref_build
    fi

    if [ "$START_STEP" -ge 1 ]; then
        log_info "Build plan: ISOs only (reusing existing golden image)"
    else
        log_info "Build plan: golden image (the slow step), then ISOs"
    fi
    log_info "Will produce in $OUTPUT_DIR:"
    planned_iso_names | while read -r line; do log_info "  $line"; done

    # Build Docker image
    log_step "Building Docker image..."
    docker build -t "$IMAGE_NAME" "$BUILD_CTX"

    # Run build in container
    log_info "Running build in container (starting from step $START_STEP)..."
    log_info "Architecture: Initramfs Injection"
    log_info "  - We download official Ubuntu Server ISO"
    log_info "  - We inject a hook script into the initramfs"
    log_info "  - Squashfs and boot stack remain untouched"

    # Resolve version on the host where git works (container hits safe.directory errors)
    if [ -z "${PURPLE_VERSION:-}" ]; then
        local git_hash
        git_hash=$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
        PURPLE_VERSION="build-${git_hash}-$(date +%Y%m%d)"
    fi

    docker run --rm --privileged \
        -v "$BUILD_CTX:/build" \
        -v "$PROJECT_DIR:/purple-src" \
        -v "$HOST_INSTALLER_DIR:$INSTALLER_BASE" \
        -e "PURPLE_VERSION=${PURPLE_VERSION}" \
        -e "FAST_BUILD=${FAST_BUILD}" \
        -e "PURPLE_WITH_BACKUP_ISO=${PURPLE_WITH_BACKUP_ISO:-}" \
        "$IMAGE_NAME" \
        /build/build-all.sh "$START_STEP"

    log_info "Build complete!"
    log_info "Output in: $OUTPUT_DIR/"
}

main "$@"
