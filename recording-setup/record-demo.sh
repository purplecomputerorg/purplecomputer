#!/bin/bash
# Record Purple Computer Demo
#
# Start/stop handshake keeps audio and video perfectly aligned: nothing is
# ever trimmed from the head or re-timed, so the streams stay exactly as
# ffmpeg captured them.
#
# 1. Purple launches first; the app touches READY once the UI has painted
# 2. ffmpeg starts; we wait for its -progress output to show frames flowing
# 3. We touch GO; the demo player waits for GO before its first action
# 4. The player touches DONE when the script ends; recording stops right
#    away, while Purple is still on screen (Purple exits itself 2s later)
#
# Usage:
#   ./recording-setup/record-demo.sh [output.mp4] [duration_seconds]
#
# Examples:
#   ./recording-setup/record-demo.sh                    # Default: recordings/demo.mp4, 180s cap
#   ./recording-setup/record-demo.sh my-demo.mp4 90    # Custom output, 90 second cap
#   PURPLE_NO_MUSIC=1 ./recording-setup/record-demo.sh  # Record without background music
#   PURPLE_RECORD_NO_POSTFX=1 ...                       # Skip cropped/zoomed versions
#
# Output files:
#   demo.mp4         - Full screen recording
#   demo_cropped.mp4 - Cropped to viewport (unless PURPLE_RECORD_NO_POSTFX=1)
#   demo_zoomed.mp4  - With dynamic zoom (unless PURPLE_RECORD_NO_POSTFX=1)

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/recordings"
FRAMERATE=30
OUTPUT_FILE="${1:-$OUTPUT_DIR/demo.mp4}"
MANUAL="$(printenv PURPLE_RECORD_MANUAL)"
NO_POSTFX="$(printenv PURPLE_RECORD_NO_POSTFX)"
if [ "$MANUAL" = "1" ]; then
    MAX_DURATION="${2:-300}"  # You drive it; stops when you exit Purple, with a 5-minute safety cap.
else
    MAX_DURATION="${2:-180}"  # Default 3 minutes max (palm tree painting has 1300+ tiny sleeps)
fi
if [ "$(printenv PURPLE_NO_MUSIC)" = "1" ]; then
    MUSIC_FILE=""
else
    MUSIC_FILE="$SCRIPT_DIR/demo_music.mp3"
fi
if [ "$MANUAL" = "1" ] || [ "$NO_POSTFX" = "1" ]; then
    ZOOM_EVENTS=""  # No scripted zoom keyframes when driving manually or skipping post-fx.
else
    # PURPLE_ZOOM_EVENTS_FILE lets a caller (e.g. record-ad) use a separate
    # keyframe file so its inline zooms regenerate instead of reusing the demo's.
    ZOOM_EVENTS="${PURPLE_ZOOM_EVENTS_FILE:-$SCRIPT_DIR/zoom_events.json}"
fi

mkdir -p "$OUTPUT_DIR"

if ! command -v ffmpeg &> /dev/null; then
    echo "Error: FFmpeg not found. Run: ./recording-setup/setup.sh"
    exit 1
fi

if [ -z "$DISPLAY" ]; then
    echo "Error: No DISPLAY set. Run this from an X11 session (startx first)."
    exit 1
fi

SCREEN_SIZE=$(xdpyinfo | grep dimensions | awk '{print $2}')
if [ -z "$SCREEN_SIZE" ]; then
    echo "Warning: Could not detect screen size, using 1920x1080"
    SCREEN_SIZE="1920x1080"
fi

CROPPED_FILE="${OUTPUT_FILE%.mp4}_cropped.mp4"
ZOOMED_FILE="${OUTPUT_FILE%.mp4}_zoomed.mp4"
TEMP_FILE="${OUTPUT_FILE%.mp4}_raw.mp4"

READY_FILE="$OUTPUT_DIR/.record_ready"
GO_FILE="$OUTPUT_DIR/.record_go"
DONE_FILE="$OUTPUT_DIR/.record_done"
PROGRESS_FILE="$OUTPUT_DIR/.record_progress"

echo "=== Purple Computer Demo Recording ==="
echo ""
echo "Output:     $OUTPUT_FILE (full)"
if [ "$NO_POSTFX" != "1" ]; then
    echo "            $CROPPED_FILE (cropped, auto-detected)"
    echo "            $ZOOMED_FILE (with dynamic zoom, if events present)"
fi
echo "Screen:     $SCREEN_SIZE"
echo "Max time:   ${MAX_DURATION}s"
echo ""

rm -f "$OUTPUT_FILE" "$CROPPED_FILE" "$ZOOMED_FILE" "$TEMP_FILE"
rm -f "$READY_FILE" "$GO_FILE" "$DONE_FILE" "$PROGRESS_FILE"

FFMPEG_PID=""
PURPLE_PID=""

