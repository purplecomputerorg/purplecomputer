#!/usr/bin/env bash
# Automatic fix application based on boot test analysis
# Reads test results and applies fixes automatically

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
TEST_DIR="/opt/purple-installer/test-results"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

error() { echo -e "${RED}[ERROR]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
action() { echo -e "${BLUE}[FIX]${NC} $1"; }

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Automatically apply fixes based on boot test failures"
    echo
    echo "Options:"
    echo "  --analysis FILE      Path to analysis file (default: latest)"
    echo "  --dry-run            Show what would be fixed without applying"
    echo "  --rebuild            Rebuild affected components after fixes"
    echo
    exit 1
}

# Parse arguments
ANALYSIS_FILE=""
DRY_RUN=0
REBUILD=1

while [ $# -gt 0 ]; do
    case "$1" in
        --analysis) ANALYSIS_FILE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --no-rebuild) REBUILD=0; shift ;;
        -h|--help) usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
done

find_latest_analysis() {
    if [ -z "$ANALYSIS_FILE" ]; then
        # Try system dir first, then local dir
        ANALYSIS_FILE=$(ls -t "$TEST_DIR"/analysis-*.txt 2>/dev/null | head -1)
        if [ -z "$ANALYSIS_FILE" ]; then
            # Try local test-results directory
            LOCAL_TEST_DIR="$SCRIPT_DIR/test-results"
            ANALYSIS_FILE=$(ls -t "$LOCAL_TEST_DIR"/analysis-*.txt 2>/dev/null | head -1)
        fi

        if [ -z "$ANALYSIS_FILE" ]; then
            error "No analysis files found in $TEST_DIR or $LOCAL_TEST_DIR"
            error "Run ./test-boot.sh first"
            exit 1
        fi
    fi

    if [ ! -f "$ANALYSIS_FILE" ]; then
        error "Analysis file not found: $ANALYSIS_FILE"
        exit 1
    fi

    info "Using analysis: $(basename $ANALYSIS_FILE)"
}

