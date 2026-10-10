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
# On a live USB boot the report fits one photo: stick link speed, systemd's
# view, the startup timeline in seconds since the kernel started (X allowed,
# X up, squashfs cache read, python, first paint), memory, stick read speed.
#
# Usage:
#   purple-boot-timing              # report
#   purple-boot-timing --timeline   # just the startup timeline from the boot log
#   purple-boot-timing --menu on    # show the GRUB menu (10s) on next boot
#   purple-boot-timing --menu off   # back to a hidden, immediate boot

set -u

# The same config lives in both places: UEFI reads the ESP copy, BIOS the root one.
GRUB_CFGS="/boot/grub/grub.cfg /boot/efi/EFI/ubuntu/grub.cfg"
STUB_INFO=/sys/firmware/efi/efivars/StubInfo-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f
UKI=/boot/efi/EFI/purple/purple.efi

section() { printf '\n=== %s ===\n' "$1"; }

# Boot-log lines that bound each startup phase, as seconds since the kernel
# started. The log carries wall-clock stamps; "now minus uptime" is when the
# kernel's clock began, so anything before that (firmware, GRUB) is invisible.
timeline() {
    local log=${PURPLE_BOOT_LOG:-/tmp/purple-boot.log}
    [ -f "$log" ] || log=/var/log/purple/boot.log
    [ -f "$log" ] || { echo "no boot log at /tmp/purple-boot.log"; return; }
    local boot_hms
    boot_hms=$(date -d "@$(( $(date +%s) - $(cut -d. -f1 /proc/uptime) ))" +%H:%M:%S)
    grep -E 'wait-display\] (===|Display ready|No connected)|xinitrc\] (=== |matchbox|Launching)|usb-cache\] |launcher\] exec|\[python\] (watchdog armed|all purple_tui|PurpleApp|main loop|first render|WATCHDOG|mixer)' "$log" |
    awk -v boot="$boot_hms" '
        function secs(t,  a) { split(t, a, ":"); return a[1] * 3600 + a[2] * 60 + a[3] }
        BEGIN { b = secs(boot) }
        { d = secs(substr($1, 2, 12)) - b; if (d < -43200) d += 86400
          sub(/^\[[^]]*\] (\[\+[^]]*\] )?/, "")
          printf "%7.1fs  %.68s\n", d, $0 }'
}

# The disk the live squashfs is read from, and the link speed of the USB
# device behind it (the `speed` file sits on the USB device node, a few
# levels above the SCSI device the block layer points at).
live_disk() {
    local dev
    dev=$(findmnt -no SOURCE /cdrom 2>/dev/null)
    [ -n "$dev" ] || dev=$(. /run/purple-live.conf 2>/dev/null; findmnt -no SOURCE -T "${SQUASHFS:-/nonexistent}" 2>/dev/null)
    [ -n "$dev" ] || return 1
    lsblk -no PKNAME "$dev" 2>/dev/null | head -1 | grep . || basename "$dev"
}
usb_speed() {
    local node
    node=$(readlink -f "/sys/block/$1/device" 2>/dev/null)
    while [ -n "$node" ] && [ ! -f "$node/speed" ]; do node=${node%/*}; done
    [ -n "$node" ] || { echo "not a USB device"; return; }
    case "$(cat "$node/speed")" in
        12|1.5) echo "12 Mb/s: USB 1.1 FALLBACK, ~1 MB/s, every read of the stick is 20-30x slower than it should be" ;;
        480) echo "480 Mb/s (high-speed, normal for a USB 2.0 port)" ;;
        *) echo "$(cat "$node/speed") Mb/s (SuperSpeed)" ;;
    esac
}

grub_menu() {
    [ -w /boot/grub/grub.cfg ] || { echo "need root: sudo purple-boot-timing --menu $1"; exit 1; }
    for cfg in $GRUB_CFGS; do
        [ -f "$cfg" ] || continue
        case "$1" in
            on)
                sed -i -e 's/^set timeout=.*/set timeout=10/' \
                       -e '/^set timeout_style=/d' \
                       -e '/^set timeout=/a set timeout_style=menu' "$cfg"
                ;;
            off)
                sed -i -e 's/^set timeout=.*/set timeout=0/' \
                       -e '/^set timeout_style=/d' "$cfg"
                ;;
            *) echo "usage: purple-boot-timing --menu on|off"; exit 1 ;;
        esac
        printf '%s: ' "$cfg"; grep -E '^set timeout' "$cfg" | tr '\n' ' '; echo
    done
    case "$1" in
        on)
            echo "GRUB menu on (10s). Reboot and watch which side of the menu the wait is on:"
            echo "  menu appears fast, then a long wait  -> GRUB/stub reading the disk"
            echo "  long wait before the menu appears    -> Apple firmware, before GRUB"
            [ -e "$STUB_INFO" ] && echo "this Mac boots the UKI, not GRUB: hold Option at power-on and pick EFI Boot to see the menu"
            ;;
        off) echo "GRUB menu off (timeout=0)." ;;
    esac
}

if [ "${1:-}" = "--menu" ]; then grub_menu "${2:-}"; exit 0; fi
if [ "${1:-}" = "--timeline" ]; then timeline; exit 0; fi

section "Boot path"
LIVE_DISK=""
if grep -qE '(^| )boot=(casper|purple-live)( |$)' /proc/cmdline 2>/dev/null; then
    LIVE_DISK=$(live_disk || true)
    echo "Live USB: /dev/${LIVE_DISK:-?} at $(usb_speed "$LIVE_DISK")"
elif [ -e "$STUB_INFO" ]; then
    echo "UKI: the firmware loaded $UKI itself (no shim, no GRUB)"
elif [ -d /sys/firmware/efi ]; then
    echo "UEFI: shim -> GRUB -> kernel"
else
    echo "BIOS: MBR -> GRUB -> kernel"
fi

section "Boot phases (what Linux can see)"
systemd-analyze 2>&1 | head -3
printf 'uptime now: %s s\n' "$(cut -d' ' -f1 /proc/uptime)"
echo
echo "If the wall-clock wait was much longer than the total above, the extra time"
echo "is pre-kernel: firmware + GRUB + EFI stub. Read uptime AT FIRST PAINT to confirm."

section "Startup timeline (seconds since the kernel started)"
timeline

if [ -n "$LIVE_DISK" ]; then
    section "Memory"
    awk '/^(MemTotal|MemAvailable):/ {printf "%s %d MB  ", $1, $2 / 1024}' /proc/meminfo; echo
    echo "purple-usb-cache reads the whole squashfs (~1GB) once X starts, at idle disk priority,"
    echo "and locks it in RAM when there is room. The Caching -> USB safe window above is how"
    echo "long the stick was busy with it."

    section "Stick: sequential read (/dev/$LIVE_DISK)"
    if [ "$(id -u)" -ne 0 ]; then
        echo "run with sudo for the read test"
    else
        timeout -s INT 15 dd if="/dev/$LIVE_DISK" of=/dev/null bs=1M count=64 iflag=direct 2>&1 | tail -1
        echo "USB 2.0 stick: 20-35 MB/s. single digits means the stick or the port is the problem."
    fi
    exit 0
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
[ -f "$UKI" ] && ls -lL "$UKI"
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
