#!/bin/bash
# Purple Computer: periodic boot diagnostic dump to the USB stick's FAT partition.
#
# Rewrites PURPLE-LOG.TXT on the stick's PURPLEUSB partition (plain FAT, so
# Windows and macOS mount it like a thumb drive) every few seconds during boot, then once a minute. A
# customer whose boot hangs holds the power button, plugs the stick into their
# own computer and emails the file. The FAT partition is mounted only for the
# duration of each write so a power cut between writes leaves it clean.
#
# Read-only apart from that one file. Runs as root (dmesg, journal).
set +e

INTERVAL_FAST=5
FAST_UNTIL_UPTIME=300
INTERVAL_SLOW=60
WORK=/run/purple-diag
MNT=$WORK/efi
NAME=PURPLE-LOG.TXT
LOCAL_COPY=/var/log/purple/diag.txt

section() { echo; echo "===== $* ====="; }

stick_log_partition() {
    blkid -L PURPLEUSB 2>/dev/null | grep .
}

collect() {
    echo "purple-diag-dump $(date -Iseconds) uptime=$(cut -d' ' -f1 /proc/uptime)s"
    echo "uname: $(uname -a)"
    echo "machine: $(cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/product_name /sys/class/dmi/id/product_version 2>/dev/null | tr '\n' ' ')"
    echo "bios: $(cat /sys/class/dmi/id/bios_vendor /sys/class/dmi/id/bios_version /sys/class/dmi/id/bios_date 2>/dev/null | tr '\n' ' ')"
    echo "cmdline: $(cat /proc/cmdline)"
    echo "build: $(cat /etc/purple-version 2>/dev/null || echo unknown)"

    section "memory"
    grep -E '^(MemTotal|MemAvailable|SwapTotal)' /proc/meminfo

    section "DRM connectors"
    for f in /sys/class/drm/card*-*/status; do
        [ -f "$f" ] && echo "  ${f#/sys/class/drm/}: $(cat "$f" 2>/dev/null)  enabled=$(cat "${f%/status}/enabled" 2>/dev/null)"
    done
    ls -l /dev/dri/ 2>&1

    section "PCI devices"
    for d in /sys/bus/pci/devices/*; do
        echo "  ${d##*/} class=$(cat "$d/class") $(cat "$d/vendor"):$(cat "$d/device") driver=$(basename "$(readlink "$d/driver" 2>/dev/null)" 2>/dev/null)"
    done

    section "systemd: failed units and pending jobs"
    systemctl list-units --failed --no-pager --no-legend 2>&1
    systemctl list-jobs --no-pager --no-legend 2>&1
    section "systemd: purple-x11"
    systemctl status purple-x11 --no-pager -l 2>&1 | head -40

    section "processes (wchan shows what a stuck process waits on)"
    ps -eo pid,ppid,stat,etimes,wchan:28,args --sort=pid 2>&1

    section "boot log"
    cat /tmp/purple-boot.log 2>/dev/null
    section "xinitrc log"
    tail -60 /tmp/xinitrc.log 2>/dev/null
    section "Xorg log (tail)"
    tail -60 /home/purple/.local/share/xorg/Xorg.0.log /var/log/Xorg.0.log 2>/dev/null
    section "power log"
    cat /tmp/purple-power.log 2>/dev/null

    section "journal (tail)"
    journalctl -b --no-pager -n 800 2>&1

    section "dmesg (tail)"
    dmesg 2>&1 | tail -n 4000

    section "end"
}

write_to_stick() {
    local part=$1 file=$2
    mkdir -p "$MNT"
    mount -t vfat -o rw,noatime "$part" "$MNT" 2>/dev/null || return 1
    cp -f "$file" "$MNT/$NAME.tmp" && mv -f "$MNT/$NAME.tmp" "$MNT/$NAME"
    umount "$MNT" 2>/dev/null || umount -l "$MNT" 2>/dev/null
}

mkdir -p "$WORK" /var/log/purple
while :; do
    collect > "$WORK/dump.txt" 2>&1
    cp -f "$WORK/dump.txt" "$LOCAL_COPY" 2>/dev/null
    part=$(stick_log_partition) && write_to_stick "$part" "$WORK/dump.txt"
    up=$(cut -d. -f1 /proc/uptime)
    [ "$up" -lt "$FAST_UNTIL_UPTIME" ] && sleep "$INTERVAL_FAST" || sleep "$INTERVAL_SLOW"
done
