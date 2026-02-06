#!/usr/bin/env python3
"""Apply dynamic zoom effects to demo recordings.

Reads zoom events from a JSON sidecar file and applies smooth crop/scale
transitions via FFmpeg. Uses a segment-based approach: splits video at
zoom transitions, applies crops, then concatenates.

Usage:
    python apply_zoom.py input.mp4 zoom_events.json output.mp4

The zoom events JSON format:
    [
        {"time": 2.5, "action": "zoom_in", "region": "input", "zoom": 1.5, "duration": 0.4},
        {"time": 8.0, "action": "zoom_out", "duration": 0.4}
    ]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Add parent to path to import constants
sys.path.insert(0, str(Path(__file__).parent.parent))
from purple_tui.constants import ZOOM_REGIONS


def get_video_info(video_path: Path) -> tuple[int, int, float, float]:
    """Get video dimensions, duration, and framerate."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path)
        ],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)

    stream = data["streams"][0]
    width = int(stream["width"])
    height = int(stream["height"])

    fps_str = stream["r_frame_rate"]
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)

    duration = float(stream.get("duration") or data["format"]["duration"])

    return width, height, duration, fps


def get_crop_rect(
    zoom: float,
    region: str,
    video_width: int,
    video_height: int,
) -> tuple[int, int, int, int]:
    """Get crop rectangle for a zoom level and region.

    Returns: (crop_w, crop_h, crop_x, crop_y) - FFmpeg crop order
    """
    if zoom <= 1.0:
        return video_width, video_height, 0, 0

    region_data = ZOOM_REGIONS.get(region, ZOOM_REGIONS["viewport"])
    cx_frac, cy_frac, _, _ = region_data

    # Calculate crop size (smaller = more zoom)
    crop_w = int(video_width / zoom)
    crop_h = int(video_height / zoom)

    # Ensure even dimensions
    crop_w = crop_w - (crop_w % 2)
    crop_h = crop_h - (crop_h % 2)

    # Center crop on region
    region_center_x = int(video_width * cx_frac)
    region_center_y = int(video_height * cy_frac)

    crop_x = region_center_x - crop_w // 2
    crop_y = region_center_y - crop_h // 2

    # Clamp to video bounds
    crop_x = max(0, min(crop_x, video_width - crop_w))
    crop_y = max(0, min(crop_y, video_height - crop_h))

    return crop_w, crop_h, crop_x, crop_y


def build_segments(events: list[dict], duration: float) -> list[dict]:
    """Build list of segments with their zoom states.

    Each segment has: start, end, zoom, region, is_transition
    For transitions, also has: from_zoom, from_region, to_zoom, to_region
    """
    segments = []
    current_zoom = 1.0
    current_region = "viewport"
    last_time = 0.0

    for event in events:
        t = event["time"]
        d = event.get("duration", 0.4)

        # Static segment before this event
        if t > last_time + 0.01:
            segments.append({
                "start": last_time,
                "end": t,
                "zoom": current_zoom,
                "region": current_region,
                "is_transition": False,
            })

        # Transition segment
        if event["action"] == "zoom_in":
            segments.append({
                "start": t,
                "end": t + d,
                "from_zoom": current_zoom,
                "from_region": current_region,
                "to_zoom": event["zoom"],
                "to_region": event["region"],
                "is_transition": True,
            })
            current_zoom = event["zoom"]
            current_region = event["region"]
        else:  # zoom_out
            segments.append({
                "start": t,
                "end": t + d,
                "from_zoom": current_zoom,
                "from_region": current_region,
                "to_zoom": 1.0,
                "to_region": "viewport",
                "is_transition": True,
            })
            current_zoom = 1.0
            current_region = "viewport"

        last_time = t + d

    # Final segment
    if last_time < duration - 0.01:
        segments.append({
            "start": last_time,
            "end": duration,
            "zoom": current_zoom,
            "region": current_region,
            "is_transition": False,
        })

    return segments


def interpolate_rect(
    from_rect: tuple[int, int, int, int],
    to_rect: tuple[int, int, int, int],
    t: float,
) -> tuple[int, int, int, int]:
    """Interpolate between two crop rectangles (0 <= t <= 1)."""
    # Apply ease-out cubic for smoother motion
    t = 1 - pow(1 - t, 3)
    return (
        int(from_rect[0] + (to_rect[0] - from_rect[0]) * t),
        int(from_rect[1] + (to_rect[1] - from_rect[1]) * t),
        int(from_rect[2] + (to_rect[2] - from_rect[2]) * t),
        int(from_rect[3] + (to_rect[3] - from_rect[3]) * t),
    )


