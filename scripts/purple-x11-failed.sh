#!/bin/sh
# Shown on tty1 when X11 fails to start after multiple attempts.
# Called as ExecStopPost by purple-x11.service.
# Only shows the error screen on failure, not clean shutdown.

# Don't show error on clean stop (e.g. system shutdown)
[ "$SERVICE_RESULT" = "success" ] && exit 0

DEBUG_FLAG=/opt/purple/debug

# Paint tty1 purple background
printf '\033]P02d1b4e\033[H\033[2J' > /dev/tty1 2>/dev/null

if [ -f "$DEBUG_FLAG" ]; then
    # Debug mode: dump diagnostics to screen in auto-paged sections with pauses,
    # so a parent can just point a phone camera and record a video.
    # Full output also saved to /tmp/purple-diag.txt for tty2 access.
    DIAG=/tmp/purple-diag.txt
    TTY=/dev/tty1
    PAUSE=5

    # Xorg runs rootless (no xserver-xorg-legacy), so it logs to the user's home
    XORG_LOG=""
    for candidate in /home/purple/.local/share/xorg/Xorg.0.log /var/log/Xorg.0.log; do
        [ -f "$candidate" ] && XORG_LOG="$candidate" && break
    done

    # show_section: clear screen, show a section, pause for video capture
    show_section() {
        printf '\033[H\033[2J' > "$TTY" 2>/dev/null
        cat > "$TTY" 2>/dev/null
        sleep "$PAUSE"
    }

    # Also save everything to the diag file
    : > "$DIAG"

    # --- Section 1: Header + hardware ---
    {
        echo ""
        echo "  Purple Computer could not start the display."
        echo "  Recording? Each screen pauses ${PAUSE}s then auto-advances."
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
    } | tee -a "$DIAG" | show_section

    # --- Section 2: Xorg log (the most important one) ---
    {
        echo ""
        echo "  === Xorg log (last 40 lines) ==="
        echo "  Path: ${XORG_LOG:-(not found)}"
        echo ""
        if [ -n "$XORG_LOG" ]; then
            tail -40 "$XORG_LOG" 2>/dev/null | sed 's/^/    /'
        else
            echo "    (no Xorg log found)"
        fi
    } | tee -a "$DIAG" | show_section

    # --- Section 3: xinitrc + boot log ---
    {
        echo ""
        echo "  === xinitrc log (last 20 lines) ==="
        tail -20 /tmp/xinitrc.log 2>/dev/null | sed 's/^/    /' || echo "    (no xinitrc log)"
        echo ""
        echo "  === boot log ==="
        cat /tmp/purple-boot.log 2>/dev/null | sed 's/^/    /' || echo "    (no boot log)"
    } | tee -a "$DIAG" | show_section

    # --- Section 4: systemd journal for this service ---
    {
        echo ""
        echo "  === purple-x11 journal (last 30 lines) ==="
        sudo journalctl -u purple-x11 -b --no-pager -n 30 2>/dev/null | sed 's/^/    /' \
            || echo "    (no journal entries)"
    } | tee -a "$DIAG" | show_section

    # --- Final screen: stays up ---
    printf '\033[H\033[2J' > "$TTY" 2>/dev/null
    cat > "$TTY" 2>/dev/null <<MSG

  Done. All diagnostics saved to /tmp/purple-diag.txt
  Shell: Ctrl+Alt+F2

MSG
else
    # Production: kid/parent-friendly message
    cat > /dev/tty1 2>/dev/null <<'MSG'

  Something went wrong starting Purple Computer.

  Please turn off and on again.

  If this keeps happening, contact us at
  support@purplecomputer.org

MSG
fi
