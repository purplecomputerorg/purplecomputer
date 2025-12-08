#!/usr/bin/env bash
# Automated boot testing with QEMU
# Boots the ISO, captures all output, analyzes for panics/errors, suggests fixes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
OUTPUT_DIR="/opt/purple-installer/output"
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

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Automated boot testing for PurpleOS installer"
    echo
    echo "Options:"
    echo "  --timeout SECONDS    Boot timeout in seconds (default: 60)"
    echo "  --iso PATH           Path to ISO file (default: auto-detect latest)"
    echo "  --memory MB          QEMU memory in MB (default: 2048)"
    echo "  --debug              Enable verbose QEMU output"
    echo "  --interactive        Open QEMU window (default: headless)"
    echo "  --keep-logs          Don't delete logs after successful boot"
    echo
    exit 1
}

# Parse arguments
TIMEOUT=60
ISO_PATH=""
MEMORY=2048
DEBUG=0
INTERACTIVE=0
KEEP_LOGS=0

while [ $# -gt 0 ]; do
    case "$1" in
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --iso) ISO_PATH="$2"; shift 2 ;;
        --memory) MEMORY="$2"; shift 2 ;;
        --debug) DEBUG=1; shift ;;
        --interactive) INTERACTIVE=1; shift ;;
        --keep-logs) KEEP_LOGS=1; shift ;;
        -h|--help) usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
done

check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        error "This script must be run with sudo"
        error "Run: sudo ./test-boot.sh"
        exit 1
    fi
}

check_qemu() {
    if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
        error "QEMU not found. Install with:"
        error "  Ubuntu: apt-get install qemu-system-x86"
        error "  NixOS: nix-shell -p qemu"
        exit 1
    fi
    ok "QEMU found: $(qemu-system-x86_64 --version | head -1)"
}

find_iso() {
    if [ -z "$ISO_PATH" ]; then
        ISO_PATH=$(ls -t "$OUTPUT_DIR"/purple-installer-*.iso 2>/dev/null | head -1)
        if [ -z "$ISO_PATH" ]; then
            error "No ISO found in $OUTPUT_DIR"
            error "Build the ISO first: ./build-in-docker.sh"
            exit 1
        fi
    fi

    if [ ! -f "$ISO_PATH" ]; then
        error "ISO not found: $ISO_PATH"
        exit 1
    fi

    ok "Testing ISO: $(basename $ISO_PATH) ($(du -h $ISO_PATH | cut -f1))"
}

setup_test_env() {
    # Try system test dir first, fallback to local if no permissions
    if ! mkdir -p "$TEST_DIR" 2>/dev/null; then
        warn "Cannot write to $TEST_DIR (need sudo), using local directory"
        TEST_DIR="$(pwd)/test-results"
        mkdir -p "$TEST_DIR"
    fi

    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    LOG_FILE="$TEST_DIR/boot-test-${TIMESTAMP}.log"
    SERIAL_LOG="$TEST_DIR/serial-${TIMESTAMP}.log"
    ANALYSIS_FILE="$TEST_DIR/analysis-${TIMESTAMP}.txt"

    info "Test logs will be saved to: $TEST_DIR"
}

