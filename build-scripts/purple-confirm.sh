#!/bin/bash
# Purple Computer Installer - Gate 2: Runtime User Confirmation
#
# TWO-GATE SAFETY MODEL:
#   Gate 1 (initramfs hook): Sets /run/purple/armed marker
#   Gate 2 (this script): Shows confirmation, requires ENTER to proceed
#
# This script is copied to /run/purple/confirm.sh by the initramfs hook
# and executed by a runtime systemd unit (also created by the hook).
#
# CRITICAL: We do NOT modify squashfs. Everything runs from /run.
#
# UX PRINCIPLES:
# - Minimal words, no jargon, calm tone
# - Warning → Yes/Cancel flow
# - Progress indicator during install
# - Logs hidden by default (debug via tty2)
#
# NEVER blocks silently - always shows what it's waiting for

set -e

# =============================================================================
# CONFIGURATION
# =============================================================================
MARKER_FILE="/run/purple/armed"
INPUT_TIMEOUT=300  # 5 minutes max wait for input
LOG_TAG="[PURPLE]"

# =============================================================================
# LOGGING - loud, always to console
# =============================================================================
log() {
    echo "$LOG_TAG $1"
    echo "$LOG_TAG $1" >/dev/console 2>/dev/null || true
}

log_error() {
    echo "$LOG_TAG ERROR: $1" >&2
    echo "$LOG_TAG ERROR: $1" >/dev/console 2>/dev/null || true
}

# =============================================================================
# CLEANUP AND EXIT HANDLERS
# =============================================================================
cleanup() {
    # Restore terminal settings if we changed them
    stty sane 2>/dev/null || true
}
trap cleanup EXIT

cancel_and_reboot() {
    log "Installation CANCELLED by user"
    echo ""
    echo "Installation cancelled."
    echo ""

    # Check if we're in debug mode
    if grep -q "purple.debug=1" /proc/cmdline 2>/dev/null; then
        log "Debug mode - dropping to shell instead of reboot"
        echo "Debug mode active. Dropping to shell..."
        echo "Type 'reboot' to restart."
        exec /bin/bash
    else
        echo "Rebooting in 5 seconds..."
        sleep 5
        log "Rebooting after cancellation"
        reboot -f || echo b > /proc/sysrq-trigger
    fi
}

input_error_and_reboot() {
    local reason="$1"
    log_error "Input device failure: $reason"
    echo ""
    echo "=========================================="
    echo "  ERROR: Cannot read keyboard input"
    echo "=========================================="
    echo ""
    echo "  Reason: $reason"
    echo ""
    echo "  Please check:"
    echo "    - Keyboard is plugged in"
    echo "    - USB ports are working"
    echo ""
    echo "  Rebooting in 30 seconds..."
    echo ""
    sleep 30
    reboot -f || echo b > /proc/sysrq-trigger
}

# =============================================================================
# GATE 2: CHECK MARKER FROM GATE 1
# =============================================================================
log "=== Purple Computer Installer (Gate 2: User Confirmation) ==="

if [ ! -f "$MARKER_FILE" ]; then
    log "Gate 2: SKIPPED - No marker file ($MARKER_FILE not found)"
    log "This means Gate 1 did not pass or installer is not armed"
    exit 0
fi

log "Gate 2: Marker file found - Gate 1 passed"

# Source the marker file to get payload info
. "$MARKER_FILE"

if [ -z "$PAYLOAD_PATH" ]; then
    log_error "Marker file exists but PAYLOAD_PATH not set"
    exit 1
fi

log "Payload path: $PAYLOAD_PATH"

# Verify payload still exists
if [ ! -x "$PAYLOAD_PATH/install.sh" ]; then
    log_error "Payload not found at $PAYLOAD_PATH/install.sh"
    log_error "The USB drive may have been removed"
    echo ""
    echo "ERROR: Installer payload not found."
    echo "Please ensure the USB drive is still connected."
    echo ""
    echo "Rebooting in 10 seconds..."
    sleep 10
    reboot -f
fi

# =============================================================================
# VERIFY INPUT DEVICES
# =============================================================================
log "Checking input devices..."

# Try to find a working TTY
TTY_DEV=""
for tty in /dev/tty1 /dev/tty0 /dev/console; do
    if [ -c "$tty" ] && [ -w "$tty" ]; then
        TTY_DEV="$tty"
        break
    fi
done

if [ -z "$TTY_DEV" ]; then
    input_error_and_reboot "No writable TTY device found"
fi

log "Using TTY: $TTY_DEV"

# Switch to the TTY
exec <$TTY_DEV >$TTY_DEV 2>&1

# Note: We used to have a keyboard test here, but it was too aggressive.
# Users should just see the confirmation screen and press ENTER when ready.
# If keyboard doesn't work, they'll hit the 5-minute timeout on the main prompt.
log "Input device ready"

# =============================================================================
# DISPLAY CONFIRMATION SCREEN (calm, parent-friendly)
# =============================================================================
clear

