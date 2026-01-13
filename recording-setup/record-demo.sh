#!/bin/bash
# Record Purple Computer Demo
#
# This script:
# 1. Starts FFmpeg recording in background
# 2. Launches Purple with demo auto-start
# 3. Stops recording when Purple exits
#
# Usage:
#   ./recording-setup/record-demo.sh [output.mp4] [duration_seconds]
#
# Examples:
#   ./recording-setup/record-demo.sh                    # Default: recordings/demo.mp4, 120s
#   ./recording-setup/record-demo.sh my-demo.mp4 90    # Custom output, 90 seconds

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/recordings"
OUTPUT_FILE="${1:-$OUTPUT_DIR/demo.mp4}"
MAX_DURATION="${2:-120}"  # Default 2 minutes max

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

echo "=== Purple Computer Demo Recording ==="
echo ""
echo "Output:     $OUTPUT_FILE"
echo "Screen:     $SCREEN_SIZE"
echo "Max time:   ${MAX_DURATION}s"
echo ""

# Remove old recording if exists
rm -f "$OUTPUT_FILE"

# Start FFmpeg recording in background
# -y: overwrite output
# -video_size: screen dimensions
# -framerate: 30fps is smooth enough
# -f x11grab: capture X11 display
# -i :0: display 0
# -c:v libx264: H.264 codec (widely compatible)
# -preset ultrafast: fast encoding (can re-encode later for smaller size)
# -crf 18: high quality (lower = better, 18-23 is good)
# -t: max duration
echo "Starting recording..."
ffmpeg -y \
    -video_size "$SCREEN_SIZE" \
    -framerate 30 \
    -f x11grab \
    -i "$DISPLAY" \
    -c:v libx264 \
    -preset ultrafast \
    -crf 18 \
    -t "$MAX_DURATION" \
    "$OUTPUT_FILE" \
    2>/dev/null &

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

    if [ -f "$OUTPUT_FILE" ]; then
        SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
        echo ""
        echo "=== Recording Complete ==="
        echo "Output: $OUTPUT_FILE ($SIZE)"
        echo ""
        echo "To compress further:"
        echo "  ffmpeg -i $OUTPUT_FILE -crf 23 -preset slow compressed.mp4"
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