purple_alive() { [ -n "$PURPLE_PID" ] && kill -0 "$PURPLE_PID" 2>/dev/null; }
ffmpeg_alive() { [ -n "$FFMPEG_PID" ] && kill -0 "$FFMPEG_PID" 2>/dev/null; }

# Duration from frame count: x11grab can leave a bogus final timestamp, so
# the container's reported duration isn't trustworthy, but frame count is.
video_duration() {
    local nb
    nb=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of default=noprint_wrappers=1:nokey=1 "$1" 2>/dev/null)
    if ! [[ "$nb" =~ ^[0-9]+$ ]]; then
        nb=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of default=noprint_wrappers=1:nokey=1 "$1" 2>/dev/null)
    fi
    [[ "$nb" =~ ^[0-9]+$ ]] && [ "$nb" -gt 0 ] || return 1
    awk "BEGIN {printf \"%.2f\", $nb / $FRAMERATE}"
}

postprocess() {
    [ -f "$TEMP_FILE" ] || return 0
    echo "Processing video..."

    # -t bounds the output to the real frame count; manual runs also lose the
    # last second, which shows the terminal after Purple exits.
    local dur t_args=()
    if dur=$(video_duration "$TEMP_FILE"); then
        if [ "$MANUAL" = "1" ]; then
            dur=$(awk "BEGIN {printf \"%.2f\", $dur - 1.0}")
        fi
        t_args=(-t "$dur")
    fi

    local has_audio
    has_audio=$(ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$TEMP_FILE" 2>/dev/null)

    # Video is never re-encoded or re-timed here: -c:v copy preserves the
    # captured stream exactly, keeping audio and video aligned.
    if [ -f "$MUSIC_FILE" ] && [ -n "$has_audio" ]; then
        echo "Adding background music with ducking..."
        # Music ducks under app audio: sidechaincompress triggers on quiet
        # sounds (threshold=0.02), compresses hard (ratio=6), ducks fast
        # (attack=50ms) and recovers slow (release=500ms). Music sits at 30%.
        ffmpeg -y \
            -i "$TEMP_FILE" \
            -stream_loop -1 -i "$MUSIC_FILE" \
            -filter_complex "
                [0:a]aformat=fltp:44100:stereo,asplit=2[app][sidechain];
                [1:a]aformat=fltp:44100:stereo,volume=0.3[music];
                [music][sidechain]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=500[ducked];
                [app][ducked]amix=inputs=2:duration=first:weights=1 0.7[out]
            " \
            -map 0:v -map "[out]" \
            -c:v copy -c:a aac -b:a 192k \
            "${t_args[@]}" \
            "$OUTPUT_FILE" 2>/dev/null
    elif [ -f "$MUSIC_FILE" ]; then
        echo "Adding background music (no app audio to duck)..."
        ffmpeg -y \
            -i "$TEMP_FILE" \
            -stream_loop -1 -i "$MUSIC_FILE" \
            -filter_complex "[1:a]volume=0.25[music]" \
            -map 0:v -map "[music]" \
            -c:v copy -c:a aac -b:a 192k \
            -shortest "${t_args[@]}" \
            "$OUTPUT_FILE" 2>/dev/null
    else
        ffmpeg -y -i "$TEMP_FILE" -c copy "${t_args[@]}" "$OUTPUT_FILE" 2>/dev/null
    fi
    rm -f "$TEMP_FILE"

    [ -f "$OUTPUT_FILE" ] || { echo "Error: failed to produce $OUTPUT_FILE"; return 1; }
    SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)

    if [ "$NO_POSTFX" = "1" ]; then
        echo ""
        echo "=== Recording Complete ==="
        echo "Full: $OUTPUT_FILE ($SIZE)"
        return 0
    fi

    echo ""
    echo "Detecting viewport border..."
    CROP_PARAMS=$("$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/detect_crop.py" "$OUTPUT_FILE" 2>/dev/null)
    if [ -z "$CROP_PARAMS" ]; then
        echo "Warning: Could not detect viewport border"
        echo ""
        echo "=== Recording Complete ==="
        echo "Full: $OUTPUT_FILE ($SIZE)"
        return 0
    fi

    echo "Crop detected: $CROP_PARAMS"
    echo "Creating cropped version..."
    ffmpeg -y \
        -i "$OUTPUT_FILE" \
        -vf "crop=$CROP_PARAMS" \
        -c:v libx264 -preset ultrafast -crf 18 \
        -c:a copy \
        "$CROPPED_FILE" 2>/dev/null
    if [ ! -f "$CROPPED_FILE" ]; then
        echo "Warning: Failed to create cropped version"
        echo ""
        echo "=== Recording Complete ==="
        echo "Full: $OUTPUT_FILE ($SIZE)"
        return 0
    fi
    CROPPED_SIZE=$(du -h "$CROPPED_FILE" | cut -f1)

    ZOOM_LINE=""
    if [ -n "$ZOOM_EVENTS" ] && [ -s "$ZOOM_EVENTS" ]; then
        echo ""
        echo "Applying zoom effects..."
        if "$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/apply_zoom.py" \
            "$CROPPED_FILE" "$ZOOM_EVENTS" "$ZOOMED_FILE" && [ -f "$ZOOMED_FILE" ]; then
            ZOOM_LINE="Zoomed:  $ZOOMED_FILE ($(du -h "$ZOOMED_FILE" | cut -f1))"
        else
            echo "Warning: Zoom post-processing failed"
        fi
    fi

    echo ""
    echo "=== Recording Complete ==="
    echo "Full:    $OUTPUT_FILE ($SIZE)"
    echo "Cropped: $CROPPED_FILE ($CROPPED_SIZE)"
    [ -n "$ZOOM_LINE" ] && echo "$ZOOM_LINE"
    echo ""
    echo "To compress further:"
    echo "  ffmpeg -i $OUTPUT_FILE -crf 23 -preset slow compressed.mp4"
}