boot_test() {
    info "Starting QEMU boot test (timeout: ${TIMEOUT}s)..."

    # Create temporary target disk for installation testing
    TARGET_DISK=$(mktemp -u).qcow2
    qemu-img create -f qcow2 "$TARGET_DISK" 20G > /dev/null 2>&1
    info "Created temporary target disk: $TARGET_DISK"

    # Build QEMU command
    # Use -hda to simulate USB stick (hybrid ISO shows as /dev/sda)
    # Use -hdb as target installation disk (shows as /dev/sdb)
    # Use -snapshot to avoid write lock issues
    QEMU_CMD=(
        qemu-system-x86_64
        -m "$MEMORY"
        -hda "$ISO_PATH"
        -hdb "$TARGET_DISK"
        -snapshot
        -serial file:"$SERIAL_LOG"
        -boot c
        -no-reboot
    )

    if [ "$INTERACTIVE" -eq 0 ]; then
        QEMU_CMD+=(-nographic)
    fi

    if [ "$DEBUG" -eq 1 ]; then
        QEMU_CMD+=(-d cpu_reset,guest_errors)
    fi

    info "QEMU command: ${QEMU_CMD[@]}"

    # Start QEMU in background
    "${QEMU_CMD[@]}" > "$LOG_FILE" 2>&1 &
    QEMU_PID=$!

    info "QEMU started (PID: $QEMU_PID)"

    # Monitor boot process
    local ELAPSED=0
    local CHECK_INTERVAL=2

    while [ $ELAPSED -lt $TIMEOUT ]; do
        if ! kill -0 $QEMU_PID 2>/dev/null; then
            warn "QEMU exited early (after ${ELAPSED}s)"
            break
        fi

        # Check for success markers in serial log
        if grep -q "PurpleOS Installer Starting" "$SERIAL_LOG" 2>/dev/null; then
            ok "Installer started successfully!"
            sleep 2  # Let it run a bit more
            kill $QEMU_PID 2>/dev/null || true
            wait $QEMU_PID 2>/dev/null || true
            return 0
        fi

        # Check for kernel panic
        if grep -qi "kernel panic" "$SERIAL_LOG" 2>/dev/null; then
            error "Kernel panic detected!"
            kill $QEMU_PID 2>/dev/null || true
            wait $QEMU_PID 2>/dev/null || true
            return 1
        fi

        # Check for init errors
        if grep -qi "Cannot find PurpleOS installer partition" "$SERIAL_LOG" 2>/dev/null; then
            warn "Installer partition detection failed"
            kill $QEMU_PID 2>/dev/null || true
            wait $QEMU_PID 2>/dev/null || true
            return 2
        fi

        sleep $CHECK_INTERVAL
        ELAPSED=$((ELAPSED + CHECK_INTERVAL))

        # Progress indicator
        if [ $((ELAPSED % 10)) -eq 0 ]; then
            info "Boot progress: ${ELAPSED}/${TIMEOUT}s..."
        fi
    done

    # Timeout reached
    warn "Boot test timed out after ${TIMEOUT}s"
    kill $QEMU_PID 2>/dev/null || true
    wait $QEMU_PID 2>/dev/null || true
    return 3
}

analyze_logs() {
    local EXIT_CODE=$1

    info "Analyzing boot logs..."

    {
        echo "=========================================="
        echo "  PurpleOS Boot Test Analysis"
        echo "  $(date)"
        echo "=========================================="
        echo
        echo "ISO: $ISO_PATH"
        echo "Exit Code: $EXIT_CODE"
        echo

        case $EXIT_CODE in
            0)
                echo "RESULT: SUCCESS - Installer started normally"
                echo
                echo "The boot process succeeded. The installer environment loaded correctly."
                ;;
            1)
                echo "RESULT: KERNEL PANIC DETECTED"
                echo
                analyze_kernel_panic
                ;;
            2)
                echo "RESULT: INSTALLER PARTITION NOT FOUND"
                echo
                analyze_partition_detection
                ;;
            3)
                echo "RESULT: BOOT TIMEOUT"
                echo
                analyze_timeout
                ;;
            *)
                echo "RESULT: UNKNOWN FAILURE"
                echo
                echo "QEMU exited unexpectedly. Check logs manually."
                ;;
        esac

        echo
        echo "=========================================="
        echo "  Full Serial Console Output"
        echo "=========================================="
        cat "$SERIAL_LOG" 2>/dev/null || echo "(no serial output)"

    } > "$ANALYSIS_FILE"

    # Display analysis
    cat "$ANALYSIS_FILE"

    info "Analysis saved to: $ANALYSIS_FILE"
}

