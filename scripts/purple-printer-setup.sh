#!/bin/bash
# Purple Computer: make whatever USB printer is plugged in print, with no setup.
# Run as root by purple-printer.service on every printer plug and unplug, and
# idempotent: it rebuilds the one queue from scratch each time. Tries
# driverless IPP-over-USB first, then a driver matched to the printer's own
# IEEE 1284 ID. The Esc menu's Print card reads STATE.
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

# lpinfo runs each request the moment it reads -v or -m, so filters go first.
# CUPS ranks drivers on the printer's make, model and command set; Brother
# lasers brlaser doesn't list by name speak the same protocol as the ones it does.
try_driver() {
    local info uri id model ppd
    info=$(lpinfo --include-schemes usb -l -v 2>/dev/null)
    uri=$(sed -n 's/^Device: uri = //p' <<<"$info" | head -1)
    id=$(sed -n 's/^ *device-id = //p' <<<"$info" | head -1)
    model=$(sed -n 's/^ *make-and-model = //p' <<<"$info" | head -1)
    [ -n "$uri" ] || { log "no usb device from lpinfo"; write_state false "a printer" "CUPS sees no USB printer"; exit 0; }
    log "device: $uri ($id)"
    ppd=$(lpinfo --device-id "$id" -m 2>/dev/null | grep -v -e '^driverless' -e '^everywhere' | head -1 | cut -d' ' -f1)
    if [ -z "$ppd" ] && [[ $id == *MFG:Brother* ]] && [[ $id =~ Brother\ Laser|HBP|XL2HB ]]; then
        ppd=drv:///brlaser.drv/brl2300d.ppd
    fi
    if [ -z "$ppd" ]; then
        log "no driver for: $model ($id)"
        write_state false "${model:-a printer}" "no driver for this model"
        exit 0
    fi
    log "driver: $ppd"
    lpadmin -p "$QUEUE" -E -v "$uri" -m "$ppd" 2>>"$LOG" && finish "$model" "$ppd"
    write_state false "$model" "queue setup failed"
}

IPP_USB=0
# Some other USB device came or went: leave a working queue (and its job) alone.
usb_printer && grep -qs '"ready": true' "$STATE" && exit 0
rm -f "$STATE"
grep -qs "<Printer $QUEUE>\|<DefaultPrinter $QUEUE>" /etc/cups/printers.conf && lpadmin -x "$QUEUE"
usb_printer || exit 0
log "printer plugged in (ipp-usb: $IPP_USB)"
write_state false "a printer" "$SETTING_UP"
[ "$IPP_USB" = 1 ] && try_ipp_usb
try_driver
