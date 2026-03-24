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
    # Debug mode: show technical details
    cat > /dev/tty1 2>/dev/null <<'MSG'

  Purple Computer could not start the display.

  Logs:
    /tmp/purple-boot.log      (boot sequence)
    /tmp/startx.log           (X11 output)
    /tmp/xinitrc.log           (xinitrc output)
    /var/log/Xorg.0.log        (X server)

  Switch to tty2 for a shell: Ctrl+Alt+F2

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
