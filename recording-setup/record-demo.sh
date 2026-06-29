#!/bin/bash
# Record Purple Computer Demo
#
# This script:
# 1. Starts FFmpeg recording in background
# 2. Launches Purple with demo auto-start
# 3. Stops recording when Purple exits
# 4. Produces both full and cropped versions
#
# Usage:
#   ./recording-setup/record-demo.sh [output.mp4] [duration_seconds]
#
# Examples:
#   ./recording-setup/record-demo.sh                    # Default: recordings/demo.mp4, 120s
#   ./recording-setup/record-demo.sh my-demo.mp4 90    # Custom output, 90 seconds
#   PURPLE_NO_MUSIC=1 ./recording-setup/record-demo.sh  # Record without background music
#
# Output files:
#   demo.mp4         - Full screen recording
#   demo_cropped.mp4 - Cropped to viewport (no F-keys or empty space)

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/recordings"
FRAMERATE=30
OUTPUT_FILE="${1:-$OUTPUT_DIR/demo.mp4}"
if [ "$(printenv PURPLE_RECORD_MANUAL)" = "1" ]; then
    MAX_DURATION="${2:-300}"  # You drive it; stops when you exit Purple, with a 5-minute safety cap.
else
    MAX_DURATION="${2:-180}"  # Default 3 minutes max (palm tree painting has 1300+ tiny sleeps)
fi
if [ "$(printenv PURPLE_NO_MUSIC)" = "1" ]; then
    MUSIC_FILE=""
else
    MUSIC_FILE="$SCRIPT_DIR/demo_music.mp3"
fi
if [ "$(printenv PURPLE_RECORD_MANUAL)" = "1" ]; then
    ZOOM_EVENTS=""  # No scripted zoom keyframes when you drive it yourself.
else
    # PURPLE_ZOOM_EVENTS_FILE lets a caller (e.g. record-ad) use a separate
    # keyframe file so its inline zooms regenerate instead of reusing the demo's.
    ZOOM_EVENTS="${PURPLE_ZOOM_EVENTS_FILE:-$SCRIPT_DIR/zoom_events.json}"
fi

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Check dependencies
if ! command -v ffmpeg &> /dev/null; then
    echo "Error: FFmpeg not found. Run: ./recording-setup/setup.sh"
    exit 1
fi

if [ -z "$DISPLAY" ]; then
    echo "Error: No DISPLAY set. Run this from an X11 session (startx first)."
    exit 1
fi

# Get screen dimensions
SCREEN_SIZE=$(xdpyinfo | grep dimensions | awk '{print $2}')
if [ -z "$SCREEN_SIZE" ]; then
    echo "Warning: Could not detect screen size, using 1920x1080"
    SCREEN_SIZE="1920x1080"
fi

# Cropped output filename
CROPPED_FILE="${OUTPUT_FILE%.mp4}_cropped.mp4"
ZOOMED_FILE="${OUTPUT_FILE%.mp4}_zoomed.mp4"

echo "=== Purple Computer Demo Recording ==="
echo ""
echo "Output:     $OUTPUT_FILE (full)"
echo "            $CROPPED_FILE (cropped, auto-detected)"
echo "            $ZOOMED_FILE (with dynamic zoom, if events present)"
echo "Screen:     $SCREEN_SIZE"
echo "Max time:   ${MAX_DURATION}s"
echo ""

# Remove old recordings (but keep zoom_events.json if hand-edited)
rm -f "$OUTPUT_FILE"
rm -f "$CROPPED_FILE"
rm -f "$ZOOMED_FILE"

# Start the screen capture in the background via the shared capture command.
# capture.sh exec's ffmpeg, so $FFMPEG_PID is ffmpeg itself and the cleanup
# trap's kill finalizes the file cleanly.
echo "Starting recording..."
TEMP_FILE="${OUTPUT_FILE%.mp4}_raw.mp4"

# Record FFmpeg start time for sync with demo player
date +%s.%N > "$OUTPUT_DIR/.rec_start_epoch"

PURPLE_CAPTURE_SIZE="$SCREEN_SIZE" \
PURPLE_CAPTURE_FRAMERATE="$FRAMERATE" \
PURPLE_CAPTURE_MAX_DURATION="$MAX_DURATION" \
    "$SCRIPT_DIR/capture.sh" "$TEMP_FILE" 2>/dev/null &

FFMPEG_PID=$!

# Give FFmpeg a moment to start
sleep 1

# Check if FFmpeg started successfully
if ! kill -0 $FFMPEG_PID 2>/dev/null; then
    echo "Error: FFmpeg failed to start"
    exit 1
fi

echo "Recording started (PID: $FFMPEG_PID)"
echo ""