analyze_kernel_panic() {
    echo "Kernel panic occurred during boot. Analyzing..."
    echo

    # Extract panic message
    if grep -A 20 -i "kernel panic" "$SERIAL_LOG" > /tmp/panic.txt; then
        echo "Panic message:"
        echo "---"
        cat /tmp/panic.txt
        echo "---"
        echo
    fi

    # Determine root cause
    if grep -qi "VFS: Unable to mount root" "$SERIAL_LOG"; then
        echo "ROOT CAUSE: Cannot mount root filesystem"
        echo
        echo "LIKELY ISSUES:"
        echo "  1. Initramfs not found or corrupted"
        echo "  2. Missing CONFIG_EXT4_FS=y in kernel"
        echo "  3. Initramfs path wrong in boot config"
        echo
        echo "AUTOMATIC FIXES TO APPLY:"
        echo "  - Verify initramfs exists: ls -lh $BUILD_DIR/initrd.img"
        echo "  - Check kernel config: grep CONFIG_EXT4_FS=y $BUILD_DIR/kernel-config-purple"
        echo "  - Rebuild initramfs: ./02-build-initramfs.sh"

    elif grep -qi "Attempted to kill init" "$SERIAL_LOG"; then
        echo "ROOT CAUSE: Init process failed or not found"
        echo
        echo "LIKELY ISSUES:"
        echo "  1. /init script missing or not executable in initramfs"
        echo "  2. BusyBox missing or dynamically linked"
        echo "  3. Init script has syntax errors"
        echo
        echo "AUTOMATIC FIXES TO APPLY:"
        extract_and_check_initramfs

    elif grep -qi "No working init found" "$SERIAL_LOG"; then
        echo "ROOT CAUSE: Kernel cannot find init executable"
        echo
        echo "LIKELY ISSUES:"
        echo "  1. Init path wrong (kernel expects /init, /sbin/init, or init= parameter)"
        echo "  2. Initramfs empty or corrupted"
        echo
        echo "AUTOMATIC FIXES TO APPLY:"
        extract_and_check_initramfs

    elif grep -qi "not syncing" "$SERIAL_LOG"; then
        echo "ROOT CAUSE: Critical kernel subsystem failure"
        echo
        echo "LIKELY ISSUES:"
        echo "  1. Missing critical driver (storage, filesystem)"
        echo "  2. Hardware incompatibility"
        echo
        echo "AUTOMATIC FIXES TO APPLY:"
        echo "  - Check for missing drivers in kernel config"
        check_kernel_drivers
    else
        echo "ROOT CAUSE: Unknown kernel panic"
        echo
        echo "Check the panic message above for clues."
    fi
}

analyze_partition_detection() {
    echo "Installer partition not detected by init script."
    echo
    echo "LIKELY ISSUES:"
    echo "  1. ISO not properly configured as hybrid bootable"
    echo "  2. Partition label PURPLE_INSTALLER missing"
    echo "  3. USB/SATA drivers not loaded (but should be built-in)"
    echo
    echo "CHECKING ISO CONFIGURATION:"

    if command -v isoinfo >/dev/null 2>&1; then
        echo "  Volume ID: $(isoinfo -d -i "$ISO_PATH" | grep "Volume id:" || echo "unknown")"
    fi

    echo
    echo "AUTOMATIC FIXES TO APPLY:"
    echo "  - Rebuild ISO with correct volume label: ./04-build-iso.sh"
    echo "  - Verify xorriso hybrid ISO creation succeeded"
}

analyze_timeout() {
    echo "Boot process did not complete within timeout."
    echo
    echo "CHECKING SERIAL LOG FOR CLUES:"

    if grep -q "Mounting pseudo-filesystems" "$SERIAL_LOG"; then
        echo "  ✓ Init script started"
    else
        echo "  ✗ Init script never started - kernel didn't load initramfs"
    fi

    if grep -q "Waiting for hardware initialization" "$SERIAL_LOG"; then
        echo "  ✓ Hardware enumeration started"
    else
        echo "  ✗ Stuck before hardware enumeration"
    fi

    if grep -q "Detected block devices:" "$SERIAL_LOG"; then
        echo "  ✓ Block device detection ran"
        echo "  Devices found:"
        grep -A 5 "Detected block devices:" "$SERIAL_LOG" | sed 's/^/    /'
    else
        echo "  ✗ No block devices detected"
    fi

    echo
    echo "LAST 20 LINES OF OUTPUT:"
    tail -20 "$SERIAL_LOG"
}

