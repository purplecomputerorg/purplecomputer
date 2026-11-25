#!/bin/bash
# The admin menu's next-start switches (purplecomputer/rooms/admin_menu.py), applied before X starts.
# Taken once from the log partition, the one place a Purple Key keeps across restarts, and held in
# /run for this boot only: a switch that stops X from starting is gone after the next restart.
# Every start first undoes the last one's edits, so an installed system never keeps one either.

NEXT=/var/log/purple/admin-next-start
NOW=/run/purple-admin-start
XCONF=/usr/share/X11/xorg.conf.d/10-modesetting.conf
TAG="# purple-admin"

if [ -f "$NEXT" ]; then
    mv -f "$NEXT" "$NOW"
elif W=$(mktemp -d) && mount -L writable "$W" 2>/dev/null; then
    # A Purple Key's live boot gives /var/log a new folder on its writable partition every start
    # (install-logs-<date>.N/log), so the switch is in an earlier start's folder: the newest one wins.
    LAST=$(ls -t "$W"/install-logs-*/log/purple/admin-next-start 2>/dev/null | head -1)
    [ -n "$LAST" ] && cp "$LAST" "$NOW"
    rm -f "$W"/install-logs-*/log/purple/admin-next-start
    umount "$W"
fi
[ -n "$W" ] && rmdir "$W" 2>/dev/null
sync
sed -i "/$TAG\$/d" "$XCONF"
grep -qx noaccel "$NOW" 2>/dev/null &&
    sed -i "/Driver     \"modesetting\"/a\\    Option     \"AccelMethod\" \"none\"  $TAG" "$XCONF"
[ -f "$NOW" ] && echo "admin switches this start: $(tr '\n' ' ' < "$NOW")"
exit 0