# Trap to ensure we stop recording on exit
cleanup() {
    echo ""
    echo "Stopping recording..."
    kill $FFMPEG_PID 2>/dev/null || true
    wait $FFMPEG_PID 2>/dev/null || true

    if [ -f "$TEMP_FILE" ]; then
        echo "Processing video (trimming + adding background music)..."
        # x11grab tags frames with wall-clock PTS; an abrupt stop can leave a bogus
        # final timestamp, so the container's reported duration is absurd (tiny file,
        # hundreds of "hours"). Frame count stays accurate, so derive duration from it
        # and rebuild every timeline below with -r "$FRAMERATE" before the input.
        NB_FRAMES=$(ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of default=noprint_wrappers=1:nokey=1 "$TEMP_FILE" 2>/dev/null)
        if ! [[ "$NB_FRAMES" =~ ^[0-9]+$ ]]; then
            NB_FRAMES=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of default=noprint_wrappers=1:nokey=1 "$TEMP_FILE" 2>/dev/null)
        fi
        if [[ "$NB_FRAMES" =~ ^[0-9]+$ ]] && [ "$NB_FRAMES" -gt 0 ]; then
            DURATION=$(awk "BEGIN {printf \"%.2f\", $NB_FRAMES / $FRAMERATE}")
        else
            DURATION=""
        fi
        if [ -n "$DURATION" ]; then
            # Compute dynamic trim: how far into the recording the demo actually started
            TRIM_START=2  # fallback if sync files are missing
            if [ -f "$OUTPUT_DIR/.rec_start_epoch" ] && [ -f "$OUTPUT_DIR/.demo_start_epoch" ]; then
                TRIM_START=$("$PROJECT_DIR/.venv/bin/python" -c "
rec = float(open('$OUTPUT_DIR/.rec_start_epoch').read())
demo = float(open('$OUTPUT_DIR/.demo_start_epoch').read())
print(f'{demo - rec:.2f}')
")
                echo "Demo started ${TRIM_START}s into recording (dynamic trim)"
            else
                echo "Sync files missing, using fallback trim of ${TRIM_START}s"
            fi
            END_TRIM=2
            TRIM_DURATION=$(awk "BEGIN {printf \"%.2f\", $DURATION - $TRIM_START - $END_TRIM}")

            # Check if temp file has audio
            HAS_AUDIO=$(ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 "$TEMP_FILE" 2>/dev/null)

            if [ -f "$MUSIC_FILE" ] && [ -n "$HAS_AUDIO" ]; then
                echo "Adding background music with ducking..."
                # Mix background music with ducking:
                # - [0:a] is app audio, [1:a] is music
                # - sidechaincompress: music ducks when app audio plays
                #   - threshold=0.02: trigger ducking on quiet sounds
                #   - ratio=6: strong compression when triggered
                #   - attack=50: duck quickly (50ms)
                #   - release=500: come back slowly (500ms)
                # - Music at 30% volume normally, app audio at full volume
                # - amix combines them (duration=first keeps video length)
                ffmpeg -y \
                    -r "$FRAMERATE" -ss "$TRIM_START" -t "$TRIM_DURATION" -i "$TEMP_FILE" \
                    -stream_loop -1 -i "$MUSIC_FILE" \
                    -filter_complex "
                        [0:a]aformat=fltp:44100:stereo,asplit=2[app][sidechain];
                        [1:a]aformat=fltp:44100:stereo,volume=0.3[music];
                        [music][sidechain]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=500[ducked];
                        [app][ducked]amix=inputs=2:duration=first:weights=1 0.7[out]
                    " \
                    -map 0:v -map "[out]" \
                    -c:v libx264 -preset ultrafast -crf 18 \
                    -c:a aac -b:a 192k \
                    "$OUTPUT_FILE" 2>/dev/null
            elif [ -f "$MUSIC_FILE" ]; then
                echo "Adding background music (no app audio to duck)..."
                # No app audio, just add music at lower volume
                ffmpeg -y \
                    -r "$FRAMERATE" -ss "$TRIM_START" -t "$TRIM_DURATION" -i "$TEMP_FILE" \
                    -stream_loop -1 -i "$MUSIC_FILE" \
                    -filter_complex "[1:a]volume=0.25[music]" \
                    -map 0:v -map "[music]" \
                    -c:v libx264 -preset ultrafast -crf 18 \
                    -c:a aac -b:a 192k \
                    -shortest \
                    "$OUTPUT_FILE" 2>/dev/null
            else
                echo "No music file found, trimming only..."
                ffmpeg -y -r "$FRAMERATE" -ss "$TRIM_START" -t "$TRIM_DURATION" -i "$TEMP_FILE" \
                    -c:v libx264 -preset ultrafast -crf 18 -c:a copy "$OUTPUT_FILE" 2>/dev/null
            fi
            rm -f "$TEMP_FILE"
        else
            # Fallback: just rename if we can't get duration
            mv "$TEMP_FILE" "$OUTPUT_FILE"
        fi

        if [ -f "$OUTPUT_FILE" ]; then
            SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
            echo ""
            echo "=== Full Recording Complete ==="
            echo "Output: $OUTPUT_FILE ($SIZE)"

            # Create cropped version (viewport only, no F-keys or empty space)
            # Detect bounds by finding the viewport border color (#9b7bc4)
            echo ""
            echo "Detecting viewport border..."
            CROP_PARAMS=$("$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/detect_crop.py" "$OUTPUT_FILE" 2>/dev/null)

            if [ -n "$CROP_PARAMS" ]; then
                echo "Crop detected: $CROP_PARAMS"
                echo "Creating cropped version..."
                rm -f "$CROPPED_FILE"
                ffmpeg -y \
                    -i "$OUTPUT_FILE" \
                    -vf "crop=$CROP_PARAMS" \
                    -c:v libx264 -preset ultrafast -crf 18 \
                    -c:a copy \
                    "$CROPPED_FILE" 2>/dev/null

                if [ -f "$CROPPED_FILE" ]; then
                    CROPPED_SIZE=$(du -h "$CROPPED_FILE" | cut -f1)

                    # Apply zoom effects if zoom events were recorded
                    if [ -f "$ZOOM_EVENTS" ] && [ -s "$ZOOM_EVENTS" ]; then
                        echo ""
                        echo "Applying zoom effects..."
                        if "$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/apply_zoom.py" \
                            "$CROPPED_FILE" "$ZOOM_EVENTS" "$ZOOMED_FILE"; then
                            if [ -f "$ZOOMED_FILE" ]; then
                                ZOOMED_SIZE=$(du -h "$ZOOMED_FILE" | cut -f1)
                                echo ""
                                echo "=== Recording Complete ==="
                                echo "Full:    $OUTPUT_FILE ($SIZE)"
                                echo "Cropped: $CROPPED_FILE ($CROPPED_SIZE)"
                                echo "Zoomed:  $ZOOMED_FILE ($ZOOMED_SIZE)"
                            else
                                echo "Warning: Failed to create zoomed version"
                                echo ""
                                echo "=== Recording Complete ==="
                                echo "Full:    $OUTPUT_FILE ($SIZE)"
                                echo "Cropped: $CROPPED_FILE ($CROPPED_SIZE)"
                            fi
                        else
                            echo "Warning: Zoom post-processing failed"
                            echo ""
                            echo "=== Recording Complete ==="
                            echo "Full:    $OUTPUT_FILE ($SIZE)"
                            echo "Cropped: $CROPPED_FILE ($CROPPED_SIZE)"
                        fi
                    else
                        echo ""
                        echo "=== Recording Complete ==="
                        echo "Full:    $OUTPUT_FILE ($SIZE)"
                        echo "Cropped: $CROPPED_FILE ($CROPPED_SIZE)"
                        echo "(No zoom events recorded)"
                    fi
                else
                    echo "Warning: Failed to create cropped version"
                    echo ""
                    echo "=== Recording Complete ==="
                    echo "Full: $OUTPUT_FILE ($SIZE)"
                fi
            else
                echo "Warning: Could not detect viewport border"
                echo ""
                echo "=== Recording Complete ==="
                echo "Full: $OUTPUT_FILE ($SIZE)"
            fi
            echo ""
            echo "To compress further:"
            echo "  ffmpeg -i $OUTPUT_FILE -crf 23 -preset slow compressed.mp4"
        fi
    fi
}
trap cleanup EXIT

