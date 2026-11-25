#!/bin/bash
# The admin menu's next-start switches (purplecomputer/rooms/admin_menu.py), applied before X starts.
# Taken once from the log partition, the one place a Purple Key keeps across restarts, and held in
# /run for this boot only: a switch that stops X from starting is gone after the next restart.
# Every start first undoes the last one's edits, so an installed system never keeps one either.

NEXT=/var/log/purple/admin-next-start
NOW=/run/purple-admin-start
XCONF=/usr/share/X11/xorg.conf.d/10-modesetting.conf
TAG="# purple-admin"

[ -f "$NEXT" ] && mv -f "$NEXT" "$NOW"
sed -i "/$TAG\$/d" "$XCONF"
grep -qx noaccel "$NOW" 2>/dev/null &&
    sed -i "/Driver     \"modesetting\"/a\\    Option     \"AccelMethod\" \"none\"  $TAG" "$XCONF"
[ -f "$NOW" ] && echo "admin switches this start: $(tr '\n' ' ' < "$NOW")"
exit 0
