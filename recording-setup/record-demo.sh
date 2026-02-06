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
#
# Output files:
#   demo.mp4         - Full screen recording
#   demo_cropped.mp4 - Cropped to viewport (no F-keys or empty space)

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/recordings"
OUTPUT_FILE="${1:-$OUTPUT_DIR/demo.mp4}"
MAX_DURATION="${2:-120}"  # Default 2 minutes max
MUSIC_FILE="$SCRIPT_DIR/demo_music.mp3"

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

echo "=== Purple Computer Demo Recording ==="
echo ""
echo "Output:     $OUTPUT_FILE (full)"
echo "            $CROPPED_FILE (cropped, auto-detected)"
echo "Screen:     $SCREEN_SIZE"
echo "Max time:   ${MAX_DURATION}s"
echo ""

# Remove old recordings if exist
rm -f "$OUTPUT_FILE"
rm -f "$CROPPED_FILE"

# Get default audio sink for capturing system audio
AUDIO_SINK=$(pactl get-default-sink 2>/dev/null || echo "")

# Start FFmpeg recording in background
# Video: x11grab captures X11 display
# Audio: pulse captures system audio via PulseAudio monitor
# -y: overwrite output
# -video_size: screen dimensions
# -framerate: 30fps is smooth enough
# -f x11grab: capture X11 display
# -f pulse: capture PulseAudio
# -c:v libx264: H.264 codec (widely compatible)
# -c:a aac: AAC audio codec
# -preset ultrafast: fast encoding (can re-encode later for smaller size)
# -crf 18: high quality (lower = better, 18-23 is good)
# -t: max duration
echo "Starting recording..."
TEMP_FILE="${OUTPUT_FILE%.mp4}_raw.mp4"

if [ -n "$AUDIO_SINK" ]; then
    echo "Audio:      $AUDIO_SINK (system audio)"
    ffmpeg -y \
        -video_size "$SCREEN_SIZE" \
        -framerate 30 \
        -draw_mouse 0 \
        -f x11grab \
        -i "$DISPLAY" \
        -f pulse \
        -i "${AUDIO_SINK}.monitor" \
        -c:v libx264 \
        -c:a aac \
        -preset ultrafast \
        -crf 18 \
        -t "$MAX_DURATION" \
        "$TEMP_FILE" \
        2>/dev/null &
else
    echo "Audio:      none (PulseAudio not available)"
    ffmpeg -y \
        -video_size "$SCREEN_SIZE" \
        -framerate 30 \
        -draw_mouse 0 \
        -f x11grab \
        -i "$DISPLAY" \
        -c:v libx264 \
        -preset ultrafast \
        -crf 18 \
        -t "$MAX_DURATION" \
        "$TEMP_FILE" \
        2>/dev/null &
fi

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
        # Get duration and calculate trim points
        DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$TEMP_FILE" 2>/dev/null)
        if [ -n "$DURATION" ]; then
            # Calculate trimmed duration (remove 2s from start + 2s from end = 4s total)
            TRIM_DURATION=$(awk "BEGIN {printf \"%.2f\", $DURATION - 4}")

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
                    -ss 2 -t "$TRIM_DURATION" -i "$TEMP_FILE" \
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
                    -ss 2 -t "$TRIM_DURATION" -i "$TEMP_FILE" \
                    -stream_loop -1 -i "$MUSIC_FILE" \
                    -filter_complex "[1:a]volume=0.25[music]" \
                    -map 0:v -map "[music]" \
                    -c:v libx264 -preset ultrafast -crf 18 \
                    -c:a aac -b:a 192k \
                    -shortest \
                    "$OUTPUT_FILE" 2>/dev/null
            else
                echo "No music file found, trimming only..."
                ffmpeg -y -i "$TEMP_FILE" -ss 2 -t "$TRIM_DURATION" -c copy "$OUTPUT_FILE" 2>/dev/null
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
            CROP_PARAMS=$(python3 "$SCRIPT_DIR/detect_crop.py" "$OUTPUT_FILE" 2>/dev/null)

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
                    echo ""
                    echo "=== Recording Complete ==="
                    echo "Full:    $OUTPUT_FILE ($SIZE)"
                    echo "Cropped: $CROPPED_FILE ($CROPPED_SIZE)"
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
PURPLE_TEST_BATTERY=1 PURPLE_DEMO_AUTOSTART=1 ./scripts/run_local.sh

echo ""
echo "Purple exited, stopping recording..."
