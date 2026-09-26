#!/bin/bash
# Purple Computer: the boot diagnostic report, printed to stdout.
#
# purple-stick-log runs this every few seconds during boot, less often once
# Purple is up, and writes the text in place into PURPLE-LOG on the stick's
# PURPLEUSB partition (plain FAT, so Windows and macOS mount it like a thumb
# drive). A customer whose boot hangs holds the power button, plugs the stick
# into their own computer and emails the file. Read-only. Runs as root.
set +e

section() { echo; echo "===== $* ====="; }

collect() {
    echo "purple-boot-report $(date -Iseconds) uptime=$(cut -d' ' -f1 /proc/uptime)s"
    echo "uname: $(uname -a)"
    echo "machine: $(cat /sys/class/dmi/id/sys_vendor /sys/class/dmi/id/product_name /sys/class/dmi/id/product_version 2>/dev/null | tr '\n' ' ')"
    echo "bios: $(cat /sys/class/dmi/id/bios_vendor /sys/class/dmi/id/bios_version /sys/class/dmi/id/bios_date 2>/dev/null | tr '\n' ' ')"
    echo "cmdline: $(cat /proc/cmdline)"
    echo "build: $(cat /etc/purple-version 2>/dev/null || echo unknown)"
    echo "debug mode: $([ -e /opt/purple/debug ] && echo on || echo off), P held at start: $([ -e /run/purple/debug-key ] && echo yes || echo no)"

    section "memory"
    grep -E '^(MemTotal|MemAvailable|SwapTotal|Mlocked)' /proc/meminfo
    # dio=0: the system image is read through the page cache that purple-usb-cache locks
    grep -H . /sys/block/loop*/loop/backing_file /sys/block/loop*/loop/dio 2>/dev/null

    section "DRM connectors"
    for f in /sys/class/drm/card*-*/status; do
        [ -f "$f" ] && echo "  ${f#/sys/class/drm/}: $(cat "$f" 2>/dev/null)  enabled=$(cat "${f%/status}/enabled" 2>/dev/null)"
    done
    ls -l /dev/dri/ 2>&1

    section "PCI devices"
    # Builtins only (read, cd -P in one subshell): this runs every few seconds during boot.
    (for d in /sys/bus/pci/devices/*; do
        read -r class < "$d/class"; read -r vendor < "$d/vendor"; read -r device < "$d/device"
        driver=; cd -P "$d/driver" 2>/dev/null && driver=${PWD##*/}
        echo "  ${d##*/} class=$class $vendor:$device driver=$driver"
    done)

    section "systemd: failed units and pending jobs"
    systemctl list-units --failed --no-pager --no-legend 2>&1
    systemctl list-jobs --no-pager --no-legend 2>&1
    section "systemd: purple-x11"
    systemctl status purple-x11 --no-pager -l 2>&1 | head -40

    section "processes (wchan shows what a stuck process waits on)"
    ps -eo pid,ppid,stat,etimes,wchan:28,args --sort=pid 2>&1

    section "casper log (initramfs stdout: medium scan, RAM copy, casper-bottom)"
    cat /var/log/casper.log 2>/dev/null
    section "initramfs trace (only with the debug kernel option)"
    tail -n 400 /run/initramfs/initramfs.debug 2>/dev/null
    section "boot log"
    cat /tmp/purple-boot.log 2>/dev/null
    section "xinitrc log"
    tail -60 /tmp/xinitrc.log 2>/dev/null
    section "Xorg log (tail)"
    tail -60 /home/purple/.local/share/xorg/Xorg.0.log /var/log/Xorg.0.log 2>/dev/null
    section "power log"
    cat /tmp/purple-power.log 2>/dev/null
    section "install log"
    cat /tmp/purple-install.log 2>/dev/null

    section "journal (tail)"
    journalctl -b --no-pager -n 800 2>&1

    section "dmesg (tail; the full live kernel log is at the end of PURPLE-LOG)"
    dmesg 2>&1 | tail -n 300

    section "end"
}

collect
