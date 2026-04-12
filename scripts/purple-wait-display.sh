#!/bin/sh
# Wait for a display to be connected before starting X11.
#
# The i915 GPU driver loads asynchronously: the DRM device node (/dev/dri/card0)
# appears before display connectors are fully initialized. Starting X11 too
# early can result in a black screen or backlight failure, especially on older
# hardware (MacBook 2014 Haswell, some ThinkPads).
#
# This script polls /sys/class/drm/ for a connected display connector.
# It's meant to run as ExecStartPre in the purple-x11 systemd service.
#
# Boot logging is ALWAYS on (not gated on debug flag): these timestamps are
# the only evidence we have when a customer reports a slow or hung live boot.

BOOT_LOG_TMP=/tmp/purple-boot.log
BOOT_LOG_PERSIST=/var/log/purple/boot.log
MAX_WAIT=15

# Ensure persistent log dir exists. On the standard ISO /var/log is tmpfs so
# this is effectively write-to-tmpfs; on the debug ISO /var/log is on the
# casper "writable" ext4 partition, so this survives reboot.
mkdir -p /var/log/purple 2>/dev/null || true

log() {
    local msg="[$(date '+%H:%M:%S.%3N')] [wait-display] $1"
    echo "$msg" >> "$BOOT_LOG_TMP" 2>/dev/null || true
    echo "$msg" >> "$BOOT_LOG_PERSIST" 2>/dev/null || true
    logger -t purple-boot -- "$msg" 2>/dev/null || true
}

# Check if any DRM connector reports "connected"
check_connected() {
    for status_file in /sys/class/drm/card*-*/status; do
        [ -f "$status_file" ] || continue
        if [ "$(cat "$status_file" 2>/dev/null)" = "connected" ]; then
            echo "$status_file"
            return 0
        fi
    done
    return 1
}

# Simulate X11 failure for testing the diagnostic error screen.
# Triggered by purple.failx11=1 kernel parameter (debug ISO GRUB menu).
# Failing here (ExecStartPre) prevents X from starting at all, so the service
# hits its restart limit quickly and ExecStopPost shows the error screen.
if grep -q "purple.failx11=1" /proc/cmdline 2>/dev/null; then
    log "purple.failx11=1 set, failing ExecStartPre to trigger error screen"
    exit 1
fi

log "=== purple-wait-display started === kernel=$(uname -r)"
log "Waiting for display (up to ${MAX_WAIT}s)..."

# Enumerate connectors once for diagnostics
for f in /sys/class/drm/card*-*/status; do
    [ -f "$f" ] || continue
    log "  connector at start: $(echo "$f" | sed 's|.*/drm/||; s|/status||') = $(cat "$f" 2>/dev/null)"
done

waited=0
while [ "$waited" -lt "$MAX_WAIT" ]; do
    found=$(check_connected)
    if [ -n "$found" ]; then
        connector=$(echo "$found" | sed 's|.*/drm/||; s|/status||')
        log "Display ready: $connector (waited ${waited} half-seconds = $((waited / 2)).$((waited % 2 * 5))s)"
        exit 0
    fi
    sleep 0.5
    waited=$((waited + 1))
done

# Timeout: proceed anyway. Some hardware (VMs, unusual panels) may not report
# connector status through sysfs but still work fine with X11.
log "No connected display found after ${MAX_WAIT}s, proceeding anyway"
for f in /sys/class/drm/card*-*/status; do
    [ -f "$f" ] || continue
    log "  connector at timeout: $(echo "$f" | sed 's|.*/drm/||; s|/status||') = $(cat "$f" 2>/dev/null)"
done
exit 0
