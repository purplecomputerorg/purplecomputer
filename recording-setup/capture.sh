#!/bin/bash
# Single source of truth for the screen-capture ffmpeg command.
#
# Captures the X display (plus system audio if a PulseAudio sink exists) to
# OUTPUT until it receives SIGINT/SIGTERM, then finalizes the file. We exec
# ffmpeg so the caller's PID *is* ffmpeg: a plain kill/SIGINT finalizes the
# recording cleanly. Used by record-demo.sh and the parent-menu recorder.
#
# Env:
#   PURPLE_CAPTURE_FRAMERATE     capture fps (default 30)
#   PURPLE_CAPTURE_SIZE          WxH (default: full X display via xdpyinfo)
#   PURPLE_CAPTURE_MAX_DURATION  optional hard cap in seconds (ffmpeg -t)
set -e

OUTPUT="${1:?usage: capture.sh OUTPUT.mp4}"
FRAMERATE="${PURPLE_CAPTURE_FRAMERATE:-30}"
SIZE="${PURPLE_CAPTURE_SIZE:-$(xdpyinfo 2>/dev/null | awk '/dimensions/{print $2; exit}')}"
# xdpyinfo (x11-utils) isn't always installed; fall back to xrandr's current mode.
if [ -z "$SIZE" ]; then
    SIZE=$(xrandr 2>/dev/null | awk '/\*/{print $1; exit}')
fi
if [ -z "$SIZE" ]; then
    echo "capture.sh: could not determine screen size (need xdpyinfo or xrandr)" >&2
    exit 1
fi

args=(-y -video_size "$SIZE" -framerate "$FRAMERATE" -draw_mouse 0 -f x11grab -i "$DISPLAY")

AUDIO_SINK=$(pactl get-default-sink 2>/dev/null || true)
if [ -n "$AUDIO_SINK" ]; then
    args+=(-f pulse -i "${AUDIO_SINK}.monitor" -c:a aac)
fi

args+=(-c:v libx264 -preset ultrafast -crf 18)

if [ -n "${PURPLE_CAPTURE_MAX_DURATION:-}" ]; then
    args+=(-t "$PURPLE_CAPTURE_MAX_DURATION")
fi

exec ffmpeg "${args[@]}" "$OUTPUT"
