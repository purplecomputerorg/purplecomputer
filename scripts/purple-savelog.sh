#!/bin/sh
# savelog: write the boot report to the Pi's boot partition as PURPLE-DEBUG.TXT,
# which any Mac or PC can read. The partition stays read-only otherwise, so a
# power cut can't damage it.
# savelog profile: first record 40s of Purple's Python stacks (py-spy) while you
# use it, saved beside the report as PURPLE-PROFILE.TXT.
set -e
BOOT=/boot/firmware
if [ "$1" = profile ]; then
    pid=$(pgrep -f 'python.* -m purple_tui' | head -1)
    [ -n "$pid" ] || { echo "Purple isn't running."; exit 1; }
    echo "Recording for 40 seconds. Press Ctrl+Alt+F1 now and use the slow parts of Purple."
    echo "Then come back here with Ctrl+Alt+F2."
    sleep 3
    sudo py-spy record --format raw --rate 50 --duration 40 --pid "$pid" --output /tmp/purple-profile.txt >/dev/null 2>&1
fi
sudo /usr/local/bin/purple-diag-collect > /tmp/purple-debug.txt 2>&1
sudo mount -o remount,rw "$BOOT"
sudo cp /tmp/purple-debug.txt "$BOOT/PURPLE-DEBUG.TXT"
[ ! -f /tmp/purple-profile.txt ] || sudo cp /tmp/purple-profile.txt "$BOOT/PURPLE-PROFILE.TXT"
sync
sudo mount -o remount,ro "$BOOT"
echo "Saved to the SD card's boot partition: $(cd "$BOOT" && ls PURPLE-*.TXT | tr '\n' ' ')"
echo "Unplug, then open the card's PURPLE_BOOT drive on another computer."
