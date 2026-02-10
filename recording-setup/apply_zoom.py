#!/usr/bin/env python3
"""Apply dynamic zoom effects to demo recordings.

Reads zoom events from a JSON sidecar file and applies smooth crop/scale
transitions via a single FFmpeg command. Uses time-based expressions in
FFmpeg's crop filter for per-frame interpolation with smoothstep easing.

Usage:
    python apply_zoom.py input.mp4 zoom_events.json output.mp4
    python apply_zoom.py input.mp4 zoom_events.json output.mp4 --debug-keyframes

The zoom events JSON format:
    [
        {"time": 2.5, "action": "zoom_in", "region": "input", "zoom": 1.5, "duration": 0.2},
        {"time": 8.0, "action": "zoom_out", "duration": 0.2},
        {"time": 5.0, "action": "pan_to", "y": 0.32, "duration": 0.3}
    ]
"""

import argparse
import json
import subprocess
import sys
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

    Returns: (crop_w, crop_h, crop_x, crop_y) in FFmpeg crop order
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


# Keyframe: (time, crop_w, crop_h, crop_x, crop_y)
Keyframe = tuple[float, int, int, int, int]


def build_keyframes(
    events: list[dict],
    video_width: int,
    video_height: int,
    video_duration: float,
) -> list[Keyframe]:
    """Convert zoom events into a list of keyframes.

    Each zoom_in/zoom_out produces two keyframes (transition start + end).
    pan_to events also produce two keyframes (start + end of pan).

    Returns sorted list of (time, crop_w, crop_h, crop_x, crop_y) tuples.
    """
    keyframes: list[Keyframe] = []

    # Start at full frame
    full_rect = (video_width, video_height, 0, 0)
    current_rect = full_rect
    current_zoom = 1.0
    current_region = "viewport"

    for event in events:
        t = event["time"]
        d = event.get("duration", 0.4)

        if event["action"] == "zoom_in":
            # Keyframe at transition start: current state
            keyframes.append((t, *current_rect))

            # Compute target rect
            target_rect = get_crop_rect(
                event["zoom"], event["region"],
                video_width, video_height,
            )

            # Keyframe at transition end: zoomed state
            keyframes.append((t + d, *target_rect))

            current_rect = target_rect
            current_zoom = event["zoom"]
            current_region = event["region"]

        elif event["action"] == "zoom_out":
            # Keyframe at transition start: current state
            keyframes.append((t, *current_rect))

            # Keyframe at transition end: full frame
            keyframes.append((t + d, *full_rect))

            current_rect = full_rect
            current_zoom = 1.0
            current_region = "viewport"

        elif event["action"] == "pan_to":
            # Pan changes x/y while keeping w/h (staying at current zoom)
            keyframes.append((t, *current_rect))

            # Compute new position from fractional coordinates
            new_x = current_rect[2]  # default: keep current x
            new_y = current_rect[3]  # default: keep current y
            crop_w = current_rect[0]
            crop_h = current_rect[1]

            if "y" in event:
                center_y = int(video_height * event["y"])
                new_y = center_y - crop_h // 2
                new_y = max(0, min(new_y, video_height - crop_h))

            if "x" in event:
                center_x = int(video_width * event["x"])
                new_x = center_x - crop_w // 2
                new_x = max(0, min(new_x, video_width - crop_w))

            target_rect = (crop_w, crop_h, new_x, new_y)
            keyframes.append((t + d, *target_rect))

            current_rect = target_rect

    # Ensure we have keyframes at t=0 and t=end
    times = [kf[0] for kf in keyframes]
    if not times or times[0] > 0.001:
        keyframes.insert(0, (0.0, *full_rect))
    if not times or times[-1] < video_duration - 0.001:
        keyframes.append((video_duration, *current_rect))

    # Sort by time (should already be sorted, but be safe)
    keyframes.sort(key=lambda kf: kf[0])

    return keyframes


