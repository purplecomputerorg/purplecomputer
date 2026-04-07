#!/bin/sh
# Shown on tty1 when X11 fails to start after multiple attempts.
# Called as ExecStopPost by purple-x11.service.
# Only shows the error screen on the final failure, not during restarts.

# Don't show error on clean stop (e.g. system shutdown)
[ "$SERVICE_RESULT" = "success" ] && exit 0

TTY=/dev/tty1
DIAG=/tmp/purple-diag.txt
FAIL_COUNT_FILE=/tmp/purple-x11-fail-count

# Track failures. The service restarts up to StartLimitBurst times (3).
# Only show the error screen on the final failure.
count=$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$FAIL_COUNT_FILE"
if [ "$count" -lt 3 ]; then
    exit 0
fi

# Paint tty1 purple background
printf '\033]P02d1b4e\033[H\033[2J' > "$TTY" 2>/dev/null

# Find Xorg log wherever it landed. Rootless Xorg (no xserver-xorg-legacy) logs
# to ~/.local/share/xorg/, root/setuid Xorg to /var/log/. Search both plus /tmp.
XORG_LOG=$(find /home/purple/.local/share/xorg /var/log /tmp -name 'Xorg.*.log' 2>/dev/null | head -1)

# Collect diagnostics into a file, then slowly scroll it on screen.
# Scrolls at ~4 lines/sec so each line stays visible for ~7s on a 30-row console,
# plenty for a phone video to capture. No interaction needed after Enter.
show_diagnostics() {
    : > "$DIAG"

    {
        echo ""
        echo "  Purple Computer could not start the display."
        echo ""
        echo "  === DRM connectors ==="
        for f in /sys/class/drm/card*-*/status; do
            [ -f "$f" ] && echo "    $(echo "$f" | sed 's|.*/drm/||;s|/status||'): $(cat "$f" 2>/dev/null)"
        done
        echo ""
        echo "  === GPU devices ==="
        ls -l /dev/dri/ 2>/dev/null | sed 's/^/    /' || echo "    /dev/dri/ not found"
        echo ""
        echo "  === Kernel command line ==="
        cat /proc/cmdline 2>/dev/null | sed 's/^/    /'
        echo ""
        echo "  === Xorg log (last 40 lines) ==="
        if [ -n "$XORG_LOG" ]; then
            echo "  Path: $XORG_LOG"
            echo ""
            tail -40 "$XORG_LOG" 2>/dev/null | sed 's/^/    /'
        else
            echo "    (no Xorg log found, X may not have started)"
            echo "    Searched: ~/.local/share/xorg/, /var/log/, /tmp/"
        fi
        echo ""
        echo "  === xinitrc log (last 20 lines) ==="
        tail -20 /tmp/xinitrc.log 2>/dev/null | sed 's/^/    /' || echo "    (no xinitrc log)"
        echo ""
        echo "  === boot log ==="
        cat /tmp/purple-boot.log 2>/dev/null | sed 's/^/    /' || echo "    (no boot log)"
        echo ""
        echo "  === purple-x11 journal (last 30 lines) ==="
        sudo journalctl -u purple-x11 -b --no-pager -n 30 2>/dev/null | sed 's/^/    /' \
            || echo "    (no journal entries)"
        echo ""
        echo "  === Done ==="
        echo ""
    } > "$DIAG"

    # Clear screen then scroll the diag file line by line
    printf '\033[H\033[2J' > "$TTY" 2>/dev/null
    while IFS= read -r line; do
        printf '%s\n' "$line" > "$TTY" 2>/dev/null
        sleep 0.25
    done < "$DIAG"
}

# Friendly message with option to show details for support
cat > "$TTY" 2>/dev/null <<'MSG'

  Something went wrong starting Purple Computer.

  Please turn off and on again.

  If this keeps happening, contact us at
  support@purplecomputer.org

  If support asks, press Enter to show details,
  then record a video of the screen.

MSG
# Wait for Enter, then show diagnostics, then loop back to the prompt.
# read from tty1 so it works even though stdin may be closed.
while read dummy < "$TTY" 2>/dev/null; do
    show_diagnostics
    # After diagnostics finish scrolling, show the prompt again
    printf '\033[H\033[2J' > "$TTY" 2>/dev/null
    cat > "$TTY" 2>/dev/null <<'MSG'

  Press Enter to show details again.

MSG
done
