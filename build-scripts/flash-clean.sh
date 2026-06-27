#!/usr/bin/env bash
# Refresh udev's view of USB drives after an aborted/ejected flash.
#
# Aborting a write and ejecting (or the post-flash udisksctl power-off) tears
# the device down. Re-plugging makes the kernel reuse the sdX name but it never
# re-runs udev rules for the new occupant, so lsblk/by-id and flash-to-usb.sh's
# whitelist matcher keep describing the *previous* stick and the new drive is
# silently unmatched. Re-trigger udev and settle so reality is reflected again.
#
# Read-only: this only re-runs udev rules, it never writes to any drive.

set -eo pipefail

GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

# Aborting a flash mid-write can wedge systemd-udevd's event queue. While it's
# stuck, udev keeps serving the *previous* occupant's identity (model/serial)
# for a re-used sdX name, and no amount of `udevadm trigger` or even a full USB
# re-enumeration updates it: the daemon never processes the events. Restarting
# udevd clears the stuck workers; only then does re-triggering take effect.
log_info "Restarting systemd-udevd to clear any wedged event queue..."
sudo systemctl restart systemd-udevd
sleep 1

triggered=0
for dev in /sys/block/sd*; do
    [[ -e "$dev" ]] || continue
    name="$(basename "$dev")"
    sudo udevadm trigger --action=change "/dev/$name" 2>/dev/null || true
    triggered=$((triggered + 1))
done

# Bounded settle: udevadm settle waits on the *whole-system* uevent queue, so a
# drive that's still bouncing can otherwise wedge it for the full 120s default.
if ! sudo udevadm settle --timeout=10; then
    echo -e "${YELLOW}[WARN]${NC} udev did not settle in 10s; a drive may still be"
    echo "       re-enumerating. Physically unplug and re-plug it, then retry."
fi

log_info "Restarted udevd and re-triggered $triggered USB block device(s)."
echo ""
lsblk -d -n -o NAME,SIZE,TRAN,VENDOR,MODEL,SERIAL 2>/dev/null | awk '$3 == "usb"'
echo ""
log_info "Now re-run 'just flash'."
