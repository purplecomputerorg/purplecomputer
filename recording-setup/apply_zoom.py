#!/usr/bin/env python3
"""Apply dynamic zoom effects to demo recordings.

Reads zoom events from a JSON sidecar file and applies smooth zoom/pan
transitions via a single FFmpeg command. Uses the zoompan filter with
per-frame expressions and smoothstep easing.

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
import os
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

# ZoomKeyframe: (time, zoom_level, x, y)
ZoomKeyframe = tuple[float, float, int, int]


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


def keyframes_to_zoom(
    keyframes: list[Keyframe],
    video_width: int,
) -> list[ZoomKeyframe]:
    """Convert crop keyframes to zoompan keyframes (zoom_level, x, y).

    zoom_level = video_width / crop_w (1.0 = no zoom, 3.0 = 3x zoom)
    x, y = top-left of visible region in input pixel coordinates
    """
    zoom_kf: list[ZoomKeyframe] = []
    for t, w, h, x, y in keyframes:
        z = video_width / w if w > 0 else 1.0
        zoom_kf.append((t, z, x, y))
    return zoom_kf


def build_zoompan_expr(
    zoom_keyframes: list[ZoomKeyframe],
    param: str,
) -> str:
    """Generate a nested if() expression for a zoompan parameter.

    param: 'z' (zoom level), 'x', or 'y'
    Uses 'in_time' as the time variable (zoompan's input timestamp).
    Uses smoothstep easing for transitions.
    """
    if not zoom_keyframes:
        return "1" if param == "z" else "0"

    if len(zoom_keyframes) == 1:
        kf = zoom_keyframes[0]
        if param == "z":
            return f"{kf[1]:.6f}"
        elif param == "x":
            return str(kf[2])
        else:
            return str(kf[3])

    # Map param to index in ZoomKeyframe
    idx = {"z": 1, "x": 2, "y": 3}[param]
    is_float = (param == "z")
    time_var = "in_time"

    # Build piecewise expression
    parts = []
    for i in range(len(zoom_keyframes) - 1):
        t_start = zoom_keyframes[i][0]
        t_end = zoom_keyframes[i + 1][0]
        v_start = zoom_keyframes[i][idx]
        v_end = zoom_keyframes[i + 1][idx]

        # For floats, use approximate equality check
        if is_float:
            same = abs(v_start - v_end) < 0.001
        else:
            same = (v_start == v_end)

        parts.append((t_start, t_end, v_start, v_end, not same))

    # Build nested if expression from right to left
    last_val = zoom_keyframes[-1][idx]
    expr = f"{last_val:.6f}" if is_float else str(last_val)

    for t_start, t_end, v_start, v_end, is_transition in reversed(parts):
        if is_transition:
            dt = t_end - t_start
            if is_float:
                dv = v_end - v_start
                p = f"clip(({time_var}-{t_start:.4f})/{dt:.4f},0,1)"
                smooth = f"({p}*{p}*(3-2*{p}))"
                lerp = f"({v_start:.6f}+{dv:.6f}*{smooth})"
            else:
                dv = v_end - v_start
                p = f"clip(({time_var}-{t_start:.4f})/{dt:.4f},0,1)"
                smooth = f"({p}*{p}*(3-2*{p}))"
                lerp = f"trunc({v_start}+{dv}*{smooth})"
            expr = f"if(lt({time_var},{t_end:.4f}),{lerp},{expr})"
        else:
            val = f"{v_start:.6f}" if is_float else str(v_start)
            expr = f"if(lt({time_var},{t_end:.4f}),{val},{expr})"

    return expr


# Keep old build_crop_expr for tests (it's still correct math, just not for crop w/h)
def build_crop_expr(keyframes: list[Keyframe], param_index: int) -> str:
    """Generate a nested if(lt(t,...)) FFmpeg expression for one crop parameter.

    param_index: 0=w, 1=h, 2=x, 3=y (offset by 1 since keyframe[0] is time)

    Note: FFmpeg's crop filter only evaluates x/y per frame, not w/h.
    For actual zoom effects, use build_zoompan_expr() instead.
    """
    if not keyframes:
        return "0"

    if len(keyframes) == 1:
        return str(keyframes[0][param_index + 1])

    parts = []
    for i in range(len(keyframes) - 1):
        t_start = keyframes[i][0]
        t_end = keyframes[i + 1][0]
        v_start = keyframes[i][param_index + 1]
        v_end = keyframes[i + 1][param_index + 1]

        if v_start == v_end:
            parts.append((t_start, t_end, v_start, v_end, False))
        else:
            parts.append((t_start, t_end, v_start, v_end, True))

    expr = str(keyframes[-1][param_index + 1])

    for t_start, t_end, v_start, v_end, is_transition in reversed(parts):
        if is_transition:
            dt = t_end - t_start
            dv = v_end - v_start
            p_expr = f"clip((t-{t_start:.4f})/{dt:.4f},0,1)"
            smooth_expr = f"({p_expr}*{p_expr}*(3-2*{p_expr}))"
            lerp_expr = f"({v_start}+{dv}*{smooth_expr})"
            if param_index <= 1:
                lerp_expr = f"trunc({lerp_expr}/2)*2"
            else:
                lerp_expr = f"trunc({lerp_expr})"
            expr = f"if(lt(t,{t_end:.4f}),{lerp_expr},{expr})"
        else:
            expr = f"if(lt(t,{t_end:.4f}),{v_start},{expr})"

    return expr


def apply_zoom(
    input_video: Path,
    events_file: Path,
    output_video: Path,
    output_width: int | None = None,
    output_height: int | None = None,
    debug_keyframes: bool = False,
) -> bool:
    """Apply zoom effects to video using zoompan filter.

    Output defaults to input video dimensions (preserving aspect ratio).
    Writes detailed debug info to apply_zoom_debug.log next to output.
    """
    # Set up debug log next to output file
    log_path = output_video.parent / "apply_zoom_debug.log"
    log_lines: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        log_lines.append(msg)

    def write_log() -> None:
        try:
            with open(log_path, "w") as f:
                f.write("\n".join(log_lines) + "\n")
            print(f"Debug log: {log_path}")
        except OSError:
            pass

    log(f"=== apply_zoom debug log ===")
    log(f"Input video: {input_video}")
    log(f"Events file: {events_file}")
    log(f"Output video: {output_video}")

    # Load events
    try:
        with open(events_file) as f:
            raw = f.read()
        events = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        log(f"ERROR reading events file: {e}")
        write_log()
        return False

    log(f"Events file contents:\n{raw.strip()}")

    # Get video info (needed for dimensions even with no events)
    try:
        width, height, duration, fps = get_video_info(input_video)
    except subprocess.CalledProcessError as e:
        log(f"ERROR getting video info: {e}")
        write_log()
        return False

    log(f"Video info: {width}x{height}, {duration:.2f}s, {fps:.2f}fps")

    # Default output to input dimensions
    if output_width is None:
        output_width = width
    if output_height is None:
        output_height = height

    log(f"Output dimensions: {output_width}x{output_height}")

    if not events:
        log("No zoom events found, copying video")
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(input_video),
            "-c:v", "copy",
            "-c:a", "copy",
            str(output_video)
        ], check=True)
        write_log()
        return True

    log(f"Zoom events: {len(events)}")
    for i, ev in enumerate(events):
        log(f"  Event {i}: {ev}")

    # Build crop keyframes, then convert to zoom keyframes
    keyframes = build_keyframes(events, width, height, duration)
    zoom_keyframes = keyframes_to_zoom(keyframes, width)
    log(f"Keyframes: {len(zoom_keyframes)}")

    log(f"{'Time':>8s}  {'Zoom':>8s}  {'X':>6s}  {'Y':>6s}")
    log(f"{'─'*8}  {'─'*8}  {'─'*6}  {'─'*6}")
    for t, z, x, y in zoom_keyframes:
        log(f"{t:8.3f}  {z:8.3f}  {x:6d}  {y:6d}")

    # Build zoompan expressions
    z_expr = build_zoompan_expr(zoom_keyframes, "z")
    x_expr = build_zoompan_expr(zoom_keyframes, "x")
    y_expr = build_zoompan_expr(zoom_keyframes, "y")

    log(f"\nZoompan expressions:")
    log(f"  z: {z_expr[:200]}{'...' if len(z_expr) > 200 else ''}")
    log(f"  x: {x_expr[:200]}{'...' if len(x_expr) > 200 else ''}")
    log(f"  y: {y_expr[:200]}{'...' if len(y_expr) > 200 else ''}")
    log(f"  Lengths: z={len(z_expr)} x={len(x_expr)} y={len(y_expr)}")

    # zoompan: d=1 means 1 output frame per input frame (video passthrough)
    # s=WxH sets output resolution, fps matches input
    fps_int = round(fps)
    zoompan = (
        f"zoompan=z='{z_expr}'"
        f":x='{x_expr}'"
        f":y='{y_expr}'"
        f":d=1"
        f":s={output_width}x{output_height}"
        f":fps={fps_int}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-vf", zoompan,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "copy",
        str(output_video)
    ]

    log(f"\nFFmpeg command (args):")
    for i, arg in enumerate(cmd):
        if arg == zoompan:
            log(f"  [{i}] <zoompan filter, {len(zoompan)} chars>")
        else:
            log(f"  [{i}] {arg}")

    # Write the full filter string to a separate file for inspection
    vf_path = output_video.parent / "apply_zoom_vf.txt"
    try:
        with open(vf_path, "w") as f:
            f.write(zoompan)
        log(f"Full filter written to: {vf_path}")
    except OSError:
        pass

    log(f"\nApplying zoom (single-pass)...")
    log(f"Video duration: {duration:.1f}s. Watch 'time=' in FFmpeg output for progress.")

    # Let FFmpeg print progress to terminal (stderr passthrough)
    ffmpeg_log_path = output_video.parent / "apply_zoom_ffmpeg.log"
    try:
        with open(ffmpeg_log_path, "w") as ffmpeg_log_f:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stderr_data = b""
            while True:
                chunk = proc.stderr.read(4096)
                if not chunk:
                    break
                stderr_data += chunk
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
                ffmpeg_log_f.write(chunk.decode(errors="replace"))
            proc.wait()

        stderr = stderr_data.decode(errors="replace")
        if proc.returncode != 0:
            log(f"FFmpeg FAILED (exit code {proc.returncode}):\n{stderr[:2000]}")
            log(f"Full FFmpeg log: {ffmpeg_log_path}")
            write_log()
            return False
        else:
            log(f"FFmpeg completed successfully")
            if stderr:
                log(f"FFmpeg log: {ffmpeg_log_path}")
    except OSError as e:
        log(f"Failed to run FFmpeg: {e}")
        write_log()
        return False

    # Check output
    if output_video.exists():
        size_mb = output_video.stat().st_size / (1024 * 1024)
        log(f"Output created: {output_video} ({size_mb:.1f} MB)")
        try:
            ow, oh, od, ofps = get_video_info(output_video)
            log(f"Output video info: {ow}x{oh}, {od:.2f}s, {ofps:.2f}fps")
        except Exception as ex:
            log(f"Could not probe output: {ex}")
    else:
        log(f"ERROR: output file was not created!")

    write_log()
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Apply dynamic zoom effects to demo recordings"
    )
    parser.add_argument("input", type=Path, help="Input video file")
    parser.add_argument("events", type=Path, help="Zoom events JSON file")
    parser.add_argument("output", type=Path, help="Output video file")
    parser.add_argument(
        "--width", type=int, default=None,
        help="Output width (default: same as input)"
    )
    parser.add_argument(
        "--height", type=int, default=None,
        help="Output height (default: same as input)"
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