cleanup() {
    trap - EXIT
    echo ""
    echo "Stopping recording..."
    if ffmpeg_alive; then
        kill -INT "$FFMPEG_PID" 2>/dev/null || true
        wait "$FFMPEG_PID" 2>/dev/null || true
    fi
    if purple_alive && [ -f "$DONE_FILE" ]; then
        # Demo finished; Purple exits itself 2s after. Give it a moment.
        for _ in $(seq 1 50); do
            purple_alive || break
            sleep 0.2
        done
    fi
    # Purple runs in its own session (setsid): kill the whole group, which
    # also sweeps up survivors if only the session leader died.
    [ -n "$PURPLE_PID" ] && kill -- -"$PURPLE_PID" 2>/dev/null || true
    rm -f "$READY_FILE" "$GO_FILE" "$DONE_FILE" "$PROGRESS_FILE"
    postprocess
}
trap cleanup EXIT

# Launch Purple first; recording starts only once its UI is up.
echo "Launching Purple Computer..."
cd "$PROJECT_DIR"

PURPLE_ENV=(
    PURPLE_TEST_BATTERY=1
    PURPLE_RECORD_READY_FILE="$READY_FILE"
    PURPLE_RECORD_GO_FILE="$GO_FILE"
    PURPLE_RECORD_DONE_FILE="$DONE_FILE"
)
if [ "$MANUAL" = "1" ]; then
    echo "Manual mode: drive Purple yourself. Recording stops when you exit Purple or after ${MAX_DURATION}s."
    PURPLE_ENV+=(PURPLE_FULLSCREEN=1)
else
    PURPLE_ENV+=(PURPLE_DEMO_AUTOSTART=1)
    # Only write zoom events if file doesn't already exist (preserve hand-edited events)
    if [ -n "$ZOOM_EVENTS" ]; then
        if [ ! -f "$ZOOM_EVENTS" ]; then
            PURPLE_ENV+=(PURPLE_ZOOM_EVENTS="$ZOOM_EVENTS")
        else
            echo "Using existing zoom_events.json (delete it to regenerate)"
        fi
    fi
fi

setsid timeout $((MAX_DURATION + 120)) env "${PURPLE_ENV[@]}" ./scripts/run_local.sh &
PURPLE_PID=$!

echo "Waiting for Purple UI..."
SECONDS=0
while [ ! -f "$READY_FILE" ]; do
    if ! purple_alive; then
        echo "Error: Purple exited before its UI came up"
        exit 1
    fi
    if [ "$SECONDS" -ge 120 ]; then
        echo "Error: timed out waiting for Purple UI"
        exit 1
    fi
    sleep 0.1
done

echo "Purple UI is up, starting recording..."
PURPLE_CAPTURE_SIZE="$SCREEN_SIZE" \
PURPLE_CAPTURE_FRAMERATE="$FRAMERATE" \
PURPLE_CAPTURE_MAX_DURATION="$MAX_DURATION" \
PURPLE_CAPTURE_PROGRESS_FILE="$PROGRESS_FILE" \
    "$SCRIPT_DIR/capture.sh" "$TEMP_FILE" 2>/dev/null &
FFMPEG_PID=$!

SECONDS=0
until grep -qE '^frame=[1-9]' "$PROGRESS_FILE" 2>/dev/null; do
    if ! ffmpeg_alive; then
        echo "Error: FFmpeg failed to start"
        exit 1
    fi
    if [ "$SECONDS" -ge 20 ]; then
        echo "Error: timed out waiting for FFmpeg to capture frames"
        exit 1
    fi
    sleep 0.05
done

touch "$GO_FILE"
echo "Recording started (PID: $FFMPEG_PID)"
echo "(Press Ctrl+C to stop recording early)"
echo ""

# Record until the demo signals DONE, Purple exits (manual mode), or the
# ffmpeg -t cap ends the capture.
while [ ! -f "$DONE_FILE" ] && purple_alive && ffmpeg_alive; do
    sleep 0.2
done

echo ""
echo "Recording finished."
