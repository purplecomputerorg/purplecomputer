#!/bin/bash
# Record ALL Purple Computer Demos
#
# This script records each demo variant and produces separate MP4 files.
#
# Usage:
#   ./recording-setup/record-all-demos.sh
#
# Output files will be in recordings/ with names like:
#   demo_magic_show.mp4
#   demo_smiley_symphony.mp4
#   etc.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/recordings"

# All available demo names (must match DEMO_SCRIPTS in purple_tui/demo/__init__.py)
DEMOS=(
    "magic_show"
    "smiley_symphony"
    "rainbow_explorer"
    "story_time"
    "quick_punchy"
    "default"
    "short"
)

# Max durations for each demo (in seconds)
declare -A DURATIONS
DURATIONS["magic_show"]=90
DURATIONS["smiley_symphony"]=80
DURATIONS["rainbow_explorer"]=100
DURATIONS["story_time"]=90
DURATIONS["quick_punchy"]=60
DURATIONS["default"]=90
DURATIONS["short"]=45

echo "=== Recording All Purple Computer Demos ==="
echo ""
echo "Output directory: $OUTPUT_DIR"
echo "Demos to record: ${DEMOS[*]}"
echo ""

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

# Record each demo
for demo in "${DEMOS[@]}"; do
    output_file="$OUTPUT_DIR/demo_${demo}.mp4"
    duration="${DURATIONS[$demo]:-90}"

    echo ""
    echo "============================================"
    echo "Recording: $demo"
    echo "Output:    $output_file"
    echo "Max time:  ${duration}s"
    echo "============================================"
    echo ""

    # Export the demo name for Purple to pick up
    export PURPLE_DEMO_NAME="$demo"

    # Run the recording script
    "$SCRIPT_DIR/record-demo.sh" "$output_file" "$duration"

    # Small pause between recordings
    sleep 2
done

echo ""
echo "=== All Demos Recorded ==="
echo ""
echo "Output files:"
for demo in "${DEMOS[@]}"; do
    output_file="$OUTPUT_DIR/demo_${demo}.mp4"
    if [ -f "$output_file" ]; then
        size=$(du -h "$output_file" | cut -f1)
        echo "  $output_file ($size)"
    else
        echo "  $output_file (MISSING)"
    fi
done
echo ""
