#!/usr/bin/env python3
"""Apply dynamic zoom effects to demo recordings.

Reads zoom events from a JSON sidecar file and applies smooth crop/scale
transitions via FFmpeg. Designed for high-resolution recordings that will
be output at 1080p.

Usage:
    python apply_zoom.py input.mp4 zoom_events.json output.mp4

The zoom events JSON format:
    [
        {"time": 2.5, "action": "zoom_in", "region": "input", "zoom": 1.5, "duration": 0.4},
        {"time": 8.0, "action": "zoom_out", "duration": 0.4}
    ]

Zoom regions are defined in purple_tui/constants.py as percentages:
    (x_center, y_center, width_fraction, height_fraction)
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

# Add parent to path to import constants
sys.path.insert(0, str(Path(__file__).parent.parent))
from purple_tui.constants import ZOOM_REGIONS


def ease_out_cubic(t: float) -> float:
    """Ease-out cubic: fast start, gentle finish. Good for zoom-in."""
    return 1 - pow(1 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    """Ease-in-out cubic: smooth start and finish. Good for zoom-out."""
    if t < 0.5:
        return 4 * t * t * t
    else:
        return 1 - pow(-2 * t + 2, 3) / 2


def get_video_info(video_path: Path) -> tuple[int, int, float, float]:
    """Get video dimensions, duration, and framerate.

    Returns: (width, height, duration_seconds, fps)
    """
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

    # Parse framerate (may be "30/1" or "29.97")
    fps_str = stream["r_frame_rate"]
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)

    # Duration from stream or format
    duration = float(stream.get("duration") or data["format"]["duration"])

    return width, height, duration, fps


def calculate_crop_at_time(
    t: float,
    events: list[dict],
    video_width: int,
    video_height: int,
) -> tuple[int, int, int, int]:
    """Calculate crop rectangle at a given time.

    Returns: (crop_x, crop_y, crop_w, crop_h)
    """
    # Find current zoom state by scanning events
    current_zoom = 1.0
    current_region = "viewport"
    transition_start = 0.0
    transition_end = 0.0
    target_zoom = 1.0
    target_region = "viewport"
    ease_func = ease_out_cubic

    for event in events:
        event_time = event["time"]
        duration = event.get("duration", 0.4)

        if event["action"] == "zoom_in":
            if t >= event_time + duration:
                # Transition complete
                current_zoom = event["zoom"]
                current_region = event["region"]
            elif t >= event_time:
                # Mid-transition
                transition_start = event_time
                transition_end = event_time + duration
                target_zoom = event["zoom"]
                target_region = event["region"]
                ease_func = ease_out_cubic
            # Before this event: use previous state

        elif event["action"] == "zoom_out":
            if t >= event_time + duration:
                current_zoom = 1.0
                current_region = "viewport"
            elif t >= event_time:
                transition_start = event_time
                transition_end = event_time + duration
                target_zoom = 1.0
                target_region = "viewport"
                ease_func = ease_in_out_cubic

    # Check if we're in a transition
    if transition_start < t < transition_end:
        progress = (t - transition_start) / (transition_end - transition_start)
        eased = ease_func(progress)

        # Interpolate between current and target
        from_rect = get_crop_rect(current_zoom, current_region, video_width, video_height)
        to_rect = get_crop_rect(target_zoom, target_region, video_width, video_height)

        crop_x = int(from_rect[0] + (to_rect[0] - from_rect[0]) * eased)
        crop_y = int(from_rect[1] + (to_rect[1] - from_rect[1]) * eased)
        crop_w = int(from_rect[2] + (to_rect[2] - from_rect[2]) * eased)
        crop_h = int(from_rect[3] + (to_rect[3] - from_rect[3]) * eased)

        # Ensure even dimensions (required by many codecs)
        crop_w = crop_w - (crop_w % 2)
        crop_h = crop_h - (crop_h % 2)

        return crop_x, crop_y, crop_w, crop_h

    # Not in transition, use current state
    return get_crop_rect(current_zoom, current_region, video_width, video_height)


def get_crop_rect(
    zoom: float,
    region: str,
    video_width: int,
    video_height: int,
) -> tuple[int, int, int, int]:
    """Get crop rectangle for a zoom level and region.

    Returns: (crop_x, crop_y, crop_w, crop_h)
    """
    if zoom <= 1.0:
        return 0, 0, video_width, video_height

    # Get region center and size (as fractions)
    region_data = ZOOM_REGIONS.get(region, ZOOM_REGIONS["viewport"])
    cx_frac, cy_frac, w_frac, h_frac = region_data

    # Calculate crop size (smaller = more zoom)
    crop_w = int(video_width / zoom)
    crop_h = int(video_height / zoom)

    # Ensure even dimensions
    crop_w = crop_w - (crop_w % 2)
    crop_h = crop_h - (crop_h % 2)

    # Calculate crop position centered on region
    # First, find the pixel position of the region center
    region_center_x = int(video_width * cx_frac)
    region_center_y = int(video_height * cy_frac)

    # Center the crop on this point
    crop_x = region_center_x - crop_w // 2
    crop_y = region_center_y - crop_h // 2

    # Clamp to video bounds
    crop_x = max(0, min(crop_x, video_width - crop_w))
    crop_y = max(0, min(crop_y, video_height - crop_h))

    return crop_x, crop_y, crop_w, crop_h


def generate_filter_complex(
    events: list[dict],
    video_width: int,
    video_height: int,
    duration: float,
    fps: float,
    output_width: int = 1920,
    output_height: int = 1080,
) -> str:
    """Generate FFmpeg filter_complex for zooming.

    Uses sendcmd to dynamically update crop parameters frame-by-frame.
    """
    if not events:
        # No zoom events, just scale to output
        return f"scale={output_width}:{output_height}:flags=lanczos"

    # Generate keyframes at regular intervals for smooth transitions
    # Use finer granularity during transitions
    keyframes = []

    # Find all transition periods
    transition_times = set()
    for event in events:
        t = event["time"]
        d = event.get("duration", 0.4)
        # Add keyframes at 30fps during transitions
        for i in range(int(d * 30) + 1):
            transition_times.add(round(t + i / 30, 3))

    # Add keyframes at transition boundaries and every second otherwise
    all_times = set(transition_times)
    for t in range(int(duration) + 1):
        all_times.add(float(t))

    # Sort and generate crop commands
    sorted_times = sorted(all_times)

    # Instead of sendcmd (which is complex), we'll use zoompan filter
    # But zoompan doesn't support variable zoom well.
    #
    # Best approach: use a series of trim+crop+concat
    # For simplicity, let's segment the video and apply fixed crops per segment

    # Find segments between zoom changes
    segments = []
    current_zoom = 1.0
    current_region = "viewport"
    last_time = 0.0

    for event in events:
        t = event["time"]
        d = event.get("duration", 0.4)

        # Segment before this event (at current zoom)
        if t > last_time:
            segments.append({
                "start": last_time,
                "end": t,
                "zoom": current_zoom,
                "region": current_region,
                "transition": False,
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
                "transition": True,
                "ease": "out",
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
                "transition": True,
                "ease": "inout",
            })
            current_zoom = 1.0
            current_region = "viewport"

        last_time = t + d

    # Final segment after last event
    if last_time < duration:
        segments.append({
            "start": last_time,
            "end": duration,
            "zoom": current_zoom,
            "region": current_region,
            "transition": False,
        })

    # For transitions, we need to use zoompan or a complex filter
    # Let's use a simpler approach: generate a filter that samples
    # crop coordinates at each frame using expressions

    # The zoompan filter can do this with expressions
    # zoom = current zoom level (1 = no zoom, 2 = 2x)
    # x, y = pan position

    # Actually, the cleanest approach is to use crop with expressions
    # that evaluate the zoom state at each frame

    # Generate crop expression
    # We'll build a piecewise expression using if() statements

    def build_expr(coord: str) -> str:
        """Build expression for a crop coordinate (x, y, w, or h)."""
        # Start with default (no zoom)
        if coord == "w":
            default = str(video_width)
        elif coord == "h":
            default = str(video_height)
        else:
            default = "0"

        expr_parts = []

        for seg in segments:
            start = seg["start"]
            end = seg["end"]

            if seg["transition"]:
                # Transition: interpolate
                from_rect = get_crop_rect(
                    seg["from_zoom"], seg["from_region"],
                    video_width, video_height
                )
                to_rect = get_crop_rect(
                    seg["to_zoom"], seg["to_region"],
                    video_width, video_height
                )

                idx = {"x": 0, "y": 1, "w": 2, "h": 3}[coord]
                from_val = from_rect[idx]
                to_val = to_rect[idx]

                # Progress within transition
                # t is frame time, start/end are segment bounds
                # progress = (t - start) / (end - start)

                # Apply easing
                if seg["ease"] == "out":
                    # ease_out_cubic: 1 - (1-p)^3
                    eased = f"(1 - pow(1 - (t - {start}) / {end - start}, 3))"
                else:
                    # ease_in_out_cubic
                    p = f"((t - {start}) / {end - start})"
                    eased = f"if(lt({p}, 0.5), 4 * pow({p}, 3), 1 - pow(-2 * {p} + 2, 3) / 2)"

                # Interpolate: from + (to - from) * eased
                val_expr = f"({from_val} + ({to_val} - {from_val}) * {eased})"

                # Wrap in time condition
                condition = f"gte(t, {start})*lt(t, {end})"
                expr_parts.append(f"({condition}) * {val_expr}")

            else:
                # Static: fixed zoom
                rect = get_crop_rect(seg["zoom"], seg["region"], video_width, video_height)
                idx = {"x": 0, "y": 1, "w": 2, "h": 3}[coord]
                val = rect[idx]

                condition = f"gte(t, {start})*lt(t, {end})"
                expr_parts.append(f"({condition}) * {val}")

        # Combine all parts (only one will be non-zero at any time)
        if expr_parts:
            return " + ".join(expr_parts)
        return default

    # Build the filter
    x_expr = build_expr("x")
    y_expr = build_expr("y")
    w_expr = build_expr("w")
    h_expr = build_expr("h")

    # Make dimensions even (required for encoding)
    w_expr = f"floor(({w_expr})/2)*2"
    h_expr = f"floor(({h_expr})/2)*2"

    # Crop then scale to output
    filter_complex = (
        f"crop=w='{w_expr}':h='{h_expr}':x='{x_expr}':y='{y_expr}',"
        f"scale={output_width}:{output_height}:flags=lanczos"
    )

    return filter_complex


def apply_zoom(
    input_video: Path,
    events_file: Path,
    output_video: Path,
    output_width: int = 1920,
    output_height: int = 1080,
) -> bool:
    """Apply zoom effects to video based on events file.

    Returns: True on success, False on failure
    """
    # Load events
    try:
        with open(events_file) as f:
            events = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading events file: {e}", file=sys.stderr)
        return False

    if not events:
        print("No zoom events found, copying video as-is")
        # Just scale to output dimensions
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

    # Generate filter
    filter_complex = generate_filter_complex(
        events, width, height, duration, fps,
        output_width, output_height
    )

    # Apply filter
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-vf", filter_complex,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "copy",
        str(output_video)
    ]

    print("Applying zoom effects...")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg failed: {e}", file=sys.stderr)
        return False

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
