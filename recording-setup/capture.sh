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
#   PURPLE_CAPTURE_PROGRESS_FILE optional ffmpeg -progress output, so callers
#                                can confirm frames are flowing before acting
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

# Force constant frame rate at capture: if the encoder can't keep up with
# the nominal fps, ffmpeg duplicates frames instead of silently producing
# fewer, which would make the video timeline shorter than the audio and
# drift out of sync over a long recording.
args+=(-c:v libx264 -preset ultrafast -crf 18 -r "$FRAMERATE" -vsync cfr)

if [ -n "${PURPLE_CAPTURE_MAX_DURATION:-}" ]; then
    args+=(-t "$PURPLE_CAPTURE_MAX_DURATION")
fi

# -stats_period would give faster updates but needs ffmpeg 4.3+; plain
# -progress already emits frame lines ~2x/sec on every version.
if [ -n "${PURPLE_CAPTURE_PROGRESS_FILE:-}" ]; then
    args+=(-progress "$PURPLE_CAPTURE_PROGRESS_FILE")
fi

exec ffmpeg "${args[@]}" "$OUTPUT"