# Launch Purple with demo auto-start
echo "Launching Purple Computer with demo..."
echo "(Press Ctrl+C to stop recording early)"
echo ""

cd "$PROJECT_DIR"

# Only write zoom events if file doesn't already exist (preserve hand-edited events)
ZOOM_ENV=""
if [ ! -f "$ZOOM_EVENTS" ]; then
    ZOOM_ENV="PURPLE_ZOOM_EVENTS=$ZOOM_EVENTS"
else
    echo "Using existing zoom_events.json (delete it to regenerate)"
fi

SYNC_FILE="$OUTPUT_DIR/.demo_start_epoch"
if [ "$(printenv PURPLE_RECORD_MANUAL)" = "1" ]; then
    echo "Manual mode: drive Purple yourself. Recording stops when you exit Purple or after ${MAX_DURATION}s."
    # Manual mode writes no demo-start marker; drop any stale one so the trim
    # falls back to a fixed 2s head instead of a bogus epoch difference.
    rm -f "$SYNC_FILE"
    timeout "$MAX_DURATION" env PURPLE_TEST_BATTERY=1 PURPLE_FULLSCREEN=1 ./scripts/run_local.sh || true
else
    timeout "$MAX_DURATION" env PURPLE_TEST_BATTERY=1 PURPLE_DEMO_AUTOSTART=1 \
        $ZOOM_ENV PURPLE_DEMO_SYNC_FILE="$SYNC_FILE" ./scripts/run_local.sh || true
fi

echo ""
echo "Purple exited, stopping recording..."
