#!/bin/bash
# Boot timing and pre-kernel I/O evidence, in one command.
#
# Motivating case: a MacBook5,2 that takes ~5 minutes to reach Purple while
# systemd reports a 28s boot. Everything Linux can see is fast, so the time is
# spent before the kernel's clock starts (firmware, GRUB, EFI stub) reading the
# kernel and initrd off the internal disk. Linux cannot time that window, but it
# can measure the two things that would explain it: how fast the disk serves
# small seeking reads (GRUB's access pattern), and how scattered the files are.
#
# See docs/PLAN-macbook5-slow-boot.md.
#
# Usage:
#   purple-boot-timing              # report
#   purple-boot-timing --menu on    # show the GRUB menu (10s) on next boot
#   purple-boot-timing --menu off   # back to a hidden, immediate boot

set -u

GRUB_CFG=/boot/grub/grub.cfg

section() { printf '\n=== %s ===\n' "$1"; }

grub_menu() {
    [ -w "$GRUB_CFG" ] || { echo "need root: sudo purple-boot-timing --menu $1"; exit 1; }
    case "$1" in
        on)
            sed -i -e 's/^set timeout=.*/set timeout=10/' \
                   -e '/^set timeout_style=/d' \
                   -e '/^set timeout=/a set timeout_style=menu' "$GRUB_CFG"
            echo "GRUB menu on (10s). Reboot and watch which side of the menu the wait is on:"
            echo "  menu appears fast, then a long wait  -> GRUB/stub reading the disk"
            echo "  long wait before the menu appears    -> Apple firmware, before GRUB"
            ;;
        off)
            sed -i -e 's/^set timeout=.*/set timeout=0/' \
                   -e '/^set timeout_style=/d' "$GRUB_CFG"
            echo "GRUB menu off (timeout=0)."
            ;;
        *) echo "usage: purple-boot-timing --menu on|off"; exit 1 ;;
    esac
    grep -E '^set timeout' "$GRUB_CFG"
}

if [ "${1:-}" = "--menu" ]; then grub_menu "${2:-}"; exit 0; fi

section "Boot phases (what Linux can see)"
systemd-analyze 2>&1 | head -3
printf 'uptime now: %s s\n' "$(cut -d' ' -f1 /proc/uptime)"
echo
echo "If the wall-clock wait was much longer than the total above, the extra time"
echo "is pre-kernel: firmware + GRUB + EFI stub. Read uptime AT FIRST PAINT to confirm."

section "Time to first paint (from boot.log)"
LOG=/var/log/purple/boot.log
[ -f "$LOG" ] || LOG=/tmp/purple-boot.log
if [ -f "$LOG" ]; then
    head -1 "$LOG"
    grep -m1 'first render reached' "$LOG" || tail -1 "$LOG"
else
    echo "no boot log at /var/log/purple/boot.log"
fi

section "What the firmware has to read before Linux starts"
# The image ships /boot/vmlinuz symlinks, but a machine booting versioned
# names only must still report something rather than a pile of ls errors.
KERNEL=$(ls -1 /boot/vmlinuz /boot/vmlinuz-* 2>/dev/null | head -1)
INITRD=$(ls -1 /boot/initrd.img /boot/initrd.img-* 2>/dev/null | head -1)
if [ -n "$KERNEL" ] && [ -n "$INITRD" ]; then
    ls -lL "$KERNEL" "$INITRD"
else
    echo "no kernel/initrd found under /boot"
fi
BOOT_DEV=$(findmnt -no SOURCE /boot 2>/dev/null || findmnt -no SOURCE / 2>/dev/null)
echo "read from: $BOOT_DEV ($(findmnt -no FSTYPE /boot 2>/dev/null || findmnt -no FSTYPE / 2>/dev/null))"
if ! command -v filefrag >/dev/null 2>&1; then
    echo "filefrag not installed (skipping fragmentation check)"
elif [ -n "$KERNEL" ] && [ -n "$INITRD" ]; then
    # Extent count is the proxy for GRUB's seek load: one extent is a single
    # sequential run, hundreds means the firmware seeks for every chunk.
    filefrag "$KERNEL" "$INITRD" 2>&1
fi

# Never guess the disk: measuring an unrelated drive would send the whole
# investigation the wrong way.
DISK=$(lsblk -no PKNAME "$BOOT_DEV" 2>/dev/null | head -1)
if [ -z "${DISK:-}" ]; then
    echo "could not identify the disk behind $BOOT_DEV; skipping disk tests"
    echo "run the disk tests by hand against the right device if needed"
    exit 0
fi

section "Disk: sequential read (/dev/$DISK)"
if [ "$(id -u)" -ne 0 ]; then
    echo "run with sudo for the disk tests"
else
    dd if="/dev/$DISK" of=/dev/null bs=1M count=300 iflag=direct 2>&1 | tail -1
    echo "healthy 2009-era laptop drive: 40-60 MB/s. single digits means the drive is the problem."

    section "Disk: small seeking reads (what GRUB actually does)"
    # 200 x 4KB reads at random offsets. GRUB reads ext4 metadata and file
    # data in small blocks with no readahead, so per-seek latency, not
    # throughput, is what turns a 76MB load into minutes.
    SIZE_MB=$(( $(blockdev --getsize64 "/dev/$DISK") / 1048576 ))
    START=$(date +%s.%N)
    i=0
    while [ "$i" -lt 200 ]; do
        dd if="/dev/$DISK" of=/dev/null bs=4k count=1 iflag=direct \
           skip=$(( (RANDOM * 32768 + RANDOM) % (SIZE_MB * 256) )) 2>/dev/null
        i=$((i + 1))
    done
    END=$(date +%s.%N)
    awk -v s="$START" -v e="$END" 'BEGIN {
        printf "200 random 4K reads in %.1fs = %.1f ms per read\n", e-s, (e-s)*1000/200 }'
    echo "healthy: 10-20 ms. above ~50 ms means seeks are the bottleneck and"
    echo "staging vmlinuz+initrd on the FAT ESP (contiguous, sequential) should help."

    section "SMART"
    if command -v smartctl >/dev/null 2>&1; then
        smartctl -H "/dev/$DISK" 2>&1 | tail -3
        smartctl -A "/dev/$DISK" 2>&1 | grep -Ei 'reallocated|pending|uncorrect|seek_error|spin_retry' || true
    else
        echo "smartctl not installed"
    fi
fi

section "Next step"
echo "sudo purple-boot-timing --menu on   # split firmware time from GRUB time"
