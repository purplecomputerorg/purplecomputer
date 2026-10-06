#!/bin/bash
# Parent terminal: check printing and try each route by hand (guides/printing.md).
#   printer-test             what Purple set up, and the last jobs
#   printer-test print       print a test circle on the current setup
#   printer-test ipp         rebuild on the driverless route, then print
#   printer-test usb [DRV]   rebuild on the USB driver route (one driver, or the ladder), then print
#   printer-test drivers     the printer's ID and the drivers the ladder would try
#   printer-test log         the last CUPS job lines
QUEUE=purple
PAGE=/tmp/purple-test-circle.png

status() {
    cat /run/purple-printer.json 2>/dev/null || echo "no printer state (nothing plugged in?)"
    tail -n 6 /tmp/purple-printer.log 2>/dev/null
    lpstat -v "$QUEUE" 2>/dev/null
    lpstat -l -p "$QUEUE" 2>/dev/null | head -2
    lpstat -W all -o "$QUEUE" 2>/dev/null | tail -3
}

circle() {
    PYGAME_HIDE_SUPPORT_PROMPT=1 python3 -c "import pygame as p;s=p.Surface((99,99));s.fill(-1);p.draw.circle(s,0,(50,50),30);p.image.save(s,'$PAGE')"
    lp -d "$QUEUE" -o fit-to-page "$PAGE"
}

case "${1:-}" in
    "") status ;;
    print) circle ;;
    ipp | usb)
        sudo cancel -a -x
        sudo /usr/local/bin/purple-printer-setup "$@"
        status
        grep -qs '"ready": true' /run/purple-printer.json && circle
        ;;
    drivers) sudo /usr/local/bin/purple-printer-setup drivers ;;
    log) sudo cupsctl --debug-logging && sudo grep "\[Job" /var/log/cups/error_log | tail -20 ;;
    *) sed -n '2,8s/^# \{0,1\}//p' "$0" ;;
esac
