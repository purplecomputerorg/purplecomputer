#!/bin/bash
# Start the tear-free compositor. Shared by xinitrc (boot) and
# debug-display.sh (runtime A/B), so the launch behavior lives in one place.
#
# The modesetting driver has no TearFree option, so picom is what gives Purple
# whole-frame, vsync'd presentation and stops the old-Intel scanout
# checkerboard. Guarded: if picom can't start, the session continues
# uncomposited (the pre-picom behavior), never a black screen. Runs entirely as
# the purple user, no root needed. See guides/intel-display-tuning.md.

LOG=/tmp/purple-picom.log
CONF=/etc/purple/picom.conf

command -v picom >/dev/null 2>&1 || { echo "picom not installed; continuing uncomposited"; exit 0; }
[ -f "$CONF" ] || CONF=/dev/null
pkill -x picom 2>/dev/null

# Hardware GL for the compositor only; Alacritty stays software (the session
# exports LIBGL_ALWAYS_SOFTWARE=1). glx gives reliable vsync; xrender is the
# no-GL fallback for VMs and machines where hardware GL is unavailable. If
# neither stays up, we fall through and leave the screen uncomposited.
for backend in glx xrender; do
    LIBGL_ALWAYS_SOFTWARE=0 picom --config "$CONF" --backend "$backend" \
        --log-file "$LOG" >/dev/null 2>&1 &
    pid=$!
    sleep 0.6
    if kill -0 "$pid" 2>/dev/null; then
        echo "compositor started: picom --backend $backend (pid=$pid)"
        exit 0
    fi
done

echo "compositor unavailable (picom failed to start); continuing uncomposited"
exit 0
