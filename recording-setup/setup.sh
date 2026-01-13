#!/bin/bash
# Purple Computer Recording Setup
# Run this in your Ubuntu VM to install screen recording tools
#
# Installs FFmpeg for lightweight recording (no GUI needed)

set -e

echo "=== Purple Computer Recording Setup ==="
echo ""

# Check we're on Linux
if [[ "$(uname)" != "Linux" ]]; then
    echo "Error: This script requires Linux."
    exit 1
fi

echo "[1/2] Installing FFmpeg and audio tools..."
sudo apt update
sudo apt install -y \
    ffmpeg \
    x11-utils \
    pulseaudio-utils

# Check if we have a display
if [ -z "$DISPLAY" ]; then
    echo ""
    echo "Warning: No DISPLAY set. Make sure to run recording from X11 session."
fi

echo ""
echo "[2/2] Testing FFmpeg..."
ffmpeg -version | head -1

echo ""
echo "=== Recording Setup Complete ==="
echo ""
echo "Usage:"
echo "  make record-demo     - Record demo to recordings/demo.mp4"
echo "  make record-demo-gif - Record demo as animated GIF"
echo ""
echo "Or manually:"
echo "  ./recording-setup/record-demo.sh"
echo ""
