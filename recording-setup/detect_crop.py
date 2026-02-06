#!/usr/bin/env python3
"""Detect crop bounds by finding the viewport border color in a video frame."""

import subprocess
import sys
import tempfile
from pathlib import Path

# Viewport border color (dark theme)
BORDER_COLOR = (0x9b, 0x7b, 0xc4)  # #9b7bc4
COLOR_TOLERANCE = 30  # Allow some variance


def extract_frame(video_path: str, timestamp: float = 5.0) -> bytes:
    """Extract a frame from video as raw RGB data."""
    result = subprocess.run([
        "ffmpeg", "-ss", str(timestamp), "-i", video_path,
        "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
    ], capture_output=True)
    return result.stdout


def get_video_info(video_path: str) -> tuple[int, int, float]:
    """Get video width, height, and duration."""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-show_entries", "format=duration",
        "-of", "csv=p=0", video_path
    ], capture_output=True, text=True)
    lines = result.stdout.strip().split("\n")
    w, h = lines[0].split(",")
    duration = float(lines[1]) if len(lines) > 1 else 5.0
    return int(w), int(h), duration


def color_matches(r: int, g: int, b: int) -> bool:
    """Check if a pixel color matches the border color."""
    return (
        abs(r - BORDER_COLOR[0]) <= COLOR_TOLERANCE and
        abs(g - BORDER_COLOR[1]) <= COLOR_TOLERANCE and
        abs(b - BORDER_COLOR[2]) <= COLOR_TOLERANCE
    )


def find_border_bounds(data: bytes, width: int, height: int) -> tuple[int, int, int, int]:
    """Find the bounding box of pixels matching the border color."""
    min_x, max_x = width, 0
    min_y, max_y = height, 0

    for y in range(height):
        for x in range(width):
            idx = (y * width + x) * 3
            r, g, b = data[idx], data[idx + 1], data[idx + 2]

            if color_matches(r, g, b):
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

    return min_x, min_y, max_x, max_y


def main():
    if len(sys.argv) < 2:
        print("Usage: detect_crop.py <video.mp4>", file=sys.stderr)
        sys.exit(1)

    video_path = sys.argv[1]

    # Get video info
    width, height, duration = get_video_info(video_path)

    # Extract a frame from the middle of the video
    frame_data = extract_frame(video_path, timestamp=duration / 2)
    if len(frame_data) != width * height * 3:
        print(f"Error: frame size mismatch", file=sys.stderr)
        sys.exit(1)

    # Find border bounds
    min_x, min_y, max_x, max_y = find_border_bounds(frame_data, width, height)

    if max_x <= min_x or max_y <= min_y:
        print("Error: could not detect border", file=sys.stderr)
        sys.exit(1)

    # Calculate crop (include the border, add padding)
    # Padding is proportional to viewport size since font sizes vary
    viewport_h = max_y - min_y
    viewport_w = max_x - min_x

    # Title row is ~2 rows out of 34 viewport rows (including border)
    # So add ~6% of viewport height above
    pad_top = int(viewport_h * 0.08)
    pad_side = int(viewport_w * 0.01)
    pad_bottom = int(viewport_h * 0.01)

    crop_x = max(0, min_x - pad_side)
    crop_y = max(0, min_y - pad_top)
    crop_w = min(width - crop_x, max_x - min_x + 2 * pad_side)
    crop_h = min(height - crop_y, max_y - min_y + pad_top + pad_bottom)

    # Make dimensions even (required for video encoding)
    crop_w = crop_w // 2 * 2
    crop_h = crop_h // 2 * 2

    # Output ffmpeg crop format: width:height:x:y
    print(f"{crop_w}:{crop_h}:{crop_x}:{crop_y}")


if __name__ == "__main__":
    main()