# Purple-themed, minimal, calm
echo ""
echo ""
echo ""
echo ""
echo "                    ╔═══════════════════════════════════════════╗"
echo "                    ║                                           ║"
echo "                    ║          Purple Computer Setup            ║"
echo "                    ║                                           ║"
echo "                    ╚═══════════════════════════════════════════╝"
echo ""
echo ""
echo ""
echo "         This will set up Purple Computer on this laptop."
echo ""
echo "         Everything on this computer will be erased."
echo ""
echo ""
echo ""
echo "         ─────────────────────────────────────────────────"
echo ""
echo "              Press ENTER to continue"
echo ""
echo "              Press ESC to cancel"
echo ""
echo "         ─────────────────────────────────────────────────"
echo ""
echo ""

log "Waiting for user input..."

# =============================================================================
# READ USER INPUT
# =============================================================================
# Set terminal to raw mode to catch ESC immediately
stty -echo -icanon min 0 time 0

CONFIRMED=0
CANCELLED=0
WAIT_TIME=0

while [ $WAIT_TIME -lt $INPUT_TIMEOUT ]; do
    # Try to read a character
    char=$(dd bs=1 count=1 2>/dev/null | od -An -tx1 | tr -d ' ')

    case "$char" in
        "0a"|"0d")  # Enter (LF or CR)
            CONFIRMED=1
            break
            ;;
        "1b")  # ESC
            CANCELLED=1
            break
            ;;
        "")
            # No input yet
            sleep 0.5
            WAIT_TIME=$((WAIT_TIME + 1))

            # Show waiting indicator every 30 seconds
            if [ $((WAIT_TIME % 60)) -eq 0 ]; then
                echo "     (Still waiting for input... $((INPUT_TIMEOUT - WAIT_TIME))s remaining)"
            fi
            ;;
        *)
            # Any other key - remind user of options
            echo ""
            echo "     Invalid key. Press ENTER to install, or ESC to cancel."
            echo ""
            ;;
    esac
done

# Restore terminal
stty sane 2>/dev/null || true

# =============================================================================
# HANDLE INPUT RESULT
# =============================================================================
if [ $CANCELLED -eq 1 ]; then
    cancel_and_reboot
fi

if [ $CONFIRMED -ne 1 ]; then
    log "Timeout waiting for user input"
    echo ""
    echo "Timeout: No input received for $INPUT_TIMEOUT seconds."
    echo "Installation cancelled for safety."
    echo ""
    cancel_and_reboot
fi

# =============================================================================
# GATE 2: PASSED - LAUNCH INSTALLER
# =============================================================================
log "Gate 2 PASSED - User confirmed"

# Show progress screen (calm, minimal)
clear
echo ""
echo ""
echo ""
echo ""
echo "                    ╔═══════════════════════════════════════════╗"
echo "                    ║                                           ║"
echo "                    ║          Setting up Purple Computer       ║"
echo "                    ║                                           ║"
echo "                    ╚═══════════════════════════════════════════╝"
echo ""
echo ""
echo ""
echo "         This will take about 10-15 minutes."
echo ""
echo "         Please wait..."
echo ""
echo ""

# Set environment for installer
export PURPLE_PAYLOAD_DIR="$PAYLOAD_PATH"

# Launch the installer (output goes to tty2 for debugging, hidden from user)
log "Executing: $PAYLOAD_PATH/install.sh"

if "$PAYLOAD_PATH/install.sh" >/dev/tty2 2>&1; then
    log "SUCCESS: Installation completed"

    # Show completion screen (calm, minimal)
    clear
    echo ""
    echo ""
    echo ""
    echo ""
    echo "                    ╔═══════════════════════════════════════════╗"
    echo "                    ║                                           ║"
    echo "                    ║               All done!                   ║"
    echo "                    ║                                           ║"
    echo "                    ╚═══════════════════════════════════════════╝"
    echo ""
    echo ""
    echo ""
    echo "         Remove the USB drive."
    echo ""
    echo "         Press ENTER to restart."
    echo ""
    echo ""

    read -t 60 _ 2>/dev/null || true
    log "Rebooting"
    reboot -f || echo b > /proc/sysrq-trigger
else
    EXIT_CODE=$?
    log "FAILED: Installation error (exit $EXIT_CODE)"

    # Show error screen (still calm, offer debug)
    clear
    echo ""
    echo ""
    echo ""
    echo ""
    echo "                    ╔═══════════════════════════════════════════╗"
    echo "                    ║                                           ║"
    echo "                    ║          Something went wrong             ║"
    echo "                    ║                                           ║"
    echo "                    ╚═══════════════════════════════════════════╝"
    echo ""
    echo ""
    echo ""
    echo "         Setup could not be completed."
    echo ""
    echo "         Press ENTER to restart and try again."
    echo ""
    echo "         (Press Alt+F2 for technical details)"
    echo ""
    echo ""

    read -t 60 _ 2>/dev/null || true
    reboot -f || echo b > /proc/sysrq-trigger
fi
