#!/bin/sh
# savelog: write the boot report to the Pi's boot partition as PURPLE-DEBUG.TXT,
# which any Mac or PC can read. The partition stays read-only otherwise, so a
# power cut can't damage it.
set -e
BOOT=/boot/firmware
OUT=$BOOT/PURPLE-DEBUG.TXT
sudo /usr/local/bin/purple-diag-collect > /tmp/purple-debug.txt 2>&1
sudo mount -o remount,rw "$BOOT"
sudo cp /tmp/purple-debug.txt "$OUT"
sync
sudo mount -o remount,ro "$BOOT"
echo "Saved $(wc -c < /tmp/purple-debug.txt) bytes to PURPLE-DEBUG.TXT on the SD card's boot partition."
echo "Unplug, then open the card's PURPLE_BOOT drive on another computer."
