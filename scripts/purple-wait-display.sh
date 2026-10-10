#!/bin/sh
# Wait for a real GPU to report a connected display before starting X11.
# Runs as ExecStartPre in purple-x11.service.
#
# GPU drivers load from the root filesystem (not the initrd), so X can be queued
# while the firmware framebuffer (simpledrm) is still card0; X that opens it dies
# with "no screens found" when the driver replaces it (HP Stream). The driver
# removes that framebuffer before registering its card, and connector status is
# only filled in after its initial probe (the 2014 MacBook black screen), so the
# wait ends once no firmware framebuffer is left and a real GPU reports a
# connected connector.
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

# Rotate boot.log -> boot.log.prev ONCE per real (kernel) boot.
#
# Three restart layers can re-enter this script and each would double-rotate
# and lose information if we rotated unconditionally:
#   1. Purple-internal restart: xinitrc does `exec "$0"` on every Purple exit.
#      (Handled: xinitrc does not rotate at all; only this script does.)
#   2. purple-x11.service restart: Restart=on-failure + StartLimitBurst=3
#      means this ExecStartPre runs up to 3 times per boot. We must not
#      rotate on attempts 2 and 3 or we lose attempt 1's log, which is
#      usually the most interesting one when diagnosing a hang.
#   3. Actual kernel reboot: rotate exactly once, moving the previous boot's
#      accumulated log to .prev.
#
# /proc/sys/kernel/random/boot_id is a unique 128-bit value per kernel boot.
# We stash the current boot_id in a sibling file; we only rotate when the
# stored id differs from the current one (or there's no stored id yet).
BOOT_ID_FILE=/var/log/purple/boot_id
CURRENT_BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "unknown")
STORED_BOOT_ID=$(cat "$BOOT_ID_FILE" 2>/dev/null || echo "")
if [ "$CURRENT_BOOT_ID" != "$STORED_BOOT_ID" ]; then
    for f in "$BOOT_LOG_PERSIST" /var/log/purple/power.log /var/log/purple/evdev.log; do
        if [ -f "$f" ]; then
            mv -f "$f" "${f}.prev" 2>/dev/null || true
        fi
    done
    echo "$CURRENT_BOOT_ID" > "$BOOT_ID_FILE" 2>/dev/null || true
fi

log() {
    local msg="[$(date '+%H:%M:%S.%3N')] [wait-display] $1"
    echo "$msg" >> "$BOOT_LOG_TMP" 2>/dev/null || true
    echo "$msg" >> "$BOOT_LOG_PERSIST" 2>/dev/null || true
    logger -t purple-boot -- "$msg" 2>/dev/null || true
}

# gpu: the card sits on a PCI display-class device, or is an SoC GPU (a
# platform device, e.g. Raspberry Pi vc4). firmware: the firmware framebuffer
# (simpledrm), which the primary GPU's driver removes. other: e.g. a USB
# display such as the T2 Touch Bar (appletbdrm).
card_kind() {
    local dir
    dir=$(readlink -f "/sys/class/drm/$1/device")
    case "$dir" in /sys/devices/platform/*)
        case "$(basename "$(readlink -f "$dir/driver")")" in
            simple-framebuffer|simpledrm|ofdrm) echo firmware ;;
            *) echo gpu ;;
        esac
        return ;;
    esac
    while [ -n "$dir" ] && [ "$dir" != /sys/devices ]; do
        case "$(cat "$dir/class" 2>/dev/null)" in 0x03*) echo gpu; return ;; esac
        dir=${dir%/*}
    done
    echo other
}

# Print "name status kind" for each DRM connector
connectors() {
    local f name st kind
    for f in /sys/class/drm/card*-*/status; do
        [ -f "$f" ] || continue
        name=${f%/status}; name=${name##*/}
        st=$(cat "$f" 2>/dev/null)
        kind=$(card_kind "${name%%-*}")
        echo "$name ${st:-unreadable} $kind"
    done
}

# Print the first connected connector on a real GPU, once the firmware
# framebuffer is gone. On dual-GPU laptops the other GPU can finish first.
find_connected() {
    local list
    list=$(connectors)
    case "$list" in *" firmware"*) return 1 ;; esac
    echo "$list" | while read -r name st kind; do
        [ "$st $kind" = "connected gpu" ] && echo "$name" && break
    done
}

log_connectors() {
    connectors | while read -r name st kind; do
        log "  connector at $1: $name = $st ($kind)"
    done
}

# Simulate X11 failure for testing the diagnostic error screen.
# Triggered by purple.failx11=1 kernel parameter (debug ISO GRUB menu).
# Failing here (ExecStartPre) prevents X from starting at all, so the service
# hits its restart limit quickly and OnFailure= shows the error screen.
if grep -q "purple.failx11=1" /proc/cmdline 2>/dev/null; then
    log "purple.failx11=1 set, failing ExecStartPre to trigger error screen"
    exit 1
fi

log "=== purple-wait-display started === kernel=$(uname -r)"
log "Waiting for display (up to ${MAX_WAIT}s)..."

log_connectors start

waited=0
while [ "$waited" -lt $((MAX_WAIT * 2)) ]; do
    connector=$(find_connected)
    if [ -n "$connector" ]; then
        log "Display ready: $connector (waited ${waited} half-seconds = $((waited / 2)).$((waited % 2 * 5))s)"
        exit 0
    fi
    sleep 0.5
    waited=$((waited + 1))
done

# Timeout: proceed anyway. A GPU with no kernel driver leaves only the firmware
# framebuffer, which X can still drive.
log "No connected display found after ${MAX_WAIT}s, proceeding anyway"
log_connectors timeout
exit 0
