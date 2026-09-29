#!/bin/sh
# Turn every panel backlight to full and let the purple user set it. Runs as
# root (ExecStartPre=+) in purple-x11.service after purple-wait-display, once
# the GPU driver has registered its backlight. Firmware can leave it low (a
# laptop booted at 19200/96000); Purple then applies the Parent Menu level
# (purple_tui/backlight.py), so if that fails the screen stays bright.

for d in /sys/class/backlight/*; do
    [ -f "$d/max_brightness" ] || continue
    before=$(cat "$d/brightness" 2>/dev/null)
    cat "$d/max_brightness" > "$d/brightness" 2>/dev/null
    chown purple "$d/brightness" 2>/dev/null
    msg="[$(date '+%H:%M:%S.%3N')] [backlight] ${d##*/}: $before -> $(cat "$d/brightness" 2>/dev/null) (max $(cat "$d/max_brightness"))"
    echo "$msg" >> /tmp/purple-boot.log 2>/dev/null
    echo "$msg" >> /var/log/purple/boot.log 2>/dev/null
done
exit 0