detect_issues() {
    info "Detecting issues from analysis..."

    ISSUES=()

    if grep -q "VFS: Unable to mount root" "$ANALYSIS_FILE"; then
        ISSUES+=("vfs_mount_root")
    fi

    if grep -q "Attempted to kill init" "$ANALYSIS_FILE"; then
        ISSUES+=("init_failed")
    fi

    if grep -q "No working init found" "$ANALYSIS_FILE"; then
        ISSUES+=("no_init")
    fi

    if grep -q "Installer partition not detected" "$ANALYSIS_FILE"; then
        ISSUES+=("partition_detection")
    fi

    if grep -q "/init is NOT executable" "$ANALYSIS_FILE"; then
        ISSUES+=("init_not_executable")
    fi

    if grep -q "BusyBox is dynamically linked" "$ANALYSIS_FILE"; then
        ISSUES+=("busybox_dynamic")
    fi

    if grep -q "BusyBox NOT FOUND" "$ANALYSIS_FILE"; then
        ISSUES+=("busybox_missing")
    fi

    if grep -q "CONFIG_.*NOT ENABLED" "$ANALYSIS_FILE"; then
        ISSUES+=("missing_kernel_config")
    fi

    if [ ${#ISSUES[@]} -eq 0 ]; then
        ok "No fixable issues detected in analysis"
        exit 0
    fi

    info "Found ${#ISSUES[@]} issue(s): ${ISSUES[*]}"
}

fix_vfs_mount_root() {
    action "Fixing: VFS unable to mount root filesystem"

    # Check if initramfs exists
    if [ ! -f "$BUILD_DIR/initrd.img" ]; then
        action "  Rebuilding initramfs (missing)..."
        if [ "$DRY_RUN" -eq 0 ]; then
            cd "$SCRIPT_DIR"
            ./02-build-initramfs.sh
        else
            info "  [DRY RUN] Would rebuild initramfs"
        fi
        return
    fi

    # Check kernel config
    if [ -f "$BUILD_DIR/kernel-config-purple" ]; then
        if ! grep -q "^CONFIG_EXT4_FS=y" "$BUILD_DIR/kernel-config-purple"; then
            action "  Adding CONFIG_EXT4_FS=y to kernel config..."
            if [ "$DRY_RUN" -eq 0 ]; then
                echo "CONFIG_EXT4_FS=y" >> "$SCRIPT_DIR/kernel-config-fragment.config"
                action "  Rebuilding kernel..."
                cd "$SCRIPT_DIR"
                ./00-build-custom-kernel.sh
            else
                info "  [DRY RUN] Would add CONFIG_EXT4_FS=y and rebuild kernel"
            fi
        fi
    fi
}

fix_init_failed() {
    action "Fixing: Init process failed"

    # Extract and examine initramfs
    local TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" RETURN

    cd "$TEMP_DIR"
    if zcat "$BUILD_DIR/initrd.img" | cpio -i 2>/dev/null; then
        local NEEDS_REBUILD=0

        # Check if init exists
        if [ ! -f init ]; then
            error "  Init script missing from initramfs"
            NEEDS_REBUILD=1
        fi

        # Check if init is executable
        if [ -f init ] && [ ! -x init ]; then
            error "  Init script not executable"
            NEEDS_REBUILD=1
        fi

        # Check busybox
        if [ ! -f bin/busybox ]; then
            error "  BusyBox missing"
            NEEDS_REBUILD=1
        fi

        if [ "$NEEDS_REBUILD" -eq 1 ]; then
            action "  Rebuilding initramfs to fix issues..."
            if [ "$DRY_RUN" -eq 0 ]; then
                cd "$SCRIPT_DIR"
                ./02-build-initramfs.sh
            else
                info "  [DRY RUN] Would rebuild initramfs"
            fi
        fi
    else
        action "  Initramfs corrupted, rebuilding..."
        if [ "$DRY_RUN" -eq 0 ]; then
            cd "$SCRIPT_DIR"
            ./02-build-initramfs.sh
        else
            info "  [DRY RUN] Would rebuild initramfs"
        fi
    fi
}

fix_no_init() {
    action "Fixing: No working init found"
    # Same fix as init_failed
    fix_init_failed
}

fix_init_not_executable() {
    action "Fixing: Init not executable in initramfs"
    # Rebuild initramfs - the build script should make it executable
    if [ "$DRY_RUN" -eq 0 ]; then
        cd "$SCRIPT_DIR"
        ./02-build-initramfs.sh
    else
        info "  [DRY RUN] Would rebuild initramfs with executable init"
    fi
}

fix_busybox_dynamic() {
    action "Fixing: BusyBox is dynamically linked"

    error "  BusyBox must be statically compiled"
    error "  This is a Docker/build environment issue"

    action "  Checking Dockerfile for busybox-static..."
    if grep -q "busybox-static" "$SCRIPT_DIR/Dockerfile"; then
        ok "  Dockerfile has busybox-static package"
        warn "  But build used wrong busybox - check if busybox (dynamic) is also installed"
        warn "  The build script should prefer busybox-static"
    else
        action "  Adding busybox-static to Dockerfile..."
        if [ "$DRY_RUN" -eq 0 ]; then
            # Add busybox-static if not present
            if ! grep -q "busybox-static" "$SCRIPT_DIR/Dockerfile"; then
                sed -i '/apt-get install/a\    busybox-static \\' "$SCRIPT_DIR/Dockerfile"
                ok "  Added busybox-static to Dockerfile"
            fi
        else
            info "  [DRY RUN] Would add busybox-static to Dockerfile"
        fi
    fi

    action "  Rebuilding Docker image and initramfs..."
    if [ "$DRY_RUN" -eq 0 ]; then
        warn "  You need to rebuild the Docker image:"
        warn "  cd $SCRIPT_DIR && docker build -t purple-installer-builder ."
        warn "  Then run: ./02-build-initramfs.sh"
    fi
}

fix_busybox_missing() {
    action "Fixing: BusyBox missing from initramfs"
    # Same as dynamic linking issue
    fix_busybox_dynamic
}

fix_partition_detection() {
    action "Fixing: Installer partition not detected"

    action "  Rebuilding ISO with correct volume label..."
    if [ "$DRY_RUN" -eq 0 ]; then
        cd "$SCRIPT_DIR"
        ./04-build-iso.sh
    else
        info "  [DRY RUN] Would rebuild ISO"
    fi
}

fix_missing_kernel_config() {
    action "Fixing: Missing kernel configuration options"

    # Extract missing configs from analysis
    local MISSING_CONFIGS=$(grep "NOT ENABLED" "$ANALYSIS_FILE" | sed 's/.*✗ //' | sed 's/ NOT ENABLED.*//')

    if [ -z "$MISSING_CONFIGS" ]; then
        warn "  Could not extract missing configs from analysis"
        return
    fi

    action "  Missing configs:"
    echo "$MISSING_CONFIGS" | while read cfg; do
        echo "    - $cfg"
    done

    action "  These should already be in kernel-config-fragment.config"
    action "  Rebuilding kernel to ensure they're applied..."

    if [ "$DRY_RUN" -eq 0 ]; then
        cd "$SCRIPT_DIR"
        ./00-build-custom-kernel.sh
    else
        info "  [DRY RUN] Would rebuild kernel"
    fi
}

apply_fixes() {
    info "Applying fixes for detected issues..."

    for issue in "${ISSUES[@]}"; do
        case "$issue" in
            vfs_mount_root) fix_vfs_mount_root ;;
            init_failed) fix_init_failed ;;
            no_init) fix_no_init ;;
            init_not_executable) fix_init_not_executable ;;
            busybox_dynamic) fix_busybox_dynamic ;;
            busybox_missing) fix_busybox_missing ;;
            partition_detection) fix_partition_detection ;;
            missing_kernel_config) fix_missing_kernel_config ;;
            *) warn "  Unknown issue type: $issue" ;;
        esac
    done
}

rebuild_iso() {
    if [ "$REBUILD" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
        info "Rebuilding final ISO..."
        cd "$SCRIPT_DIR"
        ./04-build-iso.sh
        ok "ISO rebuilt with fixes applied"
    fi
}

retest() {
    if [ "$DRY_RUN" -eq 0 ]; then
        echo
        info "Fixes applied. Retest with:"
        info "  ./test-boot.sh"
        echo
        read -p "Run boot test now? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ./test-boot.sh
        fi
    fi
}

main() {
    echo
    echo "=========================================="
    echo "  PurpleOS Auto-Fix"
    echo "=========================================="
    echo

    if [ "$DRY_RUN" -eq 1 ]; then
        warn "DRY RUN MODE - no changes will be made"
        echo
    fi

    find_latest_analysis
    detect_issues
    apply_fixes
    rebuild_iso

    echo
    ok "Auto-fix complete!"

    retest
}

main "$@"