def process_transition_segment(
    input_video: Path,
    segment: dict,
    output_path: Path,
    video_width: int,
    video_height: int,
    output_width: int,
    output_height: int,
    fps: float,
) -> bool:
    """Process a transition using midpoint crop.

    Transitions are short (0.4s), so we just use the midpoint crop value.
    This avoids complex FFmpeg expressions that tend to fail.
    """
    start = segment["start"]
    end = segment["end"]
    duration = end - start

    from_rect = get_crop_rect(
        segment["from_zoom"], segment["from_region"],
        video_width, video_height
    )
    to_rect = get_crop_rect(
        segment["to_zoom"], segment["to_region"],
        video_width, video_height
    )

    # Use midpoint crop (with easing applied)
    mid_rect = interpolate_rect(from_rect, to_rect, 0.5)
    crop_w, crop_h, crop_x, crop_y = mid_rect

    # Ensure even dimensions
    crop_w = crop_w - (crop_w % 2)
    crop_h = crop_h - (crop_h % 2)

    vf = (
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", str(input_video),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-an", "-r", str(fps),
        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Transition failed: {e.stderr.decode()[:200]}", file=sys.stderr)
        return False


def process_segment(
    input_video: Path,
    segment: dict,
    output_path: Path,
    video_width: int,
    video_height: int,
    output_width: int,
    output_height: int,
    fps: float,
) -> bool:
    """Process a single segment with appropriate zoom."""
    start = segment["start"]
    end = segment["end"]
    duration = end - start

    if duration < 0.01:
        return False

    # For transitions, we'll handle them by splitting into sub-segments
    # and processing each with interpolated crop values
    if segment["is_transition"]:
        return process_transition_segment(
            input_video, segment, output_path,
            video_width, video_height, output_width, output_height, fps
        )

    # Static segment: simple crop and scale (preserving aspect ratio)
    crop_w, crop_h, crop_x, crop_y = get_crop_rect(
        segment["zoom"], segment["region"],
        video_width, video_height
    )

    # Scale preserving aspect ratio, then pad to exact output size
    vf = (
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", str(input_video),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-an",  # No audio for segments, we'll add it back at the end
        "-r", str(fps),
        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Segment processing failed: {e.stderr.decode()[:500]}", file=sys.stderr)
        return False


def apply_zoom(
    input_video: Path,
    events_file: Path,
    output_video: Path,
    output_width: int = 1920,
    output_height: int = 1080,
) -> bool:
    """Apply zoom effects to video based on events file."""
    # Load events
    try:
        with open(events_file) as f:
            events = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading events file: {e}", file=sys.stderr)
        return False

    if not events:
        print("No zoom events found, just scaling video")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(input_video),
            "-vf", f"scale={output_width}:{output_height}:flags=lanczos",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-c:a", "copy",
            str(output_video)
        ], check=True)
        return True

    # Get video info
    try:
        width, height, duration, fps = get_video_info(input_video)
    except subprocess.CalledProcessError as e:
        print(f"Error getting video info: {e}", file=sys.stderr)
        return False

    print(f"Input video: {width}x{height}, {duration:.1f}s, {fps:.2f}fps")
    print(f"Output: {output_width}x{output_height}")
    print(f"Zoom events: {len(events)}")

    # Build segments
    segments = build_segments(events, duration)
    print(f"Processing {len(segments)} segments...")

    # Process each segment
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        segment_files = []

        for i, seg in enumerate(segments):
            seg_file = tmpdir / f"seg_{i:04d}.mp4"
            print(f"  Segment {i+1}/{len(segments)}: {seg['start']:.2f}s - {seg['end']:.2f}s", end="")

            if seg["is_transition"]:
                print(f" (transition)")
            else:
                print(f" (zoom {seg['zoom']}x)")

            if process_segment(
                input_video, seg, seg_file,
                width, height, output_width, output_height, fps
            ):
                segment_files.append(seg_file)
            else:
                print(f"    Warning: segment {i} failed, skipping")

        if not segment_files:
            print("No segments processed successfully", file=sys.stderr)
            return False

        # Create concat list
        concat_list = tmpdir / "concat.txt"
        with open(concat_list, "w") as f:
            for sf in segment_files:
                f.write(f"file '{sf}'\n")

        # Concatenate video segments
        print("Concatenating segments...")
        concat_video = tmpdir / "concat.mp4"
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            str(concat_video)
        ], check=True, capture_output=True)

        # Add audio from original
        print("Adding audio...")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(concat_video),
            "-i", str(input_video),
            "-map", "0:v",
            "-map", "1:a?",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_video)
        ], check=True, capture_output=True)

    print(f"Output: {output_video}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Apply dynamic zoom effects to demo recordings"
    )
    parser.add_argument("input", type=Path, help="Input video file")
    parser.add_argument("events", type=Path, help="Zoom events JSON file")
    parser.add_argument("output", type=Path, help="Output video file")
    parser.add_argument(
        "--width", type=int, default=1920,
        help="Output width (default: 1920)"
    )
    parser.add_argument(
        "--height", type=int, default=1080,
        help="Output height (default: 1080)"
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input video not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if not args.events.exists():
        print(f"Events file not found: {args.events}", file=sys.stderr)
        sys.exit(1)

    success = apply_zoom(
        args.input, args.events, args.output,
        args.width, args.height
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
