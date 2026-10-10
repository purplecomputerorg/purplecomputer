#!/bin/bash
# Purple Computer: make whatever USB printer is plugged in print, with no setup.
# Run as root by purple-printer.service on every printer plug and unplug, and
# idempotent: it rebuilds the one queue from scratch each time. Every step is
# a best guess with a fallback: driverless IPP-over-USB first, then a ladder of
# drivers for the printer's IEEE 1284 ID. The Esc menu's Print card reads STATE.
# Design: guides/printing.md
set -u
STATE=/run/purple-printer.json  # printing.STATE
QUEUE=purple
LOG=/tmp/purple-printer.log
SETTING_UP="setting up"  # printing.SETTING_UP

log() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

write_state() {  # ready model via
    local model=${2//[^A-Za-z0-9 ._+-]/}
    printf '{"ready": %s, "model": "%s", "via": "%s"}\n' "$1" "$model" "$3" > "$STATE.tmp"
    chmod 644 "$STATE.tmp"
    mv "$STATE.tmp" "$STATE"
}

# Interface class 07 is a printer; subclass 01 protocol 04 is IPP-over-USB.
usb_printer() {
    local d any=1
    for d in /sys/bus/usb/devices/*:*; do
        [ "$(cat "$d/bInterfaceClass" 2>/dev/null)" = 07 ] || continue
        any=0
        [ "$(cat "$d/bInterfaceProtocol" 2>/dev/null)" = 04 ] && IPP_USB=1
    done
    return $any
}

finish() {
    lpadmin -p "$QUEUE" -o printer-error-policy=abort-job -o printer-is-shared=false
    cupsenable "$QUEUE" && cupsaccept "$QUEUE" && lpadmin -d "$QUEUE"
    write_state true "$1" "$2"
    log "ready: $1 via $2"
    exit 0
}

# ipp-usb (started by its own udev rule) needs a few seconds to open the
# device; it numbers ports from 60000.
try_ipp_usb() {
    local _ port model
    for _ in $(seq 1 20); do
        for port in 60000 60001 60002 60003; do
            model=$(ipptool -tv "ipp://localhost:$port/ipp/print" get-printer-attributes.test 2>/dev/null |
                    sed -n 's/^ *printer-make-and-model (textWithoutLanguage) = //p' | head -1)
            [ -n "$model" ] || continue
            lpadmin -p "$QUEUE" -E -v "ipp://localhost:$port/ipp/print" -m everywhere 2>>"$LOG" &&
                finish "$model" ipp-usb
        done
        sleep 1
    done
    log "ipp-usb never answered"
}

# Drivers worth trying for an IEEE 1284 ID, best guess first: CUPS's own
# ranking (lpinfo acts on -m the moment it reads it, so the filter goes
# first), then brlaser for Brother lasers it doesn't name (one protocol for the
# family), then a generic driver for each language the printer says it speaks.
drivers_for() {
    local id=$1 cmd
    cmd=",$(sed -n 's/.*\(CMD\|COMMAND SET\):\([^;]*\).*/\2/p' <<<"$id"),"
    lpinfo --device-id "$id" -m 2>/dev/null | grep -v -e '^driverless' -e '^everywhere' | cut -d' ' -f1 | head -3
    [[ $id == *MFG:Brother* && $id =~ Brother\ Laser|HBP|XL2HB ]] && echo drv:///brlaser.drv/brl2300d.ppd
    [[ $cmd =~ ,(PCLXL|PCL6), ]] && echo gutenprint.5.3://pcl-g_6/expert
    [[ $cmd =~ ,PCL ]] && echo gutenprint.5.3://pcl-g_5e/expert
    [[ $cmd =~ ,(POSTSCRIPT|PS|BR-Script) ]] && echo gutenprint.5.3://ps2/expert
    [[ $cmd =~ ,PWG ]] && echo drv:///cupsfilters.drv/pwgrast.ppd
}

# Sets URI, ID and MODEL for the first USB printer the CUPS backend can see.
usb_device() {
    local info _
    for _ in 1 2 3 4 5; do
        info=$(lpinfo --include-schemes usb -l -v 2>/dev/null)
        URI=$(sed -n 's/^Device: uri = //p' <<<"$info" | head -1)
        [ -n "$URI" ] && break
        sleep 1
    done
    ID=$(sed -n 's/^ *device-id = //p' <<<"$info" | head -1)
    MODEL=$(sed -n 's/^ *make-and-model = //p' <<<"$info" | head -1)
    [ -n "$URI" ]
}

try_driver() {  # [driver]: only that one
    local ppd
    usb_device || { log "no usb device from lpinfo"; write_state false "a printer" "CUPS sees no USB printer"; exit 0; }
    log "device: $URI ($ID)"
    for ppd in ${1:-$(drivers_for "$ID" | awk '!seen[$0]++')}; do
        log "driver: $ppd"
        lpadmin -p "$QUEUE" -E -v "$URI" -m "$ppd" 2>>"$LOG" && finish "$MODEL" "$ppd"
    done
    log "no driver for: $MODEL ($ID)"
    write_state false "${MODEL:-a printer}" "no driver for this model"
}

# No argument: the automatic setup udev runs. printer-test passes a route to
# force (ipp, or usb with an optional driver), or drivers to only list guesses.
ROUTE=${1:-auto}
if [ "$ROUTE" = drivers ]; then
    held=$(pgrep -x ipp-usb)
    systemctl stop ipp-usb.service
    usb_device && echo "$URI" && echo "$ID" && drivers_for "$ID" | awk '!seen[$0]++'
    [ -z "$held" ] || systemctl start ipp-usb.service
    exit 0
fi
IPP_USB=0
# Some other USB device came or went: leave a working queue (and its job) alone.
[ "$ROUTE" = auto ] && usb_printer && grep -qs '"ready": true' "$STATE" && exit 0
rm -f "$STATE"
grep -qs "<Printer $QUEUE>\|<DefaultPrinter $QUEUE>" /etc/cups/printers.conf && lpadmin -x "$QUEUE"
# The plug event fires before the kernel has listed the printer's interfaces;
# read them too early and an IPP-over-USB printer looks like a plain one.
udevadm settle --timeout=10
usb_printer || exit 0
pgrep -x ipp-usb >/dev/null && IPP_USB=1
case $ROUTE in
    ipp) IPP_USB=1; systemctl start ipp-usb.service ;;
    usb) IPP_USB=0 ;;
esac
log "printer plugged in (ipp-usb: $IPP_USB, route: $ROUTE)"
write_state false "a printer" "$SETTING_UP"
if [ "$IPP_USB" = 1 ]; then
    try_ipp_usb
    [ "$ROUTE" = ipp ] && { write_state false "a printer" "ipp-usb never answered"; exit 0; }
fi
# ipp-usb holds the printer while it runs, so the USB backend can't reach it.
systemctl stop ipp-usb.service
modprobe -r usblp 2>/dev/null
try_driver "${2:-}"