def build_crop_expr(keyframes: list[Keyframe], param_index: int) -> str:
    """Generate a nested if(lt(t,...)) FFmpeg expression for one crop parameter.

    param_index: 0=w, 1=h, 2=x, 3=y (offset by 1 since keyframe[0] is time)

    Uses smoothstep easing (t*t*(3-2*t)) for transitions between keyframes.
    Static holds between transitions use constant values.
    """
    if not keyframes:
        return "0"

    if len(keyframes) == 1:
        return str(keyframes[0][param_index + 1])

    # Identify transition pairs: consecutive keyframes with different values
    # and small time gaps are transitions. Consecutive keyframes with same
    # values are static holds.
    #
    # We build a piecewise expression: for each time range, either hold a
    # constant or interpolate.
    parts = []
    for i in range(len(keyframes) - 1):
        t_start = keyframes[i][0]
        t_end = keyframes[i + 1][0]
        v_start = keyframes[i][param_index + 1]
        v_end = keyframes[i + 1][param_index + 1]

        if v_start == v_end:
            # Static hold
            parts.append((t_start, t_end, v_start, v_end, False))
        else:
            # Transition (animate)
            parts.append((t_start, t_end, v_start, v_end, True))

    # Build nested if expression from right to left
    # Final value (after last keyframe)
    expr = str(keyframes[-1][param_index + 1])

    for t_start, t_end, v_start, v_end, is_transition in reversed(parts):
        if is_transition:
            # Smoothstep interpolation
            # progress = (t - t_start) / (t_end - t_start), clamped 0-1
            # smoothstep = p*p*(3-2*p)
            # value = v_start + (v_end - v_start) * smoothstep
            dt = t_end - t_start
            dv = v_end - v_start
            # p = clip((t-{t_start})/{dt}, 0, 1)
            # smoothstep(p) = p*p*(3-2*p)
            # result = {v_start} + {dv} * smoothstep(p)
            p_expr = f"clip((t-{t_start:.4f})/{dt:.4f},0,1)"
            smooth_expr = f"({p_expr}*{p_expr}*(3-2*{p_expr}))"
            lerp_expr = f"({v_start}+{dv}*{smooth_expr})"
            # Ensure even values for w and h (param_index 0 and 1)
            if param_index <= 1:
                lerp_expr = f"bitand(trunc({lerp_expr}),not(1))"
            else:
                lerp_expr = f"trunc({lerp_expr})"
            expr = f"if(lt(t,{t_end:.4f}),{lerp_expr},{expr})"
        else:
            # Static: just hold the value until the next segment
            expr = f"if(lt(t,{t_end:.4f}),{v_start},{expr})"

    return expr


def apply_zoom(
    input_video: Path,
    events_file: Path,
    output_video: Path,
    output_width: int = 1920,
    output_height: int = 1080,
    debug_keyframes: bool = False,
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

    # Build keyframes
    keyframes = build_keyframes(events, width, height, duration)
    print(f"Keyframes: {len(keyframes)}")

    if debug_keyframes:
        print()
        print(f"{'Time':>8s}  {'Width':>6s}  {'Height':>6s}  {'X':>6s}  {'Y':>6s}")
        print(f"{'─'*8}  {'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}")
        for t, w, h, x, y in keyframes:
            print(f"{t:8.3f}  {w:6d}  {h:6d}  {x:6d}  {y:6d}")
        print()

    # Build crop expressions
    w_expr = build_crop_expr(keyframes, 0)
    h_expr = build_crop_expr(keyframes, 1)
    x_expr = build_crop_expr(keyframes, 2)
    y_expr = build_crop_expr(keyframes, 3)

    # Single FFmpeg command with expression-based crop
    vf = (
        f"crop=w='{w_expr}':h='{h_expr}':x='{x_expr}':y='{y_expr}',"
        f"scale={output_width}:{output_height}:flags=lanczos"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-c:a", "copy",
        str(output_video)
    ]

    print("Applying zoom (single-pass)...")

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg failed: {e.stderr.decode()[:500]}", file=sys.stderr)
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
    parser.add_argument(
        "--debug-keyframes", action="store_true",
        help="Print computed keyframes table"
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
        args.width, args.height,
        debug_keyframes=args.debug_keyframes,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