extract_and_check_initramfs() {
    echo "  Extracting initramfs for analysis..."

    local TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" RETURN

    cd "$TEMP_DIR"
    if zcat "$BUILD_DIR/initrd.img" | cpio -i 2>/dev/null; then
        echo "  ✓ Initramfs extracted successfully"

        if [ -f init ]; then
            echo "  ✓ /init exists"
            if [ -x init ]; then
                echo "  ✓ /init is executable"
            else
                error "  ✗ /init is NOT executable - FIX: chmod +x on init before packing"
            fi

            # Check shebang
            SHEBANG=$(head -1 init)
            echo "  Shebang: $SHEBANG"
            if [ "$SHEBANG" = "#!/bin/busybox sh" ]; then
                echo "  ✓ Correct shebang"
            else
                error "  ✗ Wrong shebang - should be #!/bin/busybox sh"
            fi
        else
            error "  ✗ /init NOT FOUND in initramfs"
        fi

        if [ -f bin/busybox ]; then
            echo "  ✓ BusyBox exists at /bin/busybox"
            if ldd bin/busybox 2>&1 | grep -q "not a dynamic executable"; then
                echo "  ✓ BusyBox is statically linked"
            else
                error "  ✗ BusyBox is dynamically linked - FIX: use busybox-static package"
            fi
        else
            error "  ✗ BusyBox NOT FOUND at /bin/busybox"
        fi

        echo "  Directory structure:"
        ls -la | sed 's/^/    /'
    else
        error "  ✗ Failed to extract initramfs - may be corrupted"
    fi
}

check_kernel_drivers() {
    echo "  Checking kernel configuration for critical drivers..."

    local CONFIG="$BUILD_DIR/kernel-config-purple"

    if [ ! -f "$CONFIG" ]; then
        warn "  Kernel config not found at $CONFIG"
        return
    fi

    local CRITICAL=(
        "CONFIG_BLK_DEV"
        "CONFIG_SCSI"
        "CONFIG_BLK_DEV_SD"
        "CONFIG_EXT4_FS"
        "CONFIG_PROC_FS"
        "CONFIG_SYSFS"
        "CONFIG_DEVTMPFS"
    )

    for cfg in "${CRITICAL[@]}"; do
        if grep -q "^${cfg}=y" "$CONFIG"; then
            echo "  ✓ ${cfg}=y"
        else
            error "  ✗ ${cfg} NOT ENABLED - FIX: add to kernel-config-fragment.config"
        fi
    done
}

cleanup() {
    # Clean up temporary target disk
    if [ -n "$TARGET_DISK" ] && [ -f "$TARGET_DISK" ]; then
        rm -f "$TARGET_DISK"
    fi

    if [ $? -eq 0 ] && [ "$KEEP_LOGS" -eq 0 ]; then
        info "Cleaning up successful test logs..."
        rm -f "$LOG_FILE" "$SERIAL_LOG"
    else
        info "Logs preserved for debugging"
    fi
}

main() {
    echo
    echo "=========================================="
    echo "  PurpleOS Automated Boot Test"
    echo "=========================================="
    echo

    check_sudo
    check_qemu
    find_iso
    setup_test_env

    boot_test
    EXIT_CODE=$?

    analyze_logs $EXIT_CODE

    cleanup

    echo
    if [ $EXIT_CODE -eq 0 ]; then
        ok "Boot test PASSED"
        exit 0
    else
        error "Boot test FAILED (exit code: $EXIT_CODE)"
        error "Review analysis in: $ANALYSIS_FILE"
        exit $EXIT_CODE
    fi
}

trap cleanup EXIT
main "$@"
