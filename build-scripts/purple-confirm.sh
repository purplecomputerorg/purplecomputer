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

# =============================================================================
# REBOOT / POWEROFF - suppress Casper's shutdown prompt
# =============================================================================
# Casper's casper-stop hook shows a "remove media, press enter" prompt on
# shutdown/reboot that hangs if the USB is removed. Three layers of defense:
#   1. /run/casper-no-prompt marker file (tells casper-stop to skip prompt)
#   2. casper-stop neutered at ISO build time (01-remaster-iso.sh)
#   3. sysrq fallback (direct kernel reboot/poweroff, bypasses everything)
suppress_casper_prompt() {
    touch /run/casper-no-prompt 2>/dev/null || true
}

do_reboot() {
    log "Rebooting now"
    suppress_casper_prompt
    ( sync ) & sleep 1  # Best-effort flush, don't wait
    systemctl reboot 2>/dev/null
    sleep 3
    # Fallback: sysrq direct kernel reboot
    echo 1 > /proc/sys/kernel/sysrq 2>/dev/null
    echo b > /proc/sysrq-trigger 2>/dev/null
    sleep 30
}

do_poweroff() {
    log "Powering off now"
    suppress_casper_prompt
    ( sync ) & sleep 1
    systemctl poweroff 2>/dev/null
    sleep 3
    echo 1 > /proc/sys/kernel/sysrq 2>/dev/null
    echo o > /proc/sysrq-trigger 2>/dev/null
    sleep 30
}

countdown_poweroff() {
    local seconds="${1:-30}"
    log "Countdown poweroff: ${seconds}s"
    # Hard watchdog in case countdown or poweroff hangs
    ( sleep $((seconds + 10)); echo 1 > /proc/sys/kernel/sysrq 2>/dev/null; echo o > /proc/sysrq-trigger 2>/dev/null ) &
    while [ "$seconds" -gt 0 ]; do
        printf "\r         Powering off in %2d seconds...  " "$seconds"
        sleep 1
        seconds=$((seconds - 1))
    done
    echo ""
    do_poweroff
}

cancel_and_poweroff() {
    log "Installation CANCELLED by user"
    echo ""
    echo "Installation cancelled."
    echo ""

    # Check if we're in debug mode
    if grep -q "purple.debug=1" /proc/cmdline 2>/dev/null; then
        log "Debug mode - dropping to shell instead of poweroff"
        echo "Debug mode active. Dropping to shell..."
        echo "Type 'poweroff' to shut down."
        exec /bin/bash
    else
        countdown_poweroff 5
    fi
}

input_error_and_poweroff() {
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
    echo ""
    countdown_poweroff 30
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
    countdown_poweroff 10
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
    input_error_and_poweroff "No writable TTY device found"
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
# Use bash read -n 1 instead of dd|od pipeline (simpler, more reliable).
# read -n 1 returns empty string for Enter (it's the delimiter).
# ESC is $'\e'. read -t 1 gives us a 1-second poll interval.
stty -echo 2>/dev/null || true

CONFIRMED=0
CANCELLED=0
WAIT_TIME=0

while [ $WAIT_TIME -lt $INPUT_TIMEOUT ]; do
    if read -n 1 -t 1 key 2>/dev/null; then
        case "$key" in
            "")  # Enter (read -n 1 returns empty for the delimiter)
                CONFIRMED=1
                break
                ;;
            $'\e')  # ESC
                CANCELLED=1
                break
                ;;
            *)
                echo ""
                echo "     Press ENTER to install, or ESC to cancel."
                echo ""
                ;;
        esac
    else
        # read timed out (1 second), no input
        WAIT_TIME=$((WAIT_TIME + 1))

        # Show waiting indicator every 60 seconds
        if [ $((WAIT_TIME % 60)) -eq 0 ] && [ $WAIT_TIME -gt 0 ]; then
            echo "     (Still waiting... $((INPUT_TIMEOUT - WAIT_TIME))s remaining)"
        fi
    fi
done

# Restore terminal
stty sane 2>/dev/null || true

# =============================================================================
# HANDLE INPUT RESULT
# =============================================================================
if [ $CANCELLED -eq 1 ]; then
    cancel_and_poweroff
fi

if [ $CONFIRMED -ne 1 ]; then
    log "Timeout waiting for user input"
    echo ""
    echo "Timeout: No input received for $INPUT_TIMEOUT seconds."
    echo "Installation cancelled for safety."
    echo ""
    cancel_and_poweroff
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
    echo "         Purple Computer is installed!"
    echo ""
    echo "         You don't need the USB drive plugged in anymore."
    echo ""
    echo "         Press ENTER to restart."
    echo ""
    echo ""

    log "Waiting for user to press ENTER..."
    # Wait for ENTER (with timeout so it doesn't sit forever if abandoned).
    # If USB is still in, BIOS may boot the live USB again instead of the
    # installed system. That's fine: they'll just see Purple Computer
    # running from USB, and can remove it and reboot whenever.
    read -t "$INPUT_TIMEOUT" _ 2>/dev/null || true

    do_reboot
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
    echo "         Contact tavi@purplecomputer.org for help."
    echo ""
    echo "         (Press Alt+F2 for technical details)"
    echo ""
    echo ""

    countdown_poweroff 60
fi
