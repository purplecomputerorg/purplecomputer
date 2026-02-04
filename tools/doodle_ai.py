#!/usr/bin/env python3
"""
AI-assisted Doodle Mode drawing generator.

Uses the REAL Purple Computer app with visual feedback:
1. Run the real app in a PTY with PURPLE_DEV_MODE=1
2. Send real keypresses
3. Press F8 to take screenshots (SVG)
4. Convert to PNG, send to Claude vision
5. Get next actions, execute them
6. Repeat until drawing is complete

This ensures the AI learns from the ACTUAL app behavior.

Usage:
    python tools/doodle_ai.py --goal "a tree with green leaves"
    python tools/doodle_ai.py --goal "sunset landscape" --iterations 10

    # Use a reference image
    python tools/doodle_ai.py --goal "a palm tree" --reference photo.png

    # Refine a previous run's plan
    python tools/doodle_ai.py --refine doodle_ai_output/20260203_143022 --instruction "add a bird"
"""

import argparse
import base64
import io
import json
import os
import pty
import random
import re
import select
import struct
import subprocess
import sys
import termios
import fcntl
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from purple_tui.doodle_config import (
    CANVAS_WIDTH, CANVAS_HEIGHT,
    describe_canvas, describe_colors, describe_colors_brief,
)


# =============================================================================
# ROBUST JSON PARSING
# =============================================================================

def parse_json_robust(text: str) -> dict | list | None:
    """Parse JSON from text with fallbacks for common issues.

    Handles:
    - JSON inside markdown code blocks
    - Trailing commas
    - Truncated JSON (attempts to close brackets)
    - Comments (// style)
    """

    # Try to extract from markdown code block first
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if code_block_match:
        text = code_block_match.group(1)

    # Find the JSON object or array
    start_obj = text.find('{')
    start_arr = text.find('[')

    if start_obj < 0 and start_arr < 0:
        return None

    # Determine if we're looking for object or array
    if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
        start = start_arr
        open_char, close_char = '[', ']'
    else:
        start = start_obj
        open_char, close_char = '{', '}'

    # Find matching end by counting brackets
    depth = 0
    end = start
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if char == '\\' and in_string:
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if depth != 0:
        # Truncated JSON - try to close it
        json_text = text[start:end] if end > start else text[start:]
        # Add missing closing brackets
        json_text += close_char * depth
    else:
        json_text = text[start:end]

    # Clean up common issues
    # Remove trailing commas before ] or }
    json_text = re.sub(r',\s*([}\]])', r'\1', json_text)
    # Remove // comments (but not inside strings - simplified)
    json_text = re.sub(r'//[^\n]*\n', '\n', json_text)

    # Try to parse
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"[JSON Parse] First attempt failed: {e}")
        print(f"[JSON Parse] Extracted text length: {len(json_text)}, depth was: {depth}")
        # Show where the error is
        if hasattr(e, 'pos') and e.pos:
            context_start = max(0, e.pos - 50)
            context_end = min(len(json_text), e.pos + 50)
            print(f"[JSON Parse] Context around error: ...{json_text[context_start:context_end]}...")

    # Last resort: try to extract just the actions array
    actions_match = re.search(r'"actions"\s*:\s*(\[[\s\S]*?\])(?=\s*[,}]|$)', text)
    if actions_match:
        try:
            actions_text = actions_match.group(1)
            # Clean trailing commas
            actions_text = re.sub(r',\s*([}\]])', r'\1', actions_text)
            actions = json.loads(actions_text)
            print(f"[JSON Parse] Fallback extraction got {len(actions)} actions")
            return {"actions": actions}
        except json.JSONDecodeError as e:
            print(f"[JSON Parse] Fallback also failed: {e}")

    return None


# =============================================================================
# COMPACT ACTION FORMAT PARSER
# =============================================================================

def _extract_color_and_coords(line: str, start: int) -> tuple[str, str]:
    """Extract color key and coordinate string from a compact action line.

    The color key is everything between start and the first digit (or minus sign
    for negative coords). This handles the AI occasionally outputting multi-character
    color keys like 're' instead of just 'r'.

    Returns (color_key, coords_string). The color_key is the last character before
    digits, since that's the most likely intended single-char color key.
    """
    i = start
    while i < len(line) and not line[i].isdigit() and line[i] != '-':
        i += 1
    # Use the last non-digit character as the color key
    color = line[i - 1] if i > start else line[start]
    coords_str = line[i:]
    return color, coords_str


def parse_compact_actions(text: str) -> list[dict] | None:
    """Parse compact DSL action format into full action dictionaries.

    Compact format (one per line):
    - L<color><x1>,<y1>,<x2>,<y2>  → paint_line (horizontal or vertical)
    - P<color><x>,<y>              → paint_at

    Lines are expanded into individual paint_at commands for the controller.

    Examples:
        Lf10,5,50,5   → horizontal line from (10,5) to (50,5) in yellow
        Lf20,0,20,24  → vertical line from (20,0) to (20,24) in yellow
        Pz25,10       → single point at (25,10) in light blue

    Returns list of action dicts, or None if parsing fails.
    """
    # Try to find the actions block (might be in a code block)
    # Look for ```actions specifically first, then generic code blocks
    actions_match = re.search(r'```actions\s*([\s\S]*?)\s*```', text)
    if not actions_match:
        actions_match = re.search(r'```\s*([\s\S]*?)\s*```', text)
        # Make sure it's not a JSON block
        if actions_match and actions_match.group(1).strip().startswith('{'):
            actions_match = None

    if actions_match:
        actions_text = actions_match.group(1)
    else:
        # Look for lines starting with L or P
        lines = text.split('\n')
        action_lines = [l.strip() for l in lines if l.strip() and l.strip()[0] in 'LP']
        if not action_lines:
            return None
        actions_text = '\n'.join(action_lines)

    actions = []
    for line in actions_text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):  # Skip empty lines and comments
            continue

        try:
            if line.startswith('L'):
                # Paint line: L<color><x1>,<y1>,<x2>,<y2>
                color, coords_str = _extract_color_and_coords(line, 1)
                coords = coords_str.split(',')
                if len(coords) >= 4:
                    x1, y1 = int(coords[0]), int(coords[1])
                    x2, y2 = int(coords[2]), int(coords[3])

                    # Expand line into paint_at commands
                    # Determine direction
                    if y1 == y2:
                        # Horizontal line
                        start_x, end_x = min(x1, x2), max(x1, x2)
                        for x in range(start_x, end_x + 1):
                            actions.append({
                                "type": "paint_at",
                                "x": x,
                                "y": y1,
                                "color": color,
                            })
                    elif x1 == x2:
                        # Vertical line
                        start_y, end_y = min(y1, y2), max(y1, y2)
                        for y in range(start_y, end_y + 1):
                            actions.append({
                                "type": "paint_at",
                                "x": x1,
                                "y": y,
                                "color": color,
                            })
                    else:
                        # Diagonal or arbitrary: use Bresenham-like stepping
                        dx = abs(x2 - x1)
                        dy = abs(y2 - y1)
                        sx = 1 if x1 < x2 else -1
                        sy = 1 if y1 < y2 else -1
                        err = dx - dy
                        x, y = x1, y1
                        while True:
                            actions.append({
                                "type": "paint_at",
                                "x": x,
                                "y": y,
                                "color": color,
                            })
                            if x == x2 and y == y2:
                                break
                            e2 = 2 * err
                            if e2 > -dy:
                                err -= dy
                                x += sx
                            if e2 < dx:
                                err += dx
                                y += sy

            elif line.startswith('P'):
                # Paint at: P<color><x>,<y>
                color, coords_str = _extract_color_and_coords(line, 1)
                coords = coords_str.split(',')
                if len(coords) >= 2:
                    actions.append({
                        "type": "paint_at",
                        "color": color,
                        "x": int(coords[0]),
                        "y": int(coords[1]),
                    })
        except (ValueError, IndexError) as e:
            # Skip malformed lines but continue parsing
            print(f"[Compact Parse] Skipping malformed line: {line} ({e})")
            continue

    if actions:
        print(f"[Compact Parse] Parsed {len(actions)} paint commands from compact format")
        return actions

    return None


# =============================================================================
# LEARNING DEDUPLICATION
# =============================================================================

def _word_set(text: str) -> set[str]:
    """Extract lowercase words (3+ chars) from text for similarity comparison."""
    return {w.lower() for w in re.findall(r'[a-zA-Z]{3,}', text)}


_CONTRADICTION_PAIRS = [
    ({"more", "increase", "add", "bigger", "larger", "thicker"},
     {"less", "decrease", "remove", "smaller", "thinner", "fewer"}),
    ({"detail", "detailed", "complex", "intricate"},
     {"simple", "clean", "minimal", "sparse"}),
    ({"brighter", "lighter", "vivid"},
     {"darker", "muted", "subdued"}),
    ({"spread", "wider", "expand"},
     {"compact", "narrower", "shrink"}),
]


def _contradicts(text_a: str, text_b: str) -> bool:
    """Check if two learnings contradict each other using keyword-pair detection.

    Returns True if one text uses "positive" terms and the other uses "negative"
    terms from the same dimension pair, and they share at least one topic word
    (or both are short enough that topic overlap is likely).
    """
    words_a = _word_set(text_a)
    words_b = _word_set(text_b)
    all_keywords = set()
    for group_pos, group_neg in _CONTRADICTION_PAIRS:
        all_keywords |= group_pos | group_neg

    for group_pos, group_neg in _CONTRADICTION_PAIRS:
        a_pos = bool(words_a & group_pos)
        a_neg = bool(words_a & group_neg)
        b_pos = bool(words_b & group_pos)
        b_neg = bool(words_b & group_neg)
        # Only trigger if one text is clearly positive and the other clearly negative
        a_is_pos = a_pos and not a_neg
        a_is_neg = a_neg and not a_pos
        b_is_pos = b_pos and not b_neg
        b_is_neg = b_neg and not b_pos
        if (a_is_pos and b_is_neg) or (a_is_neg and b_is_pos):
            # Verify they're about the same subject
            topic_a = words_a - all_keywords
            topic_b = words_b - all_keywords
            overlap = len(topic_a & topic_b) if topic_a and topic_b else 0
            if overlap >= 1:
                return True
            # Short learnings likely about the same thing (few non-keyword words)
            if len(topic_a) < 6 and len(topic_b) < 6:
                return True
    return False


def deduplicate_learnings(
    learnings: list[dict],
    new_learning: dict,
    max_count: int = 5,
    similarity_threshold: float = 0.6,
) -> list[dict]:
    """Keep only unique, recent learnings up to max_count.

    Handles three cases:
    1. If new_learning is >similarity_threshold similar to an existing entry, skip it.
    2. If new_learning contradicts an existing entry, replace the old one.
    3. Otherwise, append the new learning.

    Returns a new list (does not mutate the input).
    """
    new_text = new_learning.get("learning", "")
    new_words = _word_set(new_text)
    if not new_words:
        return learnings[-max_count:] if len(learnings) > max_count else list(learnings)

    result = []
    replaced = False
    for entry in learnings:
        existing_text = entry.get("learning", "")
        existing_words = _word_set(existing_text)
        if not existing_words:
            result.append(entry)
            continue

        # Check for duplicate
        overlap = len(new_words & existing_words)
        union = len(new_words | existing_words)
        if union > 0 and overlap / union >= similarity_threshold:
            print(f"[Learnings] Skipping duplicate learning (similarity {overlap/union:.0%})")
            return learnings[-max_count:] if len(learnings) > max_count else list(learnings)

        # Check for contradiction: replace old with new
        if not replaced and _contradicts(new_text, existing_text):
            print(f"[Learnings] Replacing contradicted learning: '{existing_text[:60]}...' with '{new_text[:60]}...'")
            result.append(new_learning)
            replaced = True
            continue

        result.append(entry)

    if not replaced:
        result.append(new_learning)

    return result[-max_count:]


# =============================================================================
# SVG TO PNG CONVERSION
# =============================================================================

def svg_to_png_base64(svg_path: str, crop_to_canvas: bool = True) -> str:
    """Convert SVG file to base64-encoded PNG, optionally cropping to canvas area.

    Args:
        svg_path: Path to SVG file
        crop_to_canvas: If True, crop to just the doodle canvas area
    """
    try:
        from cairosvg import svg2png
        png_data = svg2png(url=svg_path)
    except ImportError:
        # Fallback: try using rsvg-convert or inkscape
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name

        # Try rsvg-convert first (common on Linux)
        try:
            subprocess.run(
                ['rsvg-convert', '-o', tmp_path, svg_path],
                check=True, capture_output=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try inkscape
            try:
                subprocess.run(
                    ['inkscape', '--export-type=png', f'--export-filename={tmp_path}', svg_path],
                    check=True, capture_output=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("[Warning] No SVG converter found. Install cairosvg: pip install cairosvg")
                return None

        with open(tmp_path, 'rb') as f:
            png_data = f.read()
        os.unlink(tmp_path)

    # Optionally crop to just the canvas area
    if crop_to_canvas and png_data:
        png_data = crop_to_canvas_area(png_data)

    return base64.standard_b64encode(png_data).decode('utf-8')


def _is_dark_pixel(r: int, g: int, b: int, threshold: int = 30) -> bool:
    """Check if a pixel is dark (part of gutter)."""
    return r < threshold and g < threshold and b < threshold


def _find_drawable_bounds(img) -> tuple[int, int, int, int]:
    """Find the drawable canvas area by detecting gutter boundaries.

    Scans for transitions between dark (gutter) and light (canvas) regions.
    Returns (left, top, right, bottom) pixel coordinates.
    """
    width, height = img.size

    # Sample the middle of the image to find vertical gutter positions
    # (gutters are black, canvas is purple)
    mid_y = height // 2

    # Find left boundary: scan right until we exit the dark gutter
    left = 0
    for x in range(0, width // 2, 5):
        # Sample a small vertical strip
        r, g, b = 0, 0, 0
        for dy in range(-5, 6):
            y = mid_y + dy
            if 0 <= y < height:
                px = img.getpixel((x, y))
                r += px[0]
                g += px[1]
                b += px[2]
        r, g, b = r // 11, g // 11, b // 11

        if _is_dark_pixel(r, g, b):
            # Found dark region, continue
            left = x + 10  # Move past gutter
        elif left > 0:
            # Transitioned from dark to light
            break

    # Find right boundary: scan left from right edge
    right = width
    for x in range(width - 1, width // 2, -5):
        r, g, b = 0, 0, 0
        for dy in range(-5, 6):
            y = mid_y + dy
            if 0 <= y < height:
                px = img.getpixel((x, y))
                r += px[0]
                g += px[1]
                b += px[2]
        r, g, b = r // 11, g // 11, b // 11

        if _is_dark_pixel(r, g, b):
            right = x - 5
        elif right < width:
            break

    # Find top boundary: scan down from middle-x
    mid_x = (left + right) // 2
    top = 0
    for y in range(0, height // 2, 5):
        r, g, b = 0, 0, 0
        for dx in range(-5, 6):
            x = mid_x + dx
            if 0 <= x < width:
                px = img.getpixel((x, y))
                r += px[0]
                g += px[1]
                b += px[2]
        r, g, b = r // 11, g // 11, b // 11

        if _is_dark_pixel(r, g, b):
            top = y + 10
        elif top > 0:
            break

    # Find bottom boundary: scan up from bottom
    bottom = height
    for y in range(height - 1, height // 2, -5):
        r, g, b = 0, 0, 0
        for dx in range(-5, 6):
            x = mid_x + dx
            if 0 <= x < width:
                px = img.getpixel((x, y))
                r += px[0]
                g += px[1]
                b += px[2]
        r, g, b = r // 11, g // 11, b // 11

        if _is_dark_pixel(r, g, b):
            bottom = y - 5
        elif bottom < height:
            break

    return left, top, right, bottom


def crop_to_canvas_area(png_data: bytes) -> bytes:
    """Crop PNG to just the drawable canvas area, removing all UI chrome.

    Automatically detects the gutter boundaries by scanning for dark regions.
    Falls back to constant-based calculation if detection fails.
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        print("[Warning] PIL not installed, skipping crop. Install: pip install Pillow")
        return png_data

    from purple_tui.constants import REQUIRED_TERMINAL_COLS, REQUIRED_TERMINAL_ROWS

    try:
        img = Image.open(io.BytesIO(png_data))
        img_width, img_height = img.size
        print(f"[Crop] Image size: {img_width}x{img_height}")

        # Detect gutter boundaries by scanning for dark regions
        left, top, right, bottom = _find_drawable_bounds(img)

        # If detection returned full image, use fallback constants
        # (This happens when not in Doodle paint mode, or no gutter visible)
        if left == 0 and top == 0 and right == img_width and bottom == img_height:
            print("[Crop] No gutter detected, using fallback bounds")
            cell_width = img_width / REQUIRED_TERMINAL_COLS
            cell_height = img_height / REQUIRED_TERMINAL_ROWS
            # Fallback: approximate Doodle mode canvas area from config
            # Title(2) + border(1) + header(DOODLE_HEADER_ROWS) + gutter(GUTTER)
            from purple_tui.doodle_config import DOODLE_HEADER_ROWS
            from purple_tui.modes.doodle_mode import GUTTER
            col_start = GUTTER + 1  # +1 for border
            row_start = 2 + 1 + DOODLE_HEADER_ROWS + GUTTER  # title + border + header + gutter
            left = int(col_start * cell_width)
            top = int(row_start * cell_height)
            right = int((col_start + CANVAS_WIDTH) * cell_width)
            bottom = int((row_start + CANVAS_HEIGHT) * cell_height)

        drawable_width = right - left
        drawable_height = bottom - top
        print(f"[Crop] Drawable area: {drawable_width}x{drawable_height} pixels")
        print(f"[Crop] Crop box: left={left}, top={top}, right={right}, bottom={bottom}")

        # Crop the image
        cropped = img.crop((left, top, right, bottom))
        print(f"[Crop] Cropped to: {cropped.size[0]}x{cropped.size[1]}")

        # Resize if larger than needed to reduce API token costs
        # Canvas is 110x30 cells, so 400x160 is plenty of resolution
        MAX_WIDTH = 400
        MAX_HEIGHT = 160
        if cropped.width > MAX_WIDTH or cropped.height > MAX_HEIGHT:
            original_size = cropped.size
            # Use Resampling.LANCZOS for Pillow 10+ (falls back to LANCZOS for older)
            resample = getattr(Image, 'Resampling', Image).LANCZOS
            cropped.thumbnail((MAX_WIDTH, MAX_HEIGHT), resample)
            print(f"[Resize] {original_size[0]}x{original_size[1]} → {cropped.size[0]}x{cropped.size[1]} (cost reduction)")

        # Convert back to bytes
        output = io.BytesIO()
        cropped.save(output, format='PNG')
        return output.getvalue()

    except Exception as e:
        import traceback
        print(f"[Warning] Crop failed: {e}")
        traceback.print_exc()
        return png_data


# =============================================================================
# PURPLE COMPUTER CONTROLLER
# =============================================================================

class PurpleController:
    """
    Controls the real Purple Computer app via file-based commands.
    Sends commands and captures screenshots through the dev mode API.

    The app runs in dev mode (PURPLE_DEV_MODE=1) which enables:
    - Screenshot trigger via 'trigger' file
    - Command execution via 'command' file (JSON commands)

    This bypasses the evdev keyboard requirement.
    """

    def __init__(self, width: int = 120, height: int = 40):
        self.width = width
        self.height = height
        self.process = None
        self.pty_master = None
        self.screenshot_dir = None
        self.screenshot_count = 0
        # Track cursor position for paint_line starting position
        self._cursor_x = 0
        self._cursor_y = 0

    def start(self, screenshot_dir: str) -> None:
        """Start Purple Computer in a PTY with dev mode enabled."""
        # Use absolute path to avoid working directory issues
        self.screenshot_dir = os.path.abspath(screenshot_dir)
        os.makedirs(self.screenshot_dir, exist_ok=True)

        # Create PTY (for terminal display, not keyboard input)
        self.pty_master, pty_slave = pty.openpty()

        # Set terminal size
        winsize = struct.pack('HHHH', self.height, self.width, 0, 0)
        fcntl.ioctl(pty_slave, termios.TIOCSWINSZ, winsize)

        # Environment for dev mode + screenshots
        env = os.environ.copy()
        env['TERM'] = 'xterm-256color'
        env['PURPLE_DEV_MODE'] = '1'
        env['PURPLE_SCREENSHOT_DIR'] = screenshot_dir
        env['PURPLE_NO_EVDEV'] = '1'  # Disable real keyboard, use file commands only
        env.pop('PURPLE_DEMO_AUTOSTART', None)  # Ensure demo doesn't auto-start
        # Add project root to PYTHONPATH so purple_tui can be found
        project_root = str(Path(__file__).parent.parent)
        env['PYTHONPATH'] = project_root + ':' + env.get('PYTHONPATH', '')

        # Start the app (capture stderr to file for debugging)
        stderr_log = os.path.join(screenshot_dir, 'stderr.log')
        self._stderr_file = open(stderr_log, 'w')
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'purple_tui.purple_tui'],
            stdin=pty_slave,
            stdout=pty_slave,
            stderr=self._stderr_file,
            env=env,
            preexec_fn=os.setsid,
        )

        os.close(pty_slave)

        # Wait for app to fully start and initialize timers
        time.sleep(3)
        self._drain_output()

        print(f"[App] Purple Computer started (PID: {self.process.pid})")

        # Verify app is responding by taking a test screenshot
        print("[App] Verifying app is responsive...")
        test_screenshot = self.take_screenshot()
        if test_screenshot:
            print(f"[App] App ready (test screenshot: {test_screenshot})")
        else:
            print("[App] Warning: App may not be fully initialized")

    def stop(self) -> None:
        """Stop the app."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                self.process.kill()
        if self.pty_master:
            try:
                os.close(self.pty_master)
            except:
                pass
        if hasattr(self, '_stderr_file') and self._stderr_file:
            self._stderr_file.close()
        print(f"[App] Debug log: {self.screenshot_dir}/dev_commands.log")
        print(f"[App] Stderr log: {self.screenshot_dir}/stderr.log")
        print("[App] Purple Computer stopped")

    def _drain_output(self) -> None:
        """Drain any pending output from the PTY."""
        while True:
            r, _, _ = select.select([self.pty_master], [], [], 0.1)
            if not r:
                break
            try:
                os.read(self.pty_master, 4096)
            except:
                break

    def send_command(self, action: str, value: str = "") -> None:
        """Send a command to the app via the command file."""
        self.send_commands([{"action": action, "value": value}])

    def send_commands(self, commands: list[dict]) -> None:
        """Send multiple commands to the app in a single batch.

        Uses atomic file writes (tmp + rename) and waits for the app to consume
        and verify the command batch before returning.
        """
        command_path = os.path.join(self.screenshot_dir, 'command')
        tmp_path = command_path + '.tmp'
        response_path = os.path.join(self.screenshot_dir, 'command_response')

        # Clean stale response file
        if os.path.exists(response_path):
            os.unlink(response_path)

        # Atomic write: write to tmp file, then rename
        content = '\n'.join(json.dumps(cmd) for cmd in commands)
        with open(tmp_path, 'w') as f:
            f.write(content + '\n')
        os.rename(tmp_path, command_path)

        # Wait for app to consume the command file (deleted after reading)
        for _ in range(50):  # 5 second timeout
            time.sleep(0.1)
            if not os.path.exists(command_path):
                break
        else:
            raise RuntimeError(f"App did not consume command file within 5s ({len(commands)} commands)")

        # Verify command count via response file
        for _ in range(10):  # 1 second timeout for response
            if os.path.exists(response_path):
                with open(response_path, 'r') as f:
                    processed = int(f.read().strip())
                os.unlink(response_path)
                if processed != len(commands):
                    raise RuntimeError(
                        f"Command loss! Sent {len(commands)}, app processed {processed}. "
                        f"Lost {len(commands) - processed} commands."
                    )
                return
            time.sleep(0.1)

        raise RuntimeError(f"No command_response after consumption ({len(commands)} commands)")

    def send_key(self, key: str) -> None:
        """Send a single key to the app via command file."""
        # Handle shift+key -> uppercase letter
        if key.startswith('shift+'):
            char = key[6:].upper()
            self.send_command("key", char)
        else:
            self.send_command("key", key)

    def send_keys(self, keys: list[str], delay: float = 0.05) -> None:
        """Send multiple keys with delay between them."""
        for key in keys:
            self.send_key(key)
            time.sleep(delay)

    def take_screenshot(self) -> str | None:
        """
        Take a screenshot via file-based trigger.
        Returns path to the SVG file, or None if failed.
        """
        self._drain_output()

        # Get current screenshot count to detect new one
        latest_file = os.path.join(self.screenshot_dir, 'latest.txt')
        old_path = None
        if os.path.exists(latest_file):
            with open(latest_file) as f:
                old_path = f.read().strip()
        print(f"[Screenshot] Old path: {old_path}")

        # Create trigger file - app will detect and take screenshot
        trigger_path = os.path.join(self.screenshot_dir, 'trigger')
        print(f"[Screenshot] Creating trigger: {trigger_path}")
        with open(trigger_path, 'w') as f:
            f.write('1')

        # Wait for new screenshot to appear
        for i in range(30):  # 3 seconds max
            time.sleep(0.1)
            trigger_exists = os.path.exists(trigger_path)
            if os.path.exists(latest_file):
                with open(latest_file) as f:
                    new_path = f.read().strip()
                if new_path != old_path and os.path.exists(new_path):
                    self.screenshot_count += 1
                    print(f"[Screenshot] Success after {i*0.1:.1f}s: {new_path}")
                    return new_path
            if i == 10:
                print(f"[Screenshot] Still waiting... trigger_exists={trigger_exists}")

        print(f"[Screenshot] FAILED - trigger_exists={os.path.exists(trigger_path)}")
        return None

    def switch_to_doodle(self) -> None:
        """Switch to Doodle mode."""
        self.send_command("mode", "doodle")
        time.sleep(0.1)

    def enter_paint_mode(self) -> None:
        """Enter paint mode (Tab in Doodle mode)."""
        self.send_key('tab')
        time.sleep(0.1)

    def clear_canvas(self) -> None:
        """Clear the entire canvas."""
        print("[Clear] Sending clear command...")
        self.send_commands([{"action": "clear", "value": ""}])
        print("[Clear] Command consumed, canvas cleared")
        time.sleep(0.1)  # Brief wait for render

    def execute_action(self, action: dict) -> None:
        """Execute a single drawing action using direct commands for speed."""
        action_type = action.get('type')

        if action_type == 'move':
            self.send_command("key", action['direction'])

        elif action_type == 'move_to':
            # Use direct set_position command (instant, no arrow keys)
            x = action.get('x', 0)
            y = action.get('y', 0)
            self.send_commands([{"action": "set_position", "x": x, "y": y}])
            self._cursor_x = x
            self._cursor_y = y

        elif action_type == 'select_color':
            # Shift+key to select without stamping (uppercase letter)
            key = action['key'].upper()
            self.send_command("key", key)

        elif action_type == 'stamp':
            self.send_command("key", "space")

        elif action_type == 'paint_at':
            # Direct paint at position (instant, no cursor movement needed)
            x = action.get('x', 0)
            y = action.get('y', 0)
            color = action.get('color', action.get('key', 'f'))
            self.send_commands([{"action": "paint_at", "x": x, "y": y, "color": color}])
            self._cursor_x = x
            self._cursor_y = y

        elif action_type == 'paint_line':
            # Paint a line using direct paint_at commands
            key = action.get('key', 'f')
            direction = action['direction']
            length = action.get('length', 1)
            start_x = action.get('x', getattr(self, '_cursor_x', 0))
            start_y = action.get('y', getattr(self, '_cursor_y', 0))

            # Calculate direction deltas
            dx = {'right': 1, 'left': -1, 'up': 0, 'down': 0}.get(direction, 0)
            dy = {'right': 0, 'left': 0, 'up': -1, 'down': 1}.get(direction, 0)

            # Batch all paint_at commands
            commands = []
            x, y = start_x, start_y
            for _ in range(length):
                commands.append({"action": "paint_at", "x": x, "y": y, "color": key})
                x += dx
                y += dy
            self.send_commands(commands)
            self._cursor_x = x
            self._cursor_y = y

        elif action_type == 'type_text':
            # Batch: exit paint mode, type text, re-enter paint mode
            text = action.get('text', '')
            commands = [{"action": "key", "value": "tab"}]  # Exit paint mode
            commands.extend([{"action": "key", "value": c} for c in text])
            commands.append({"action": "key", "value": "tab"})  # Re-enter paint mode
            self.send_commands(commands)

        elif action_type == 'wait':
            time.sleep(action.get('seconds', 0.5))

    def execute_actions(self, actions: list[dict]) -> None:
        """Execute a list of actions, batching paint_at commands for reliability."""
        paint_at_batch = []

        for action in actions:
            try:
                if action.get('type') == 'paint_at':
                    # Collect paint_at for batching
                    x = action.get('x', 0)
                    y = action.get('y', 0)
                    color = action.get('color', action.get('key', 'f'))
                    paint_at_batch.append({"action": "paint_at", "x": x, "y": y, "color": color})
                else:
                    # Flush any pending paint_at batch first
                    if paint_at_batch:
                        self.send_commands(paint_at_batch)
                        paint_at_batch = []
                    # Execute non-paint_at action
                    self.execute_action(action)
            except Exception as e:
                print(f"[Warning] Action failed: {action} - {e}")

        # Flush remaining paint_at batch
        if paint_at_batch:
            print(f"[Execute] Sending batch of {len(paint_at_batch)} paint_at commands")
            self.send_commands(paint_at_batch)


# =============================================================================
# AI VISION FEEDBACK LOOP
# =============================================================================

PLANNING_PROMPT = f"""You are an AI artist planning a pixel art drawing in Purple Computer's Doodle mode.

## CANVAS SIZE
{describe_canvas()}

## HOW THIS WORKS (REGENERATIVE MODEL)

Each iteration draws a COMPLETE image from scratch. The canvas is cleared between iterations.
You are planning what the FINAL DRAWING should look like, not how to build it incrementally.

The execution AI will see its previous attempt and try to improve, but each attempt is a complete redraw.

## COLOR SYSTEM

{describe_colors_brief()}

## COLOR MIXING

Colors MIX when painted on the SAME cell:
- Yellow + Blue = GREEN
- Red + Blue = PURPLE
- Red + Yellow = ORANGE

**To get green:** Paint yellow on an area, then paint blue on the SAME area.

## VISUAL IDENTITY ANALYSIS (DO THIS FIRST)

Before planning coordinates, analyze the subject:
1. **Defining features**: 3-5 visual features that make this subject instantly recognizable
2. **Common mistakes**: What similar-looking thing might you accidentally draw instead?
3. **Key proportions**: What proportions are critical for recognition?
4. **Pixel art translation**: At {CANVAS_WIDTH}x{CANVAS_HEIGHT} resolution, how to capture these features?
5. **Structural connections**: Where do parts physically attach? For each connection, specify which part connects to which and WHERE (e.g., 'fronds grow from the TOP of the trunk, not the middle')

## YOUR TASK

Create a plan describing what the FINAL drawing should look like:
1. **Composition**: Where each element goes (x/y coordinates)
2. **Colors**: What final color each area should be
3. **Mixing recipe**: For mixed colors, which base colors to use
4. **Style**: Simple, clean shapes with SOLID color regions (no stripes!)

## KEY RULES FOR SUCCESS

- Keep the main subject RECOGNIZABLE (a 4-year-old should identify it)
- Use LARGE, BOLD features so the subject is prominent
- The subject should look good WITHIN the canvas, but does NOT need to fill it edge to edge. Leave empty space where it makes sense (e.g., sky around a tree, ground around a house). Stretching the subject to fill the full width looks unnatural.
- Add SHADING for depth (lighter colors for highlights, darker for shadows)
- Use color mixing to create greens, oranges, and purples

## ENTERTAINMENT VALUE (CRITICAL)

The drawing is watched in real-time by a child. Every paint stroke appears as it's drawn.
Plan compositions that are FUN TO WATCH being drawn:
- **Minimize large background fills.** A solid blue sky or green ground covering 50+ cells per row is BORING to watch. Instead, leave the canvas background showing, or use just a few accent lines for sky/ground.
- **Focus on the SUBJECT.** The interesting part is the subject itself: its shape, colors, shading, and details. Maximize time spent on the subject.
- **Color mixing is exciting.** Watching yellow turn to green or orange is visually delightful. Plan compositions that use lots of mixing.
- **Details and texture are engaging.** Small highlights, shadow lines, and decorative touches keep the viewer interested.
- **Avoid monotone fills.** Large areas of a single flat color are the least interesting thing to watch. If a background is needed, make it minimal (a few rows, not the entire canvas).

## RESPONSE FORMAT

```json
{{
  "plan": {{
    "visual_identity": {{
      "defining_features": ["feature 1", "feature 2", "feature 3"],
      "common_mistakes": ["What you might accidentally draw instead"],
      "key_proportions": "Critical proportions for recognition",
      "pixel_art_notes": "How to capture defining features at {CANVAS_WIDTH}x{CANVAS_HEIGHT}",
      "structural_connections": ["fronds attach at the TOP of the trunk", "legs attach at the BOTTOM of the body"]
    }},
    "description": "Brief description of the final drawing",
    "composition": {{
      "element_name": {{
        "x_range": [start, end],
        "y_range": [start, end],
        "final_color": "green (or red, blue, yellow, brown, etc.)",
        "mixing_recipe": "yellow base + blue overlay" or null for pure colors,
        "description": "what this element is"
      }}
    }},
    "style_notes": "Key points about the visual style - emphasize CURVED, ORGANIC shapes (e.g., 'round fluffy foliage, not rectangular')",
    "recognition_test": "A 4-year-old should see: [what they should recognize]"
  }}
}}
```

Be specific about coordinates. The execution AI will use this as a reference for composition.

**COMPOSITION TIP:** The main subject should be naturally sized and centered, with space around it. For example, an apple tree trunk might span x=40-60, with a canopy from x=25-75, not the full 0-{CANVAS_WIDTH - 1}.

**BACKGROUND TIP:** Keep backgrounds MINIMAL. A tree doesn't need a full blue sky fill ({CANVAS_HEIGHT} rows x {CANVAS_WIDTH} columns = boring). Instead, leave most of the canvas background showing and focus detail on the subject. If you want a ground line, use 2-3 rows, not 10. If you want sky, use a few accent strokes or a gradient strip, not a full fill."""


EXECUTION_PROMPT = f"""You are an AI artist creating pixel art in Purple Computer's Doodle mode.

## GOALS
Your drawings should be:
1. **Colorful** - use lots of pretty colors, especially through color mixing
2. **Shaded** - use lighter and darker shades for depth and dimension
3. **Detailed** - add texture, highlights, gradients, and fine details
4. **Organic** - use varied shapes, not just rectangles
5. **Recognizable** - a 4-year-old should be able to identify what it is
6. **Fun to watch** - a child watches every stroke appear in real-time (see ENTERTAINMENT section)

## COLOR MIXING

Painting over an existing color MIXES them (like real paint!):
- Yellow + Blue → GREEN
- Yellow + Red → ORANGE
- Blue + Red → PURPLE

To mix: paint the base color on an area, then paint the second color on the SAME cells.

Example for green (rows 10-12):
```
Lf0,10,50,10
Lf0,11,50,11
Lf0,12,50,12
Lc0,10,50,10
Lc0,11,50,11
Lc0,12,50,12
```

## CANVAS SIZE
{describe_canvas()}

## WHAT YOU SEE IN SCREENSHOTS
- Colored cells are painted areas
- Letters visible on cells (like "F", "C", "R") are just labels showing which key painted that cell
- The cursor is a 3×3 blinking ring of box-drawing characters (┌━┐ etc.)
- Purple background = unpainted canvas

## COLOR SYSTEM (KEYBOARD ROWS)

{describe_colors()}

## SHADING TECHNIQUE

To create 3D depth and realism, use DIFFERENT keys from the same row:
- **Highlights**: Use leftmost keys (q, a, z, `)
- **Midtones**: Use middle keys (t, f, b, 5)
- **Shadows**: Use rightmost keys (\\, ', /, =)

Example for a tree trunk: paint 'd' for lit side, 'j' for middle, "'" (apostrophe) for shadow side.

**Brown requires cross-family mixing!** Yellow-on-yellow (e.g., 'f' then 'k') stays yellow/gold. To get brown, paint yellow ('f') then overlay with red ('t' or 'y'). For dark brown, use dark yellow (';') + dark red ('p').

## COLOR MIXING (CRITICAL!)

When you paint OVER an already-painted cell, colors MIX like real paint:
- Yellow + Blue = GREEN
- Red + Blue = PURPLE
- Red + Yellow = ORANGE

**IMPORTANT: For mixed colors, you MUST paint in this order:**
1. Paint the ENTIRE area with the FIRST color (e.g., all yellow for future green)
2. THEN paint the SAME area again with the SECOND color (e.g., blue over yellow)
3. Do NOT alternate between colors cell by cell - that creates stripes, not mixing!

**Correct (GREEN grass):**
```
paint_line y=20, x=0-50, color="f" (yellow)
paint_line y=20, x=0-50, color="c" (blue over SAME cells = GREEN)
```

**Wrong (stripey mess):**
```
paint_at x=0, y=20, color="f"
paint_at x=1, y=20, color="c"  # Different cell! No mixing!
```

The mixing is realistic (Kubelka-Munk spectral mixing), like real paint.

## COMPACT ACTION FORMAT (REQUIRED)

Use this compact format for actions (one per line in a code block):

**L = Line**: `L<color><x1>,<y1>,<x2>,<y2>`
Draw from (x1,y1) to (x2,y2) with the specified color key.
- Horizontal: `Lf0,10,50,10` (same y)
- Vertical: `Lf20,0,20,24` (same x)
- **Diagonal**: `Lf10,5,30,15` (different x AND y - creates curves!)

**P = Point**: `P<color><x>,<y>`
Paint a single cell at (x,y) with the specified color key.

## CURVES AND ORGANIC SHAPES

Chain short diagonal L commands to draw curves. Shorter segments = smoother curves.

**Arc** (upward curve from left to right):
```actions
Lf10,20,15,17
Lf15,17,20,15
Lf20,15,30,14
Lf30,14,40,15
Lf40,15,45,17
Lf45,17,50,20
```

**Circle outline** (for OUTLINES only, not fills; 8 segments, center ~50,12, radius ~8):
```actions
Lf50,4,56,6
Lf56,6,58,12
Lf58,12,56,18
Lf56,18,50,20
Lf50,20,44,18
Lf44,18,42,12
Lf42,12,44,6
Lf44,6,50,4
```

**Wavy line** (alternating up/down slopes):
```actions
Lf0,12,10,8
Lf10,8,20,12
Lf20,12,30,8
Lf30,8,40,12
Lf40,12,50,8
```

Key principle: Each segment covers only 5-10 x-units. The shorter the segment, the smoother the curve.

For filled shapes, vary the x-range per row to create curved edges. Don't use the same x-range for every row (that makes rectangles).

## FILLING SHAPES (PRIMARY TECHNIQUE)

For solid regions (canopies, trunks, bodies), use ROW-BY-ROW HORIZONTAL FILLS
with varying width to create round/organic shapes. This is the MOST IMPORTANT technique.
(For backgrounds like sky/ground, keep them minimal: 2-3 rows max, or skip entirely.)

**Round canopy (filled circle):**
```actions
Lf36,5,54,5
Lf32,6,58,6
Lf28,7,62,7
Lf26,8,64,8
Lf25,9,65,9
Lf25,10,65,10
Lf26,11,64,11
Lf28,12,62,12
Lf32,13,58,13
Lf36,14,54,14
```

**Small filled circle (sun, ball, apple):**
```actions
Lf48,3,52,3
Lf46,4,54,4
Lf45,5,55,5
Lf45,6,55,6
Lf46,7,54,7
Lf48,8,52,8
```
Use this for compact round objects. Do NOT draw suns as a small rectangle with long horizontal rays extending out. That creates a trophy/goblet shape. Instead, use a filled circle like this.

**Thick trunk (filled rectangle with slight taper):**
```actions
Lf43,15,57,15
Lf44,16,56,16
Lf44,17,56,17
Lf44,18,56,18
Lf45,19,55,19
```

**Oval body (animal, widest at center):**
```actions
Lf38,12,62,12
Lf34,13,66,13
Lf31,14,69,14
Lf30,15,70,15
Lf30,16,70,16
Lf31,17,69,17
Lf34,18,66,18
Lf38,19,62,19
```

**WRONG (rectangle body):** same x-range every row = boxy, unnatural shape. ALWAYS vary the width.

**Tapered tail (progressively shorter fills):**
```actions
Lf70,14,82,14
Lf72,15,84,15
Lf75,16,86,16
Lf78,17,88,17
```

Vary the x start/end per row: wider in the middle, narrower at top and bottom.
This creates smooth, solid shapes. Use this for ALL filled regions.

Diagonal lines and arcs are for OUTLINES and DETAILS only, not for filling areas.
Using diagonals to fill produces a stripy, sparse look. Always prefer horizontal fills.

**Small triangle/plate (pointing up):**
```actions
Lf48,12,52,12
Lf49,11,51,11
Pf50,10
```

**Row of triangular plates along a spine (like stegosaurus):**
```actions
Lf30,12,34,12
Lf31,11,33,11
Pf32,10
Lf37,12,41,12
Lf38,11,40,11
Pf39,10
Lf44,12,48,12
Lf45,11,47,11
Pf46,10
```

For tapered shapes (legs, tails, spikes), use progressively shorter horizontal fills.

## DRAWING MULTI-PART FIGURES (animals, people, vehicles)

For complex objects, draw each body part as a SEPARATE filled shape at its planned position:
1. Draw the largest part first (body: a wide oval of horizontal fills)
2. Draw connected parts overlapping slightly (head, neck, tail)
3. Draw appendages (legs, arms, wings)
4. Draw details last (eyes, plates, patterns)

Each part is its own group of horizontal fills at different x/y ranges.
Do NOT try to draw the whole figure with one set of lines.

**CONNECTION POINTS ARE CRITICAL:** Check WHERE each part attaches. Tree fronds start at the TOP of the trunk. Legs attach at the BOTTOM of a body. Arms attach at the SIDES of a torso, not the middle. Get connection points right BEFORE worrying about details. Wrong attachment points make the drawing look broken even if individual shapes are good.

## REGENERATIVE APPROACH

You are generating a COMPLETE drawing script from scratch each iteration.
The canvas is CLEARED before each attempt. You will see a screenshot of your PREVIOUS attempt's result.

Your goal: Generate a BETTER complete script than last time, learning from what worked and what didn't.

## USE SHADING FOR REALISM

**Don't use flat colors!** Use different keys within each row to create 3D depth:
- Assume light comes from top-left (or specify your light direction)
- **Lit surfaces**: Use lighter keys (q, a, z, `)
- **Middle tones**: Use medium keys (t, f, b, 5)
- **Shadows**: Use darker keys (\\, ', /, =)

Example: For green foliage, don't just use 'f'+'c' everywhere:
- Lit side: 'a' (light yellow) + 'z' (light blue) = bright green
- Middle: 'f' (medium yellow) + 'b' (medium blue) = medium green
- Shadow: 'k' (dark yellow) + '.' (dark blue) = dark green

**OVERLAP RULE:** Shadow and highlight overlays MUST stay WITHIN the base shape's boundaries. If the canopy's yellow base on row 12 spans x:28-68, then any blue or dark overlay on row 12 must also be within x:28-68. Painting overlay colors outside the base shape creates stray colored pixels (artifacts). Always check that your overlay coordinates fit inside the base fill coordinates for that row.

## ENTERTAINMENT VALUE (CRITICAL)

A child watches every stroke appear in real-time. The drawing process itself must be fun to watch.

**DRAW THE SUBJECT FIRST.** The subject (tree, animal, house) is the interesting part. Draw it before any background.

**MINIMIZE BACKGROUNDS.** Large monotone fills (solid blue sky, solid green ground) are BORING to watch: hundreds of identical horizontal lines with no visual change. Instead:
- Leave the canvas background showing where possible
- If you need ground, use 2-3 rows with color variation, not 10 flat rows
- If you need sky, use a thin gradient strip or a few accent lines, not a full fill
- A drawing with NO background but a detailed, colorful subject is better than one with full sky+ground fills and a simple subject

**COLOR MIXING IS THE STAR.** Watching yellow cells transform into green or orange is visually delightful. Prioritize compositions that use lots of mixing.

**DRAW ORDER MATTERS.** Structure your actions so interesting things happen throughout:
- Start with the subject's base colors (exciting: shapes appearing)
- Add mixing overlays (exciting: colors transforming)
- Add shading and details (exciting: depth appearing)
- Add minimal background last, if at all (least exciting)

## LAYERED PAINTING (within each attempt)

To get mixed colors, paint in layers PER ELEMENT (not all-yellow-first):

**Draw each element completely before moving to the next:**
1. Paint the element's base color (yellow for things that will be green/orange)
2. Immediately overlay the mixing color on that SAME element
3. Add shading to that element
4. Move to the next element

This keeps the drawing visually interesting because you see each part take shape and get its final color before moving on.

**Example: Tree with green canopy and brown trunk**
```actions
// Canopy: yellow base, then blue overlay = GREEN
Lf30,5,70,5
Lf28,6,72,6
Lf26,7,74,7
Lc30,5,70,5
Lc28,6,72,6
Lc26,7,74,7
// Trunk: yellow base + red overlay = BROWN (cross-family mixing!)
Lf45,15,55,15
Lf45,16,55,16
Lt45,15,55,15
Lt45,16,55,16
// Minimal ground: just 2 rows
Lf0,23,100,23
Lc0,23,100,23
```

Notice how the canopy gets its yellow AND blue (becoming green) before we move to the trunk. The trunk uses yellow + red = brown (cross-family mixing). This is more fun to watch than painting all yellow first.

For SHADING mixed colors, vary the shade of the overlay:
- Bright green highlight: light yellow ("a") + light blue ("z")
- Medium green: medium yellow ("f") + medium blue ("b")
- Dark green shadow: dark yellow ("k") + dark blue (".")

## RESPONSE FORMAT

Respond with a JSON object followed by a compact actions block:

```json
{{
  "analysis": "What I see from the previous attempt and what to improve",
  "strategy_summary": {{
    "composition": {{
      "element_name": {{"x_range": [start, end], "y_range": [start, end], "description": "what this element is"}}
    }},
    "layering_order": ["Step 1: Yellow base", "Step 2: Blue overlay", "Step 3: Details"],
    "keep_next_time": ["trunk position at x=48-52"],
    "change_next_time": ["make trunk wider"]
  }},
  "learnings": "Key insight from this attempt"
}}
```

```actions
Lf20,5,80,5
Lf18,6,82,6
Lc20,5,50,5
Pk35,10
```

**analysis** (REQUIRED): What you observe and your plan to improve.

**strategy_summary** (REQUIRED): Structured description with composition, layering_order, keep_next_time, change_next_time.

**learnings** (REQUIRED): One key insight from THIS attempt.

**actions block** (REQUIRED): Generate compact actions for the drawing.
- Use L (lines) to fill solid areas
- Use P (points) for details, highlights, and texture
- Use diagonal lines (L with different x1,y1 and x2,y2) for organic shapes
- More actions = more detail and richer shading!

**Tips for beautiful drawings:**
- Add shading: use lighter colors on lit surfaces, darker in shadows
- Add texture: sprinkle in detail points with varied colors
- Create depth: foreground elements overlap background
- Compose naturally: the subject should look good in the canvas, NOT stretch to fill the full width. A tree canopy should be round, not {CANVAS_WIDTH} cells wide. Leave empty space around the subject.
- Minimize backgrounds: skip large sky/ground fills. A detailed subject on a mostly-empty canvas looks better than a simple subject buried in monotone background fills.

**IMPORTANT: All fields are REQUIRED. Use the compact action format, NOT JSON arrays.**"""


def load_reference_image(path: str) -> tuple[str, str]:
    """Load an image file and return (base64_data, media_type)."""
    ext = os.path.splitext(path)[1].lower()
    media_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    media_type = media_types.get(ext, 'image/png')

    with open(path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')

    return data, media_type


def prepare_reference_for_execution(path: str) -> tuple[str, str]:
    """Load and downsize a reference image for the execution model.

    Returns a small version (max 200x200) to minimize token cost,
    since the execution model just needs a rough visual target.
    """
    from PIL import Image

    img = Image.open(path)
    resample = getattr(Image, 'Resampling', Image).LANCZOS
    img.thumbnail((200, 200), resample)

    ext = os.path.splitext(path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        fmt, media_type = 'JPEG', 'image/jpeg'
    else:
        fmt, media_type = 'PNG', 'image/png'

    buf = io.BytesIO()
    img.save(buf, format=fmt)
    data = base64.b64encode(buf.getvalue()).decode('utf-8')
    print(f"[Reference] Resized to {img.size[0]}x{img.size[1]} for execution model")
    return data, media_type


def call_plan_refinement_api(
    original_plan: dict,
    instruction: str,
    iterations: int,
    api_key: str,
    reference_image: str = None,
) -> dict:
    """Refine an existing drawing plan based on user instruction.

    Takes a previous plan and modifies it according to the instruction,
    keeping elements that aren't mentioned.

    Args:
        reference_image: Optional path to a reference image

    Returns:
        Refined plan dict
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    text_message = f"""## Original Plan
```json
{json.dumps(original_plan, indent=2)}
```

## Refinement Instruction
{instruction}

## Available Iterations: {iterations}

Modify the plan above based on the refinement instruction.
Keep everything that isn't mentioned in the instruction.
Adjust coordinates, colors, and composition as needed to incorporate the changes.
Divide the work into phases that fit within the iteration count.

Respond with a JSON object containing a "plan" field."""

    message_content = []
    if reference_image:
        img_data, media_type = load_reference_image(reference_image)
        message_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": img_data,
            },
        })
        message_content.append({"type": "text", "text": "**Reference image above.** Use it to guide proportions, composition, and style.\n\n" + text_message})
        print(f"[Planning] Refining plan with reference image: {instruction}")
    else:
        message_content = text_message
        print(f"[Planning] Refining plan: {instruction}")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=PLANNING_PROMPT,
        messages=[{
            "role": "user",
            "content": message_content,
        }],
    )

    text = response.content[0].text

    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            plan = data.get('plan', data)

            print("[Plan] Refined drawing plan:")
            print(f"  Description: {plan.get('description', 'N/A')}")
            for phase in plan.get('phases', []):
                print(f"  - {phase.get('name')}: iterations {phase.get('iterations')}")
                print(f"    Goal: {phase.get('goal')}")

            return plan
    except json.JSONDecodeError as e:
        print(f"[Error] Refined plan JSON parse failed: {e}")
        print(f"[Debug] Raw response:\n{text[:500]}...")

    # If parsing fails, return the original plan unchanged
    print("[Warning] Could not parse refined plan, using original")
    return original_plan


def call_planning_api(
    goal: str,
    iterations: int,
    api_key: str,
    reference_image: str = None,
) -> dict:
    """Call Claude API to create a drawing plan.

    Args:
        reference_image: Optional path to a reference image

    Returns:
        Plan dict with phases and composition details
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    text_message = f"""## Goal: {goal}

## Available Iterations: {iterations}

Create a detailed plan for drawing this image across {iterations} iterations.
Divide the work into phases that fit within the iteration count.

Respond with a JSON object containing a "plan" field."""

    message_content = []
    if reference_image:
        img_data, media_type = load_reference_image(reference_image)
        message_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": img_data,
            },
        })
        message_content.append({"type": "text", "text": "**Reference image above.** Use it to guide proportions, composition, and style.\n\n" + text_message})
        print("[Planning] Creating drawing plan with reference image...")
    else:
        message_content = text_message
        print("[Planning] Creating drawing plan...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=PLANNING_PROMPT,
        messages=[{
            "role": "user",
            "content": message_content,
        }],
    )

    text = response.content[0].text

    # Parse JSON response
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            plan = data.get('plan', data)  # Handle both {plan: ...} and direct plan

            # Print the plan
            print("[Plan] Created drawing plan:")
            print(f"  Description: {plan.get('description', 'N/A')}")
            for phase in plan.get('phases', []):
                print(f"  - {phase.get('name')}: iterations {phase.get('iterations')}")
                print(f"    Goal: {phase.get('goal')}")

            return plan
    except json.JSONDecodeError as e:
        print(f"[Error] Plan JSON parse failed: {e}")
        print(f"[Debug] Raw response:\n{text[:500]}...")

    # Return a default plan if parsing fails
    return {
        "description": goal,
        "phases": [
            {"name": "Phase 1", "iterations": list(range(1, iterations + 1)), "goal": goal, "color_keys": ["f", "c", "r"]}
        ]
    }


def get_current_phase(plan: dict, iteration: int) -> dict | None:
    """Get the phase that contains the given iteration number."""
    for phase in plan.get('phases', []):
        if iteration in phase.get('iterations', []):
            return phase
    return None


def get_complexity_guidance(iteration: int, max_iterations: int) -> str:
    """Get progressive complexity guidance based on iteration progress.

    Encourages detail and richness throughout.
    """
    progress = iteration / max_iterations

    if progress <= 0.25:
        return """## ITERATION PHASE: Foundation
Establish the basic composition and main shapes. Use color mixing to create greens, oranges, purples.
Focus on the SUBJECT first. Skip or minimize background fills (sky, ground). Draw the interesting parts."""

    elif progress <= 0.5:
        return """## ITERATION PHASE: Development
Build out the drawing with more colors and shading. Add texture and visual interest.
Use the full range of colors: lights for highlights, darks for shadows. Keep backgrounds minimal."""

    elif progress <= 0.75:
        return """## ITERATION PHASE: Refinement
Add fine details, highlights, and finishing touches. Make it rich and visually interesting.
Don't hold back on detail. The more texture, shading, and color mixing, the better."""

    else:
        return """## ITERATION PHASE: Polish
Perfect the details. Add any missing highlights, shadows, or textures.
Make every part of the SUBJECT interesting to look at. Avoid adding large background fills at this stage."""


def call_vision_api(
    image_base64: str,
    goal: str,
    iteration: int,
    max_iterations: int,
    api_key: str,
    plan: dict = None,
    accumulated_learnings: list[dict] = None,
    previous_strategy: str = None,
    judge_feedback: dict = None,
    best_image_base64: str = None,
    best_attempt_num: int = None,
    runner_up_image_base64: str = None,
    runner_up_attempt_num: int = None,
    best_script_text: str = None,
    consecutive_losses: int = 0,
    execution_model: str = "claude-sonnet-4-20250514",
    reference_image_base64: str = None,
    reference_image_media_type: str = None,
) -> dict:
    """Call Claude vision API with screenshot and get analysis + complete action script.

    Args:
        image_base64: Screenshot as base64 PNG (current/latest result)
        goal: What to draw
        iteration: Current iteration number (1-indexed)
        max_iterations: Total iterations
        api_key: Anthropic API key
        plan: Drawing plan from planning phase
        accumulated_learnings: List of {iteration, learning} from previous attempts
        previous_strategy: Strategy summary from previous attempt
        judge_feedback: Dict with judge's evaluation of recent comparison (reasoning, winner, etc.)
        best_image_base64: Screenshot of the current best attempt (PNG base64)
        best_attempt_num: Which attempt number produced the best result
        runner_up_image_base64: Screenshot of the runner-up attempt (PNG base64)
        runner_up_attempt_num: Which attempt number is the runner-up
        best_script_text: Compact action text (L/P commands) of the best attempt
        consecutive_losses: How many iterations the best hasn't changed

    Returns:
        Dict with keys: analysis, strategy_summary, learnings, actions
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Build accumulated learnings section (compact text, not full scripts)
    learnings_section = ""
    if accumulated_learnings:
        learnings_section = "\n## LEARNINGS FROM PREVIOUS ATTEMPTS\n"
        for entry in accumulated_learnings:
            learnings_section += f"- Attempt {entry['iteration']}: {entry['learning']}\n"
        learnings_section += "\nBuild on these insights. Don't repeat mistakes.\n"

    # Include previous strategy for context (not full script)
    strategy_section = ""
    if previous_strategy:
        strategy_section = "\n## PREVIOUS STRATEGY\n"
        if isinstance(previous_strategy, dict):
            # Format structured strategy nicely
            if previous_strategy.get("composition"):
                strategy_section += "Composition:\n"
                for name, pos in previous_strategy["composition"].items():
                    x_range = pos.get("x_range", "?")
                    y_range = pos.get("y_range", "?")
                    desc = pos.get("description", "")
                    strategy_section += f"  - {name}: x={x_range}, y={y_range} ({desc})\n"
            if previous_strategy.get("layering_order"):
                strategy_section += "Layering order:\n"
                for step in previous_strategy["layering_order"]:
                    strategy_section += f"  - {step}\n"
            if previous_strategy.get("color_results"):
                cr = previous_strategy["color_results"]
                if cr.get("worked"):
                    strategy_section += f"What worked: {', '.join(cr['worked'])}\n"
                if cr.get("failed"):
                    strategy_section += f"What failed: {', '.join(cr['failed'])}\n"
            if previous_strategy.get("keep_next_time"):
                strategy_section += f"Keep: {', '.join(previous_strategy['keep_next_time'])}\n"
            if previous_strategy.get("change_next_time"):
                strategy_section += f"Change: {', '.join(previous_strategy['change_next_time'])}\n"
        else:
            # Fallback for string format
            strategy_section += f"{previous_strategy}\n"
        strategy_section += "\nThe screenshot shows the result of this approach.\n"

    # Build judge feedback section (Option A: pass judge reasoning to execution AI)
    judge_section = ""
    if judge_feedback:
        winner = judge_feedback.get("winner", "")
        reasoning = judge_feedback.get("reasoning", "")
        compared_best = judge_feedback.get("compared_best_attempt")
        compared_new = judge_feedback.get("compared_new_attempt")

        if winner == "B":
            # Previous attempt was better than the old best
            judge_section = "\n## JUDGE FEEDBACK (Your last attempt WON)\n"
            judge_section += f"Your Attempt {compared_new} beat the previous best (Attempt {compared_best}).\n"
            judge_section += f"Judge's reasoning: {reasoning}\n"
            judge_section += "Keep doing what worked! Build on this success.\n"
        elif winner == "A":
            # Previous attempt was worse than the best
            judge_section = "\n## JUDGE FEEDBACK (Your last attempt LOST)\n"
            judge_section += f"Your Attempt {compared_new} was worse than Attempt {compared_best}.\n"
            judge_section += f"Judge's reasoning: {reasoning}\n"
            judge_section += "Change your approach. The current best is still Attempt {compared_best}.\n"

        # Add per-criterion scores if available
        weakest = judge_feedback.get("weakest_criterion")
        improvement = judge_feedback.get("specific_improvement")
        if weakest and improvement:
            judge_section += f"\n**WEAKEST AREA:** {weakest}\n"
            judge_section += f"**SPECIFIC FIX:** {improvement}\n"
            judge_section += "Focus your changes on this specific weakness.\n"

        scores_best = judge_feedback.get("scores_best")
        if scores_best and isinstance(scores_best, dict):
            judge_section += "\n**Best attempt scores:** "
            judge_section += ", ".join(f"{k}={v}" for k, v in scores_best.items())
            judge_section += "\n"

    # Build best script section (highest-impact: AI sees the exact source code)
    best_script_section = ""
    if best_script_text and best_attempt_num:
        best_script_section = f"\n## BEST ATTEMPT'S SCRIPT (Attempt {best_attempt_num})\n"
        best_script_section += "This script produced the current best result. Study it and improve upon it.\n"
        best_script_section += f"```actions\n{best_script_text}\n```\n"

    # Build refinement mode section with escalating freedom based on consecutive losses
    refinement_section = ""
    diversity_section = ""
    if consecutive_losses >= 3 and best_script_text:
        if consecutive_losses <= 4:
            refinement_section = """\n## REFINEMENT MODE (Targeted)
The best attempt's script is provided above. Make TARGETED improvements:
- Keep the overall structure that's working
- Modify specific sections (shading, details, proportions)
- Change at most 20-30% of the lines
- Focus on what the judge said was missing

IMPORTANT: If the best script uses horizontal line fills for solid shapes, keep that approach.
Do NOT convert horizontal fills into diagonal outlines or sparse line patterns.

Start from the best script and improve it.\n"""
        elif consecutive_losses <= 6:
            refinement_section = f"""\n## REFINEMENT MODE (Restructure)
You have lost {consecutive_losses} times with small tweaks. Time for bigger changes.
The best attempt's script is provided above. You may change 40-60% of the lines:
- RESTRUCTURE problem areas: reshape rectangular bodies into ovals (vary x-range per row)
- Smooth stepped/staircase shapes into tapered forms (progressively shorter fills)
- Improve proportions and organic curves
- Keep the overall layout and color scheme

Focus on SHAPE QUALITY: organic curves beat straight edges.\n"""
        else:
            refinement_section = f"""\n## REFINEMENT MODE (Major Overhaul)
You have lost {consecutive_losses} times. The current approach has plateaued.
You may change 70-100% of the lines. Keep only the general layout from the best attempt:
- REDRAW shapes from scratch with better technique
- Use varying x-ranges for organic oval bodies (wider in middle, narrower at edges)
- Use progressively shorter fills for tapered tails and limbs
- Rebuild with proper shading and 3D depth
- The layout and composition are good, but the shapes need major improvement.\n"""

    # Build plan summary
    plan_section = ""
    if plan:
        plan_section = f"\n## DRAWING PLAN\n{plan.get('description', goal)}\n"
        if plan.get('composition'):
            comp = plan['composition']
            plan_section += "\n**Parts to draw (with coordinates):**\n"
            for part_name, part_info in comp.items():
                if isinstance(part_info, dict):
                    desc = part_info.get('description', part_name)
                    x_range = part_info.get('x_range', '')
                    y_range = part_info.get('y_range', '')
                    color = part_info.get('final_color', '')
                    recipe = part_info.get('mixing_recipe', '')
                    line = f"- **{part_name}**: {desc}, x={x_range}, y={y_range}, color={color}"
                    if recipe:
                        line += f", mix={recipe}"
                    plan_section += line + "\n"
        if plan.get('style_notes'):
            plan_section += f"\nStyle: {plan['style_notes']}\n"
        if plan.get('visual_identity'):
            vi = plan['visual_identity']
            plan_section += "\n## VISUAL IDENTITY (what makes this subject recognizable)\n"
            if vi.get('defining_features'):
                plan_section += "**Must show:** " + ", ".join(vi['defining_features']) + "\n"
            if vi.get('common_mistakes'):
                mistakes = vi['common_mistakes']
                if isinstance(mistakes, list):
                    plan_section += "**AVOID:** " + "; ".join(mistakes) + "\n"
                else:
                    plan_section += f"**AVOID:** {mistakes}\n"
            if vi.get('key_proportions'):
                plan_section += f"**Proportions:** {vi['key_proportions']}\n"
            if vi.get('pixel_art_notes'):
                plan_section += f"**Pixel art approach:** {vi['pixel_art_notes']}\n"
            if vi.get('structural_connections'):
                connections = vi['structural_connections']
                if isinstance(connections, list):
                    plan_section += "**CONNECTION POINTS:** " + "; ".join(connections) + "\n"
                else:
                    plan_section += f"**CONNECTION POINTS:** {connections}\n"

    # Option D: Get progressive complexity guidance
    complexity_section = get_complexity_guidance(iteration, max_iterations)

    # First iteration vs subsequent
    if iteration == 1:
        instruction = """This is your FIRST attempt. Generate a complete drawing script based on the plan.
The canvas is blank. Draw the SUBJECT first (the interesting part), then add minimal background if needed.
For each element, paint its base color then immediately overlay the mixing color:
1. Draw main subject elements one by one (base color + mixing overlay per element)
2. Add shading and details to the subject
3. Add minimal background last (2-3 rows of ground, thin sky strip, or nothing)"""
    else:
        instruction = """The screenshot shows your PREVIOUS attempt's result.
Analyze what worked and what needs improvement, then generate a BETTER complete script.
The canvas will be CLEARED and your new script executed from scratch."""

    # Build top performers section (references images sent alongside)
    top_performers_text = ""
    if best_image_base64 and best_image_base64 != image_base64:
        top_performers_text += "\n## TOP PERFORMERS\n"
        top_performers_text += f"The BEST ATTEMPT image (Attempt {best_attempt_num}) is included below.\n"
        if runner_up_image_base64 and runner_up_image_base64 != image_base64 and runner_up_image_base64 != best_image_base64:
            top_performers_text += f"The RUNNER-UP image (Attempt {runner_up_attempt_num}) is also included.\n"
        top_performers_text += "Study what these top attempts did well and combine their strengths in your new attempt.\n"

    user_message = f"""## Goal: {goal}

## Attempt: {iteration} of {max_iterations}

{complexity_section}
{plan_section}{learnings_section}{strategy_section}{judge_section}{best_script_section}{refinement_section}{diversity_section}{top_performers_text}
{instruction}

Respond with JSON metadata followed by a compact ```actions``` block."""

    # Build message content with images (canvas + optional best + optional runner-up)
    message_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_base64,
            },
        },
        {"type": "text", "text": "CURRENT CANVAS (your most recent attempt)"},
    ]

    # Add best attempt image if it differs from canvas
    if best_image_base64 and best_image_base64 != image_base64:
        message_content.extend([
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": best_image_base64,
                },
            },
            {"type": "text", "text": f"BEST ATTEMPT (Attempt {best_attempt_num})"},
        ])

    # Add runner-up image if it differs from canvas and best
    if (runner_up_image_base64
            and runner_up_image_base64 != image_base64
            and runner_up_image_base64 != best_image_base64):
        message_content.extend([
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": runner_up_image_base64,
                },
            },
            {"type": "text", "text": f"RUNNER-UP (Attempt {runner_up_attempt_num})"},
        ])

    # Add reference image if provided
    if reference_image_base64:
        message_content.extend([
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": reference_image_media_type or "image/png",
                    "data": reference_image_base64,
                },
            },
            {"type": "text", "text": "REFERENCE IMAGE: Use this as a visual guide for proportions, composition, and style."},
        ])

    # Add the main text prompt last
    message_content.append({"type": "text", "text": user_message})

    temperature = 1.0

    response = client.messages.create(
        model=execution_model,
        max_tokens=8000,  # More tokens for complete scripts
        temperature=temperature,
        system=EXECUTION_PROMPT,
        messages=[{
            "role": "user",
            "content": message_content,
        }],
    )

    text = response.content[0].text

    # Parse response: try compact action format first, fall back to JSON
    result = {
        "analysis": "",
        "strategy_summary": "",
        "learnings": "",
        "actions": [],
        "raw_response": text,  # For debugging
        "compact_actions_text": "",  # Raw L/P commands before expansion
    }

    # 1. Try to extract compact actions from ```actions block
    compact_actions = parse_compact_actions(text)

    # Also capture the raw compact text for debugging
    actions_match = re.search(r'```actions\s*([\s\S]*?)\s*```', text)
    if actions_match:
        result["compact_actions_text"] = actions_match.group(1).strip()
    if compact_actions:
        result["actions"] = compact_actions
        print(f"[Parse] Got {len(compact_actions)} actions from compact format")

    # 2. Extract JSON metadata (analysis, strategy, learnings) regardless of action format
    data = parse_json_robust(text)

    if data and isinstance(data, dict):
        result["analysis"] = data.get('analysis', '')
        result["strategy_summary"] = data.get('strategy_summary', '')
        result["learnings"] = data.get('learnings', '')

        # If we didn't get compact actions, try JSON actions as fallback
        if not result["actions"]:
            json_actions = data.get('actions', [])
            if json_actions:
                result["actions"] = json_actions
                print(f"[Parse] Got {len(json_actions)} actions from JSON format")

        # Print feedback
        if result["analysis"]:
            print(f"[AI Analysis] {result['analysis'][:200]}...")
        if result["strategy_summary"]:
            strat = result["strategy_summary"]
            if isinstance(strat, dict):
                if strat.get("keep_next_time"):
                    print(f"[AI Keep] {', '.join(strat['keep_next_time'][:3])}")
                if strat.get("change_next_time"):
                    print(f"[AI Change] {', '.join(strat['change_next_time'][:3])}")
        if result["learnings"]:
            print(f"[AI Learning] {result['learnings']}")
    elif data and isinstance(data, list) and not result["actions"]:
        # Got just an array (old format or fallback extraction)
        result["actions"] = data
        print("[Warning] Only extracted actions array, no metadata")
    elif not result["actions"]:
        print("[Error] Could not parse actions from response")
        print(f"[Debug] Raw response:\n{text[:500]}...")

    return result


MUTATION_PROMPT = f"""You are an AI artist editing an existing pixel art script in Purple Computer's Doodle mode.

You will receive the BEST script so far and a screenshot of its result, plus a specific improvement target from the judge.

Your job: modify the script to fix ONLY the identified weakness while keeping everything else the same.

## RULES
1. Keep 70-90% of the script unchanged. Only modify the lines related to the weakness.
2. Do NOT restructure the entire drawing. Preserve the overall layout, colors, and composition.
3. The canvas is {CANVAS_WIDTH}x{CANVAS_HEIGHT}. Coordinates must stay in bounds.
4. Use the same compact format: L<color><x1>,<y1>,<x2>,<y2> for lines, P<color><x>,<y> for points.
5. Color mixing works by painting over: Yellow + Blue = GREEN, Yellow + Red = ORANGE, Red + Blue = PURPLE.

## COMPACT ACTION FORMAT
**L = Line**: `L<color><x1>,<y1>,<x2>,<y2>` (horizontal, vertical, or diagonal)
**P = Point**: `P<color><x>,<y>` (single cell)

## RESPONSE FORMAT

```json
{{
  "analysis": "What I changed and why",
  "learnings": "Key insight from this edit"
}}
```

```actions
(modified script here)
```

Output the COMPLETE modified script (not just the changed lines). The canvas is cleared and this script runs from scratch."""


def call_focused_mutation_api(
    best_image_base64: str,
    best_script_text: str,
    improvement_target: str,
    goal: str,
    api_key: str,
    execution_model: str = "claude-sonnet-4-20250514",
    reference_image_base64: str = None,
    reference_image_media_type: str = None,
) -> dict:
    """Generate a focused mutation of the best script targeting a specific weakness.

    Unlike call_vision_api which generates from scratch with full context,
    this function sends only the best image + script + a specific improvement
    target from the judge. The AI edits the existing script rather than
    regenerating from scratch.

    Args:
        best_image_base64: Screenshot of the current best attempt (PNG base64)
        best_script_text: The L/P command text of the best attempt
        improvement_target: Specific improvement suggestion from the judge
        goal: What we're trying to draw
        api_key: Anthropic API key
        execution_model: Model to use
        reference_image_base64: Optional reference image
        reference_image_media_type: Media type for reference image

    Returns:
        Dict with keys: analysis, strategy_summary, learnings, actions
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    user_message = f"""## Goal: {goal}

## CURRENT BEST SCRIPT
```actions
{best_script_text}
```

## IMPROVEMENT TARGET
{improvement_target}

Modify the script above to address this specific weakness. Keep everything else the same.
Output the complete modified script."""

    message_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": best_image_base64,
            },
        },
        {"type": "text", "text": "CURRENT BEST (the script above produced this image)"},
    ]

    if reference_image_base64:
        message_content.extend([
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": reference_image_media_type or "image/png",
                    "data": reference_image_base64,
                },
            },
            {"type": "text", "text": "REFERENCE IMAGE: Use as a visual guide."},
        ])

    message_content.append({"type": "text", "text": user_message})

    response = client.messages.create(
        model=execution_model,
        max_tokens=4000,
        temperature=1.0,
        system=MUTATION_PROMPT,
        messages=[{
            "role": "user",
            "content": message_content,
        }],
    )

    text = response.content[0].text

    result = {
        "analysis": "",
        "strategy_summary": "",
        "learnings": "",
        "actions": [],
        "raw_response": text,
        "compact_actions_text": "",
    }

    compact_actions = parse_compact_actions(text)
    actions_match = re.search(r'```actions\s*([\s\S]*?)\s*```', text)
    if actions_match:
        result["compact_actions_text"] = actions_match.group(1).strip()
    if compact_actions:
        result["actions"] = compact_actions
        print(f"[Mutation Parse] Got {len(compact_actions)} actions from compact format")

    data = parse_json_robust(text)
    if data and isinstance(data, dict):
        result["analysis"] = data.get('analysis', '')
        result["learnings"] = data.get('learnings', '')
        if not result["actions"]:
            json_actions = data.get('actions', [])
            if json_actions:
                result["actions"] = json_actions

    return result


def _format_judge_visual_identity(visual_identity: dict = None) -> str:
    """Format visual identity info for the judge prompt."""
    if not visual_identity:
        return ""
    lines = []
    if visual_identity.get('defining_features'):
        features = ", ".join(visual_identity['defining_features'])
        lines.append(f"SUBJECT-SPECIFIC: The drawing MUST show these defining features: {features}")
    if visual_identity.get('common_mistakes'):
        mistakes = visual_identity['common_mistakes']
        if isinstance(mistakes, list):
            mistakes = "; ".join(mistakes)
        lines.append(f"PENALIZE if the drawing shows these mistakes: {mistakes}")
    if visual_identity.get('structural_connections'):
        connections = visual_identity['structural_connections']
        if isinstance(connections, list):
            connections = "; ".join(connections)
        lines.append(f"STRUCTURAL CONNECTIONS: Check that these are correct: {connections}")
    if lines:
        return "\n".join(lines) + "\n\n"
    return ""


def call_judge_api(
    image_a_base64: str,
    image_b_base64: str,
    goal: str,
    api_key: str,
    judge_model: str = "claude-sonnet-4-20250514",
    visual_identity: dict = None,
) -> dict:
    """Single judge API call comparing two images.

    Uses a fresh context and focused prompt to get an objective comparison.
    Images are labeled neutrally as "Image A" and "Image B" with no temporal
    or iteration information to avoid biasing the model.

    Args:
        image_a_base64: First image (PNG base64)
        image_b_base64: Second image (PNG base64)
        goal: What we're trying to draw
        api_key: Anthropic API key
        judge_model: Model to use for judging

    Returns:
        Dict with keys: winner ("A" or "B"), reasoning, confidence
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    judge_prompt = f"""You are judging pixel art drawings. Your ONLY job is to decide which image better represents the goal.

GOAL: "{goal}"

You will see two images: Image A and Image B.

Score EACH image on these criteria (1-5 scale, 5 is best):
1. **shape_accuracy**: Do the shapes look like the goal? Organic oval bodies beat flat rectangles. Curved edges beat straight edges.
2. **recognizability**: Can you tell what it is at a glance?
3. **structural_connections**: Do parts connect at correct positions? Fronds from TOP of trunk, legs from BOTTOM of body, etc.
4. **color_quality**: Are the colors appropriate and well-mixed?
5. **detail_and_shading**: Texture, highlights, gradients, fine details, 3D depth.
6. **cleanliness**: Clean edges vs stray pixels, artifacts, messy overhangs.

SHAPE PENALTIES: Penalize rectangular/boxy bodies (same width every row), stepped/staircase tails or limbs, and flat straight edges where curves should be.

BACKGROUND PENALTIES: Penalize large monotone background fills. A detailed subject on a mostly-empty canvas is BETTER than a simple subject surrounded by flat fills.

ARTIFACT PENALTIES: Penalize stray colored pixels outside shape boundaries.

{_format_judge_visual_identity(visual_identity)}Be OBJECTIVE. Simpler is not always worse.
A messy attempt with stripes everywhere is WORSE than a clean simple drawing.

Respond with JSON only:
```json
{{
  "winner": "A" or "B",
  "reasoning": "Brief explanation of why the winner is better",
  "confidence": "high" or "medium" or "low",
  "scores_a": {{"shape_accuracy": 3, "recognizability": 4, "structural_connections": 3, "color_quality": 3, "detail_and_shading": 2, "cleanliness": 4}},
  "scores_b": {{"shape_accuracy": 3, "recognizability": 4, "structural_connections": 3, "color_quality": 3, "detail_and_shading": 2, "cleanliness": 4}},
  "weakest_criterion": "the criterion name where the winner scored lowest or could improve most",
  "specific_improvement": "one concrete, actionable suggestion to improve the winner's weakest area"
}}
```"""

    message_content = [
        {"type": "text", "text": "**Image A:**"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_a_base64,
            },
        },
        {"type": "text", "text": "**Image B:**"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_b_base64,
            },
        },
        {"type": "text", "text": "Which image better represents the goal? Respond with JSON only."},
    ]

    response = client.messages.create(
        model=judge_model,
        max_tokens=600,  # Room for per-criterion scores
        system=judge_prompt,
        messages=[{
            "role": "user",
            "content": message_content,
        }],
    )

    text = response.content[0].text

    # Parse JSON response using robust parser
    result = {
        "winner": None,
        "reasoning": "",
        "confidence": "low",
        "scores_a": None,
        "scores_b": None,
        "weakest_criterion": None,
        "specific_improvement": None,
    }

    data = parse_json_robust(text)

    if data and isinstance(data, dict):
        winner = data.get("winner", "")
        result["winner"] = winner.upper() if isinstance(winner, str) else None
        result["reasoning"] = data.get("reasoning", "")
        result["confidence"] = data.get("confidence", "low")
        result["scores_a"] = data.get("scores_a")
        result["scores_b"] = data.get("scores_b")
        result["weakest_criterion"] = data.get("weakest_criterion")
        result["specific_improvement"] = data.get("specific_improvement")

        # Sanity check: does the reasoning contradict the winner?
        # Haiku sometimes writes reasoning favoring one image but puts the wrong
        # letter in the winner field.
        if result["winner"] in ("A", "B") and result["reasoning"]:
            reasoning_lower = result["reasoning"].lower()
            other = "B" if result["winner"] == "A" else "A"
            # Check if reasoning says the OTHER image is better
            favors_other = (
                f"image {other.lower()} better" in reasoning_lower
                or f"image {other.lower()} is better" in reasoning_lower
                or f"image {other.lower()} more closely" in reasoning_lower
                or f"image {other.lower()} more accurately" in reasoning_lower
            )
            # Check reasoning does NOT also favor the declared winner
            favors_winner = (
                f"image {result['winner'].lower()} better" in reasoning_lower
                or f"image {result['winner'].lower()} is better" in reasoning_lower
                or f"image {result['winner'].lower()} more closely" in reasoning_lower
                or f"image {result['winner'].lower()} more accurately" in reasoning_lower
            )
            if favors_other and not favors_winner:
                print(f"[Judge] Reasoning contradicts winner! Reasoning favors {other}, winner says {result['winner']}. Flipping to {other}.")
                result["winner"] = other
    else:
        print("[Judge] Could not parse JSON, trying text extraction")
        # Try to extract winner from text
        if "winner" in text.lower():
            if '"A"' in text or "'A'" in text or "winner: A" in text.lower() or "Winner: A" in text:
                result["winner"] = "A"
            elif '"B"' in text or "'B'" in text or "winner: B" in text.lower() or "Winner: B" in text:
                result["winner"] = "B"
        # Try to extract reasoning
            reason_match = re.search(r'"reasoning"\s*:\s*"([^"]*)"', text)
        if reason_match:
            result["reasoning"] = reason_match.group(1)

    return result


def _is_blank_image(png_base64: str, max_colors: int = 10) -> bool:
    """Check if a PNG image is nearly uniform (blank canvas).

    A blank or near-blank image has very few unique colors (e.g., just the
    background). Real drawings have many colors from brush strokes, shading, etc.

    Returns True if the image has fewer than max_colors unique colors.
    """
    try:
        from PIL import Image
        img_bytes = base64.b64decode(png_base64)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        # getcolors returns None if more than maxcolors unique colors
        colors = img.getcolors(maxcolors=max_colors + 1)
        return colors is not None  # fewer than max_colors unique colors = blank
    except Exception:
        return False  # can't determine, assume not blank


def judge_with_single_call(
    best_image_base64: str,
    challenger_image_base64: str,
    goal: str,
    api_key: str,
    best_is_unvalidated: bool = False,
    judge_model: str = "claude-sonnet-4-20250514",
    visual_identity: dict = None,
) -> dict:
    """Judge two images with a single Sonnet call, randomized A/B position.

    Randomizes which image is A vs B to eliminate positional bias.
    Uses Sonnet for reliable single-call judging (cheaper and more consistent
    than double-Haiku, which produced 37% split decisions).

    Args:
        best_image_base64: Current best image (PNG base64)
        challenger_image_base64: New challenger image (PNG base64)
        goal: What we're trying to draw
        api_key: Anthropic API key
        best_is_unvalidated: If True, the current best has never won a judge
            comparison. Not used for split decisions (no splits with single call)
            but kept for API compatibility.
        judge_model: Model to use for judging

    Returns:
        Dict with keys: winner ("best" or "challenger"), reasoning, confidence
    """
    # Randomize which image is A to eliminate positional bias
    swapped = random.choice([True, False])

    if swapped:
        img_a, img_b = challenger_image_base64, best_image_base64
    else:
        img_a, img_b = best_image_base64, challenger_image_base64

    result = call_judge_api(img_a, img_b, goal, api_key, judge_model=judge_model, visual_identity=visual_identity)

    # Map A/B back to best/challenger
    if result["winner"] == "A":
        winner = "challenger" if swapped else "best"
    elif result["winner"] == "B":
        winner = "best" if swapped else "challenger"
    else:
        print("[Judge] Inconclusive, keeping current best")
        return {"winner": "best", "reasoning": "Judge inconclusive", "confidence": "low"}

    print(f"[Judge] Result: {winner} (raw: {result['winner']}, swapped: {swapped})")

    # Map scores back: if swapped, A=challenger and B=best, so swap them back
    if swapped:
        scores_best = result.get("scores_b")
        scores_challenger = result.get("scores_a")
    else:
        scores_best = result.get("scores_a")
        scores_challenger = result.get("scores_b")

    return {
        "winner": winner,
        "reasoning": result["reasoning"],
        "confidence": result.get("confidence", "medium"),
        "scores_best": scores_best,
        "scores_challenger": scores_challenger,
        "weakest_criterion": result.get("weakest_criterion"),
        "specific_improvement": result.get("specific_improvement"),
    }


def call_batch_judge_api(
    candidate_images: list[tuple[str, str]],
    best_image_base64: str,
    goal: str,
    api_key: str,
    judge_model: str = "claude-sonnet-4-20250514",
    visual_identity: dict = None,
) -> dict:
    """Judge multiple candidates against the current best in a single API call.

    Instead of N separate pairwise judge calls, this sends all candidate images
    plus the current best in one call and asks the judge to pick the overall winner.
    Images are shuffled to eliminate positional bias.

    Args:
        candidate_images: List of (label, png_base64) tuples for each candidate
        best_image_base64: Current best image (PNG base64)
        goal: What we're trying to draw
        api_key: Anthropic API key
        judge_model: Model to use for judging
        visual_identity: Visual identity info for subject-specific judging

    Returns:
        Dict with keys: winner_label (str or "best"), reasoning, confidence,
        scores (dict of label -> scores), weakest_criterion, specific_improvement
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Build image list: best + all candidates, shuffled
    all_entries = [("best", best_image_base64)] + list(candidate_images)
    random.shuffle(all_entries)

    # Assign neutral labels (Image 1, Image 2, etc.)
    label_map = {}  # neutral_label -> original_label
    reverse_map = {}  # original_label -> neutral_label
    for idx, (orig_label, _) in enumerate(all_entries):
        neutral = str(idx + 1)
        label_map[neutral] = orig_label
        reverse_map[orig_label] = neutral

    num_images = len(all_entries)
    image_labels = ", ".join(f"Image {i+1}" for i in range(num_images))

    # Build scores example
    scores_example = ", ".join(f'"{i+1}": {{"shape_accuracy": 3, "recognizability": 4, "structural_connections": 3, "color_quality": 3, "detail_and_shading": 2, "cleanliness": 4}}' for i in range(num_images))

    judge_prompt = f"""You are judging pixel art drawings. Your ONLY job is to decide which image best represents the goal.

GOAL: "{goal}"

You will see {num_images} images: {image_labels}.

Score EACH image on these criteria (1-5 scale, 5 is best):
1. **shape_accuracy**: Do the shapes look like the goal? Organic oval bodies beat flat rectangles. Curved edges beat straight edges.
2. **recognizability**: Can you tell what it is at a glance?
3. **structural_connections**: Do parts connect at correct positions? Fronds from TOP of trunk, legs from BOTTOM of body, etc.
4. **color_quality**: Are the colors appropriate and well-mixed?
5. **detail_and_shading**: Texture, highlights, gradients, fine details, 3D depth.
6. **cleanliness**: Clean edges vs stray pixels, artifacts, messy overhangs.

SHAPE PENALTIES: Penalize rectangular/boxy bodies (same width every row), stepped/staircase tails or limbs, and flat straight edges where curves should be.

BACKGROUND PENALTIES: Penalize large monotone background fills. A detailed subject on a mostly-empty canvas is BETTER than a simple subject surrounded by flat fills.

ARTIFACT PENALTIES: Penalize stray colored pixels outside shape boundaries.

{_format_judge_visual_identity(visual_identity)}Be OBJECTIVE. Simpler is not always worse.
A messy attempt with stripes everywhere is WORSE than a clean simple drawing.

Respond with JSON only:
```json
{{
  "winner": "1" or "2" or ... (the image number of the best drawing),
  "reasoning": "Brief explanation of why the winner is best",
  "confidence": "high" or "medium" or "low",
  "scores": {{{scores_example}}},
  "weakest_criterion": "the criterion name where the winner scored lowest or could improve most",
  "specific_improvement": "one concrete, actionable suggestion to improve the winner's weakest area"
}}
```"""

    message_content = []
    for idx, (_, img_base64) in enumerate(all_entries):
        message_content.extend([
            {"type": "text", "text": f"**Image {idx + 1}:**"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_base64,
                },
            },
        ])
    message_content.append({"type": "text", "text": f"Which of the {num_images} images best represents the goal? Respond with JSON only."})

    response = client.messages.create(
        model=judge_model,
        max_tokens=800,
        system=judge_prompt,
        messages=[{
            "role": "user",
            "content": message_content,
        }],
    )

    text = response.content[0].text
    data = parse_json_robust(text)

    result = {
        "winner_label": "best",
        "reasoning": "",
        "confidence": "low",
        "scores": {},
        "weakest_criterion": None,
        "specific_improvement": None,
        "label_map": label_map,
        "reverse_map": reverse_map,
    }

    if data and isinstance(data, dict):
        winner_neutral = str(data.get("winner", ""))
        result["reasoning"] = data.get("reasoning", "")
        result["confidence"] = data.get("confidence", "low")
        result["weakest_criterion"] = data.get("weakest_criterion")
        result["specific_improvement"] = data.get("specific_improvement")

        # Map neutral winner back to original label
        if winner_neutral in label_map:
            result["winner_label"] = label_map[winner_neutral]
        else:
            print(f"[Judge] Could not map winner '{winner_neutral}' to a label, keeping best")

        # Map scores back to original labels
        raw_scores = data.get("scores", {})
        for neutral_label, scores in raw_scores.items():
            orig = label_map.get(str(neutral_label))
            if orig:
                result["scores"][orig] = scores

        print(f"[Judge Batch] Winner: {result['winner_label']} (neutral: {winner_neutral}, {result['confidence']} confidence)")
        print(f"[Judge Batch] Reasoning: {result['reasoning']}")
        if result["scores"]:
            for lbl, sc in result["scores"].items():
                if isinstance(sc, dict):
                    total = sum(sc.values())
                    print(f"[Judge Batch]   {lbl}: total={total} {sc}")
    else:
        print("[Judge Batch] Could not parse judge response")
        print(f"[Judge Batch] Raw: {text[:300]}")

    return result


def load_env_file():
    """Load environment variables from tools/.env if it exists."""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())


def run_visual_feedback_loop(
    goal: str,
    iterations: int = 5,
    output_dir: str = None,
    api_key: str = None,
    execution_model: str = "claude-sonnet-4-20250514",
    judge_model: str = "claude-sonnet-4-20250514",
    existing_plan: dict = None,
    reference_image: str = None,
    max_candidates: int = 3,
) -> None:
    """Run the AI drawing loop with real visual feedback.

    If existing_plan is provided, skips the planning phase and uses that plan directly.
    """

    # Load from tools/.env if present
    load_env_file()

    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: Set ANTHROPIC_API_KEY in tools/.env or environment")
        sys.exit(1)

    # Always create a timestamped subfolder for each run
    if output_dir is None:
        output_dir = generate_output_dir()
    else:
        # Check if path already has a timestamp (YYYYMMDD_HHMMSS pattern)
        if not re.search(r'\d{8}_\d{6}$', output_dir):
            # Add timestamp subfolder
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(output_dir, timestamp)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    screenshot_dir = os.path.join(output_dir, "screenshots")

    # Prepare small reference image for execution model (once)
    ref_base64 = None
    ref_media_type = None
    if reference_image:
        ref_base64, ref_media_type = prepare_reference_for_execution(reference_image)

    # Start the app
    controller = PurpleController()

    try:
        controller.start(screenshot_dir)

        # Create or use existing drawing plan
        print("\n" + "="*50)
        print("PLANNING PHASE")
        print("="*50)
        if existing_plan is not None:
            plan = existing_plan
            print("[Plan] Using provided plan:")
            print(f"  Description: {plan.get('description', 'N/A')}")
        else:
            plan = call_planning_api(goal, iterations, api_key, reference_image=reference_image)
        visual_identity = plan.get('visual_identity') if plan else None

        # Save plan to file
        plan_path = os.path.join(output_dir, "plan.json")
        with open(plan_path, 'w') as f:
            json.dump(plan, f, indent=2)
        print(f"[Saved] Plan: {plan_path}")

        # Switch to Doodle mode and enter paint mode
        print("\n[Setup] Switching to Doodle mode...")
        controller.switch_to_doodle()
        controller.enter_paint_mode()
        time.sleep(0.2)

        all_results = []  # Store full results from each iteration
        iteration_scripts = []  # Store each iteration's complete script
        accumulated_learnings = []  # Compact learnings (not full scripts)
        previous_strategy = None  # Strategy from previous attempt

        # Track best result for A vs B comparison (judged by separate API call)
        best_attempt = None  # Which attempt produced the best result
        best_image_base64 = None
        best_reason = None

        # Option B: Track runner-up (second best) for more context
        runner_up_attempt = None
        runner_up_image_base64 = None
        runner_up_reason = None

        # Track consecutive losses for refinement mode and early stopping
        consecutive_losses = 0
        best_compact_actions = None  # Compact L/P text of the best attempt's script
        iteration_compact_actions = {}  # Map iteration_num -> compact_actions_text
        max_stale_iterations = 10  # Stop after this many consecutive losses

        judge_history = []  # Track all judge comparisons for monitoring
        last_judge_feedback = None  # Option A: pass judge reasoning to execution AI

        # Track what's ACTUALLY on the canvas (not just loop index)
        # This is crucial when iterations fail - the canvas still shows the last successful result
        canvas_shows_attempt = None  # Which attempt's result is currently on canvas

        for i in range(iterations):
            print(f"\n{'='*50}")
            print(f"ATTEMPT {i + 1}/{iterations}")
            if best_attempt:
                print(f"Current Best: Attempt {best_attempt}'s result")
            if runner_up_attempt:
                print(f"Runner-up: Attempt {runner_up_attempt}'s result")
            if consecutive_losses > 0:
                if consecutive_losses < 3 or not best_compact_actions:
                    mode = "normal"
                elif consecutive_losses <= 4:
                    mode = "refinement-targeted"
                elif consecutive_losses <= 6:
                    mode = "refinement-restructure"
                else:
                    mode = "refinement-overhaul"
                print(f"Consecutive losses: {consecutive_losses} (mode: {mode})")
            print('='*50)

            # Determine how many candidates to generate this iteration
            # Ramp-up: 2 candidates when not stuck, all candidates when stuck
            if consecutive_losses < 3 or not best_compact_actions:
                num_candidates = min(2, max_candidates)
            else:
                num_candidates = max_candidates

            # For the first iteration, just generate one candidate (no best to compare against)
            if best_attempt is None:
                num_candidates = 1

            # Take screenshot of current canvas state (for the informed regen candidate)
            svg_path = controller.take_screenshot()
            if not svg_path:
                print("[Error] Failed to capture screenshot")
                continue

            screenshot_dir_path = os.path.dirname(svg_path)
            if i == 0:
                new_name = "iteration_0_blank.svg"
                print("[Screenshot] iteration_0_blank = blank canvas (before any drawing)")
            else:
                new_name = f"iteration_{i}.svg"
                print(f"[Screenshot] iteration_{i} = Attempt {i}'s result")
            new_svg_path = os.path.join(screenshot_dir_path, new_name)
            os.rename(svg_path, new_svg_path)
            svg_path = new_svg_path

            png_base64 = svg_to_png_base64(svg_path)
            if not png_base64:
                print("[Error] Failed to convert SVG to PNG")
                continue

            png_path = svg_path.replace('.svg', '_cropped.png')
            with open(png_path, 'wb') as f:
                f.write(base64.standard_b64decode(png_base64))

            # Generate candidates using different strategies
            # Each candidate is: (label, actions, result, compact_text)
            candidates = []

            debug_dir = os.path.join(output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)

            # --- Candidate B: Informed regen (current approach, always generated) ---
            print("\n[Candidate B] Generating informed regen (full context)...")
            informed_result = None
            for retry in range(3):
                if retry > 0:
                    print(f"[Retry] Attempt {retry + 1}/3 for informed regen...")
                    time.sleep(1)
                informed_result = call_vision_api(
                    image_base64=png_base64,
                    goal=goal,
                    iteration=i + 1,
                    max_iterations=iterations,
                    api_key=api_key,
                    plan=plan,
                    accumulated_learnings=accumulated_learnings,
                    previous_strategy=previous_strategy,
                    judge_feedback=last_judge_feedback,
                    best_image_base64=best_image_base64,
                    best_attempt_num=best_attempt,
                    runner_up_image_base64=runner_up_image_base64,
                    runner_up_attempt_num=runner_up_attempt,
                    best_script_text=best_compact_actions,
                    consecutive_losses=consecutive_losses,
                    execution_model=execution_model,
                    reference_image_base64=ref_base64,
                    reference_image_media_type=ref_media_type,
                )
                if informed_result.get("actions"):
                    break
            if informed_result and informed_result.get("actions"):
                candidates.append(("informed", informed_result.get("actions"), informed_result, informed_result.get("compact_actions_text", "")))
                # Save debug
                raw_path = os.path.join(debug_dir, f"iteration_{i+1:02d}_informed_raw.txt")
                with open(raw_path, 'w') as f:
                    f.write(informed_result.get("raw_response", ""))
                compact_path = os.path.join(debug_dir, f"iteration_{i+1:02d}_informed_compact.txt")
                with open(compact_path, 'w') as f:
                    f.write(informed_result.get("compact_actions_text", ""))
                print(f"[Candidate B] Got {len(informed_result['actions'])} actions")

            # --- Candidate A: Focused mutation (only when we have a best script and judge feedback) ---
            if num_candidates >= 2 and best_compact_actions and last_judge_feedback:
                improvement_target = last_judge_feedback.get("specific_improvement", "")
                weakest = last_judge_feedback.get("weakest_criterion", "")
                if improvement_target:
                    mutation_instruction = f"Weakness: {weakest}. Fix: {improvement_target}"
                else:
                    mutation_instruction = f"Improve the weakest area: {weakest}" if weakest else "Improve overall quality"

                print(f"\n[Candidate A] Generating focused mutation: {mutation_instruction[:80]}...")
                mutation_result = call_focused_mutation_api(
                    best_image_base64=best_image_base64,
                    best_script_text=best_compact_actions,
                    improvement_target=mutation_instruction,
                    goal=goal,
                    api_key=api_key,
                    execution_model=execution_model,
                    reference_image_base64=ref_base64,
                    reference_image_media_type=ref_media_type,
                )
                if mutation_result.get("actions"):
                    candidates.append(("mutation", mutation_result.get("actions"), mutation_result, mutation_result.get("compact_actions_text", "")))
                    raw_path = os.path.join(debug_dir, f"iteration_{i+1:02d}_mutation_raw.txt")
                    with open(raw_path, 'w') as f:
                        f.write(mutation_result.get("raw_response", ""))
                    print(f"[Candidate A] Got {len(mutation_result['actions'])} actions")
                else:
                    print("[Candidate A] Failed to generate mutation")

            # --- Candidate C: Fresh regen (no script context, higher temp) ---
            if best_image_base64:
                print("\n[Candidate C] Generating fresh regen (no script, temp 1.2)...")
                fresh_result = None
                for retry in range(2):
                    if retry > 0:
                        print(f"[Retry] Attempt {retry + 1}/2 for fresh regen...")
                        time.sleep(1)
                    # Fresh regen: send best image but NOT the best script
                    # Use a higher consecutive_losses to trigger higher temperature
                    fresh_result = call_vision_api(
                        image_base64=png_base64,
                        goal=goal,
                        iteration=i + 1,
                        max_iterations=iterations,
                        api_key=api_key,
                        plan=plan,
                        accumulated_learnings=accumulated_learnings,
                        previous_strategy=None,  # No strategy anchoring
                        judge_feedback=last_judge_feedback,
                        best_image_base64=best_image_base64,
                        best_attempt_num=best_attempt,
                        runner_up_image_base64=None,  # Skip runner-up to save tokens
                        runner_up_attempt_num=None,
                        best_script_text=None,  # Key: no script = forces fresh approach
                        consecutive_losses=max(consecutive_losses, 5),  # Force higher temp
                        execution_model=execution_model,
                        reference_image_base64=ref_base64,
                        reference_image_media_type=ref_media_type,
                    )
                    if fresh_result and fresh_result.get("actions"):
                        break
                if fresh_result and fresh_result.get("actions"):
                    candidates.append(("fresh", fresh_result.get("actions"), fresh_result, fresh_result.get("compact_actions_text", "")))
                    raw_path = os.path.join(debug_dir, f"iteration_{i+1:02d}_fresh_raw.txt")
                    with open(raw_path, 'w') as f:
                        f.write(fresh_result.get("raw_response", ""))
                    print(f"[Candidate C] Got {len(fresh_result['actions'])} actions")
                else:
                    print("[Candidate C] Failed to generate fresh regen")

            # --- Candidate D: Second fresh regen (independent take) ---
            if best_image_base64:
                print("\n[Candidate D] Generating second fresh regen...")
                fresh2_result = None
                for retry in range(2):
                    if retry > 0:
                        print(f"[Retry] Attempt {retry + 1}/2 for fresh regen 2...")
                        time.sleep(1)
                    fresh2_result = call_vision_api(
                        image_base64=png_base64,
                        goal=goal,
                        iteration=i + 1,
                        max_iterations=iterations,
                        api_key=api_key,
                        plan=plan,
                        accumulated_learnings=accumulated_learnings,
                        previous_strategy=None,
                        judge_feedback=last_judge_feedback,
                        best_image_base64=best_image_base64,
                        best_attempt_num=best_attempt,
                        runner_up_image_base64=None,
                        runner_up_attempt_num=None,
                        best_script_text=None,
                        consecutive_losses=max(consecutive_losses, 5),
                        execution_model=execution_model,
                        reference_image_base64=ref_base64,
                        reference_image_media_type=ref_media_type,
                    )
                    if fresh2_result and fresh2_result.get("actions"):
                        break
                if fresh2_result and fresh2_result.get("actions"):
                    candidates.append(("fresh2", fresh2_result.get("actions"), fresh2_result, fresh2_result.get("compact_actions_text", "")))
                    raw_path = os.path.join(debug_dir, f"iteration_{i+1:02d}_fresh2_raw.txt")
                    with open(raw_path, 'w') as f:
                        f.write(fresh2_result.get("raw_response", ""))
                    print(f"[Candidate D] Got {len(fresh2_result['actions'])} actions")
                else:
                    print("[Candidate D] Failed to generate fresh regen 2")

            if not candidates:
                print(f"[Error] No candidates generated for iteration {i + 1}")
                continue

            print(f"\n[Candidates] Generated {len(candidates)} candidates: {[c[0] for c in candidates]}")

            # === PHASE 1: Execute all candidates and collect screenshots ===
            # Each entry: (label, attempt_label, actions, result, compact, png_base64)
            executed_candidates = []

            for c_idx, (label, c_actions, c_result, c_compact) in enumerate(candidates):
                attempt_label = f"{i + 1}{chr(ord('a') + c_idx)}"  # e.g., "2a", "2b", "2c", "2d"

                # Clear canvas
                if canvas_shows_attempt is not None or c_idx > 0:
                    print(f"[Clear] Clearing canvas for candidate {label}...")
                    try:
                        controller.clear_canvas()
                    except RuntimeError as e:
                        print(f"[ERROR] Failed to clear canvas: {e}")
                        break
                    time.sleep(0.3)

                # Execute
                print(f"[Execute] Running candidate {label}: {len(c_actions)} actions...")
                controller.execute_actions(c_actions)
                time.sleep(0.5)

                # Take screenshot
                c_svg = controller.take_screenshot()
                if not c_svg:
                    print(f"[Error] Failed to capture screenshot for candidate {label}")
                    continue

                c_svg_new = os.path.join(screenshot_dir_path, f"iteration_{attempt_label}_{label}.svg")
                os.rename(c_svg, c_svg_new)
                c_png = svg_to_png_base64(c_svg_new)
                if not c_png:
                    print(f"[Error] Failed to convert candidate {label} SVG to PNG")
                    continue

                # Save cropped PNG
                c_png_path = c_svg_new.replace('.svg', '_cropped.png')
                with open(c_png_path, 'wb') as f:
                    f.write(base64.standard_b64decode(c_png))

                # Store compact actions and script
                iteration_compact_actions[attempt_label] = c_compact
                iteration_scripts.append({"iteration": attempt_label, "actions": c_actions})
                canvas_shows_attempt = attempt_label

                executed_candidates.append((label, attempt_label, c_actions, c_result, c_compact, c_png))

            if not executed_candidates:
                print(f"[Error] No candidates executed successfully for iteration {i + 1}")
                continue

            # === PHASE 2: Judge all candidates against best ===
            best_challenger_label = None
            best_challenger_result = None
            best_challenger_judge = None

            if best_attempt is None:
                # No best yet: pick the first executed candidate as initial best
                label, attempt_label, c_actions, c_result, c_compact, c_png = executed_candidates[0]
                best_attempt = attempt_label
                best_image_base64 = c_png
                best_reason = "Initial drawing (first result)"
                best_compact_actions = c_compact
                best_challenger_label = label
                best_challenger_result = c_result
                print(f"[Best] Setting candidate {label} (Attempt {attempt_label}) as initial best")

                # If there are more candidates from the first iteration, judge them
                remaining = executed_candidates[1:]
                if remaining:
                    # Use batch judge for the remaining candidates
                    candidate_images = [(lbl, png) for lbl, _, _, _, _, png in remaining]
                    print(f"\n[Judge Batch] Comparing {len(candidate_images)} remaining candidates against initial best...")
                    batch_result = call_batch_judge_api(
                        candidate_images=candidate_images,
                        best_image_base64=best_image_base64,
                        goal=goal,
                        api_key=api_key,
                        judge_model=judge_model,
                        visual_identity=visual_identity,
                    )
                    winner_label = batch_result.get("winner_label", "best")
                    if winner_label != "best":
                        # A candidate beat the initial best
                        for lbl, albl, c_act, c_res, c_cmp, c_img in remaining:
                            if lbl == winner_label:
                                runner_up_attempt = best_attempt
                                runner_up_image_base64 = best_image_base64
                                runner_up_reason = best_reason
                                best_attempt = albl
                                best_image_base64 = c_img
                                best_reason = batch_result.get("reasoning", "")
                                best_compact_actions = c_cmp
                                best_challenger_label = lbl
                                best_challenger_result = c_res
                                print(f"[Judge] ✓ Candidate {lbl} (Attempt {albl}) is the new best")
                                break

                    judge_history.append({
                        "judged_during_attempt": f"{i + 1}",
                        "judge_type": "batch",
                        "candidates": [lbl for lbl, _, _, _, _, _ in executed_candidates],
                        "winner_label": winner_label,
                        "new_best_attempt": best_attempt,
                        "reasoning": batch_result.get("reasoning", ""),
                        "confidence": batch_result.get("confidence", "low"),
                        "scores": batch_result.get("scores", {}),
                        "weakest_criterion": batch_result.get("weakest_criterion"),
                        "specific_improvement": batch_result.get("specific_improvement"),
                    })
                    best_challenger_judge = batch_result

            elif _is_blank_image(best_image_base64):
                # Best is blank, auto-accept first candidate
                label, attempt_label, c_actions, c_result, c_compact, c_png = executed_candidates[0]
                runner_up_attempt = best_attempt
                runner_up_image_base64 = best_image_base64
                runner_up_reason = best_reason
                best_attempt = attempt_label
                best_image_base64 = c_png
                best_reason = "Auto-accepted (previous best was blank)"
                best_compact_actions = c_compact
                consecutive_losses = 0
                best_challenger_label = label
                best_challenger_result = c_result
                print(f"[Judge] Auto-accepted candidate {label} (previous best was blank)")
                judge_history.append({
                    "judged_during_attempt": f"{i + 1}",
                    "judge_type": "auto",
                    "winner_label": label,
                    "new_best_attempt": attempt_label,
                    "reasoning": "Previous best was blank, auto-accepted",
                    "confidence": "high",
                })

            else:
                # Normal case: batch judge all candidates against current best
                candidate_images = [(lbl, png) for lbl, _, _, _, _, png in executed_candidates]
                print(f"\n[Judge Batch] Comparing {len(candidate_images)} candidates against best (Attempt {best_attempt})...")
                batch_result = call_batch_judge_api(
                    candidate_images=candidate_images,
                    best_image_base64=best_image_base64,
                    goal=goal,
                    api_key=api_key,
                    judge_model=judge_model,
                    visual_identity=visual_identity,
                )

                winner_label = batch_result.get("winner_label", "best")
                reasoning = batch_result.get("reasoning", "")
                confidence = batch_result.get("confidence", "low")

                if winner_label != "best":
                    # A candidate beat the current best
                    for lbl, albl, c_act, c_res, c_cmp, c_img in executed_candidates:
                        if lbl == winner_label:
                            runner_up_attempt = best_attempt
                            runner_up_image_base64 = best_image_base64
                            runner_up_reason = best_reason

                            best_attempt = albl
                            best_image_base64 = c_img
                            best_reason = reasoning
                            best_compact_actions = c_cmp
                            consecutive_losses = 0

                            best_challenger_label = lbl
                            best_challenger_result = c_res
                            best_challenger_judge = batch_result
                            print(f"[Judge] ✓ Candidate {lbl} (Attempt {albl}) is the new best ({confidence})")
                            print(f"[Judge]   Reason: {reasoning}")
                            break
                else:
                    print(f"[Judge] ✗ Current best (Attempt {best_attempt}) remains best ({confidence})")
                    print(f"[Judge]   Reason: {reasoning}")
                    # Pick the highest-scoring loser as runner-up
                    best_loser_score = -1
                    for lbl, albl, _, _, _, c_img in executed_candidates:
                        scores = batch_result.get("scores", {}).get(lbl)
                        if scores and isinstance(scores, dict):
                            total = sum(scores.values())
                            if total > best_loser_score:
                                best_loser_score = total
                                runner_up_attempt = albl
                                runner_up_image_base64 = c_img
                                runner_up_reason = reasoning

                judge_history.append({
                    "judged_during_attempt": f"{i + 1}",
                    "judge_type": "batch",
                    "candidates": [lbl for lbl, _, _, _, _, _ in executed_candidates],
                    "winner_label": winner_label,
                    "new_best_attempt": best_attempt,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "scores": batch_result.get("scores", {}),
                    "weakest_criterion": batch_result.get("weakest_criterion"),
                    "specific_improvement": batch_result.get("specific_improvement"),
                })
                best_challenger_judge = batch_result

            # Save judge history after judging
            judge_path = os.path.join(output_dir, "judge_history.json")
            with open(judge_path, 'w') as f:
                json.dump(judge_history, f, indent=2)

            # If no candidate won, increment consecutive losses
            if best_challenger_label is None and best_attempt is not None:
                consecutive_losses += 1
                print(f"[Judge] No candidate beat the best. Consecutive losses: {consecutive_losses}")

            # Use the winning candidate's result (or the informed regen) for learnings/strategy
            winning_result = None
            if best_challenger_result:
                winning_result = best_challenger_result
            elif candidates:
                winning_result = candidates[0][2]

            if winning_result:
                learning = winning_result.get("learnings")
                strategy = winning_result.get("strategy_summary")

                if learning:
                    new_entry = {"iteration": i + 1, "learning": learning}
                    accumulated_learnings = deduplicate_learnings(
                        accumulated_learnings, new_entry, max_count=5,
                    )
                    learnings_path = os.path.join(output_dir, "learnings.json")
                    with open(learnings_path, 'w') as f:
                        json.dump(accumulated_learnings, f, indent=2)

                previous_strategy = strategy if strategy else ""
                if strategy:
                    strategy_path = os.path.join(output_dir, "latest_strategy.json")
                    with open(strategy_path, 'w') as f:
                        json.dump({"iteration": i + 1, "strategy": strategy}, f, indent=2)

            # Store judge feedback for next iteration
            if best_challenger_judge:
                winner_scores = best_challenger_judge.get("scores", {}).get(best_challenger_label) if best_challenger_label else None
                last_judge_feedback = {
                    "winner": "B" if best_challenger_label else "A",
                    "reasoning": best_challenger_judge.get("reasoning", ""),
                    "confidence": best_challenger_judge.get("confidence", "medium"),
                    "compared_best_attempt": runner_up_attempt,
                    "compared_new_attempt": best_attempt,
                    "weakest_criterion": best_challenger_judge.get("weakest_criterion"),
                    "specific_improvement": best_challenger_judge.get("specific_improvement"),
                    "scores_best": winner_scores,
                }
            elif judge_history:
                last_record = judge_history[-1]
                last_judge_feedback = {
                    "winner": "A" if last_record.get("winner_label") == "best" else "B",
                    "reasoning": last_record.get("reasoning", ""),
                    "confidence": last_record.get("confidence", "low"),
                    "compared_best_attempt": best_attempt,
                    "compared_new_attempt": last_record.get("new_best_attempt"),
                    "weakest_criterion": last_record.get("weakest_criterion"),
                    "specific_improvement": last_record.get("specific_improvement"),
                }

            # Store full results for monitoring
            all_results.append({
                "iteration": i + 1,
                "num_candidates": len(candidates),
                "candidate_types": [c[0] for c in candidates],
                "winning_candidate": best_challenger_label,
                "analysis": winning_result.get("analysis", "") if winning_result else "",
                "learnings": winning_result.get("learnings", "") if winning_result else "",
            })

            # Early stopping
            if consecutive_losses >= max_stale_iterations:
                print(f"\n[Early stop] Best hasn't changed in {consecutive_losses} iterations. Stopping.")
                break

        # Take final screenshot
        print("\n[Final] Taking final screenshot...")
        final_svg = controller.take_screenshot()
        if final_svg:
            # Rename to match iteration numbering
            screenshot_dir_path = os.path.dirname(final_svg)
            final_name = f"iteration_{canvas_shows_attempt}.svg" if canvas_shows_attempt else "iteration_final.svg"
            new_final_path = os.path.join(screenshot_dir_path, final_name)
            os.rename(final_svg, new_final_path)
            final_svg = new_final_path
            print(f"[Final] {final_svg}")
            # Also generate cropped PNG for the final screenshot
            final_png_base64 = svg_to_png_base64(final_svg)
            if final_png_base64:
                final_png_path = final_svg.replace('.svg', '_cropped.png')
                with open(final_png_path, 'wb') as f:
                    f.write(base64.standard_b64decode(final_png_base64))
                print(f"[Final Cropped PNG] {final_png_path}")

        # Save all iteration scripts
        scripts_path = os.path.join(output_dir, "iteration_scripts.json")
        with open(scripts_path, 'w') as f:
            json.dump(iteration_scripts, f, indent=2)
        print(f"\n[Saved] All scripts: {scripts_path}")

        # Save full results (analyses, strategies, learnings)
        if all_results:
            results_path = os.path.join(output_dir, "iteration_results.json")
            with open(results_path, 'w') as f:
                json.dump(all_results, f, indent=2)
            print(f"[Saved] Results (analyses/learnings): {results_path}")

        # Save accumulated learnings summary
        if accumulated_learnings:
            learnings_path = os.path.join(output_dir, "learnings.json")
            with open(learnings_path, 'w') as f:
                json.dump(accumulated_learnings, f, indent=2)
            print(f"[Saved] Learnings: {learnings_path}")

        # Generate demo script from the BEST attempt (not necessarily the last)
        if iteration_scripts:
            # Find the best attempt's script
            best_script = None
            source_attempt = None
            if best_attempt:
                # Find the script for the best attempt
                for script_entry in iteration_scripts:
                    if script_entry["iteration"] == best_attempt:
                        best_script = script_entry["actions"]
                        source_attempt = best_attempt
                        break
            # Fallback to last successful iteration if best not found
            if not best_script:
                best_script = iteration_scripts[-1]["actions"]
                source_attempt = iteration_scripts[-1]["iteration"]

            demo_script = generate_demo_script(best_script)
            script_path = os.path.join(output_dir, "generated_demo.py")
            with open(script_path, 'w') as f:
                f.write(demo_script)
            print(f"[Saved] Demo script (from best Attempt {source_attempt}): {script_path}")

            # Also save info about which attempt was best (and runner-up)
            best_info_path = os.path.join(output_dir, "best_iteration.json")
            with open(best_info_path, 'w') as f:
                json.dump({
                    "best_attempt": best_attempt,
                    "reason": best_reason,
                    "runner_up_attempt": runner_up_attempt,
                    "runner_up_reason": runner_up_reason,
                    "total_iterations": iterations,
                }, f, indent=2)
            print(f"[Saved] Best iteration info: {best_info_path}")

    finally:
        controller.stop()

    print("\n" + "="*50)
    print("Done!")
    print(f"Output directory: {output_dir}/")
    print("="*50)


def generate_demo_script(actions: list[dict], canvas_width: int = CANVAS_WIDTH, canvas_height: int = CANVAS_HEIGHT) -> str:
    """Convert actions to a Purple Computer demo script with interpolated cursor movement.

    The AI training uses fast direct paint_at commands, but the demo script
    shows the cursor moving between positions to look natural during playback.
    """
    lines = [
        '"""AI-generated drawing demo."""',
        '',
        'from purple_tui.demo.script import (',
        '    PressKey, SwitchMode, Pause, DrawPath, MoveSequence, Comment,',
        ')',
        '',
        'AI_DRAWING = [',
        '    Comment("=== AI GENERATED DRAWING ==="),',
        '    SwitchMode("doodle"),',
        '    Pause(0.3),',
        '    PressKey("tab"),  # Enter paint mode',
        '',
    ]

    # Track cursor position for movement interpolation
    cursor_x, cursor_y = 0, 0

    def clamp(x: int, y: int) -> tuple[int, int]:
        """Clamp coordinates to canvas bounds (matches UI edge behavior)."""
        return max(0, min(x, canvas_width - 1)), max(0, min(y, canvas_height - 1))

    def move_to(target_x: int, target_y: int) -> list[str]:
        """Generate movement commands to reach target position (L-shaped path)."""
        nonlocal cursor_x, cursor_y
        target_x, target_y = clamp(target_x, target_y)
        result = []

        # Move horizontally first, then vertically
        dx = target_x - cursor_x
        dy = target_y - cursor_y

        if dx != 0 or dy != 0:
            # Use MoveSequence for fast cursor movement without painting
            # This generates arrow key presses without holding space
            directions = []
            if dx > 0:
                directions.extend(['right'] * dx)
            elif dx < 0:
                directions.extend(['left'] * (-dx))
            if dy > 0:
                directions.extend(['down'] * dy)
            elif dy < 0:
                directions.extend(['up'] * (-dy))

            result.append(f'    MoveSequence(directions={directions}, delay_per_step=0.008),')

            cursor_x = target_x
            cursor_y = target_y

        return result

    for action in actions:
        t = action.get('type')

        if t == 'move':
            direction = action["direction"]
            lines.append(f'    PressKey({repr(direction)}),')
            # Update cursor position (clamped to canvas bounds)
            if direction == "right": cursor_x += 1
            elif direction == "left": cursor_x -= 1
            elif direction == "down": cursor_y += 1
            elif direction == "up": cursor_y -= 1
            cursor_x, cursor_y = clamp(cursor_x, cursor_y)

        elif t == 'move_to':
            target_x = action.get('x', 0)
            target_y = action.get('y', 0)
            lines.extend(move_to(target_x, target_y))

        elif t == 'stamp':
            lines.append('    PressKey("space"),')

        elif t == 'paint_at':
            # Move to position, then paint
            target_x = action.get('x', cursor_x)
            target_y = action.get('y', cursor_y)
            color = action.get('color', action.get('key', 'f'))

            lines.extend(move_to(target_x, target_y))
            # In paint mode, pressing a key stamps and advances cursor right by 1
            lines.append(f'    PressKey({repr(color.lower())}),')
            cursor_x = min(target_x + 1, canvas_width - 1)

        elif t == 'paint_line':
            key = action.get('key', 'f')
            direction = action['direction']
            length = action.get('length', 1)
            start_x = action.get('x', cursor_x)
            start_y = action.get('y', cursor_y)

            # Move to start position
            lines.extend(move_to(start_x, start_y))

            # Draw the line
            dirs = [direction] * length
            lines.append(f'    DrawPath(directions={dirs}, color_key={repr(key)}, delay_per_step=0.02),')

            # Update cursor position based on direction (clamped to canvas bounds)
            if direction == 'right': cursor_x += length
            elif direction == 'left': cursor_x -= length
            elif direction == 'down': cursor_y += length
            elif direction == 'up': cursor_y -= length
            cursor_x, cursor_y = clamp(cursor_x, cursor_y)

        elif t == 'wait':
            lines.append(f'    Pause({action.get("seconds", 0.3)}),')

    lines.extend([
        '',
        '    Pause(1.0),',
        '    Comment("Drawing complete!"),',
        ']',
    ])

    return '\n'.join(lines)


# =============================================================================
# MAIN
# =============================================================================

def generate_output_dir(base_dir: str = "doodle_ai_output") -> str:
    """Generate a unique output directory with timestamp."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_dir}/{timestamp}"


def main():
    parser = argparse.ArgumentParser(
        description="AI-assisted drawing using real Purple Computer app",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tools/doodle_ai.py --goal "a tree on a green hill"
    python tools/doodle_ai.py --goal "sunset with orange sky" --iterations 8
    python tools/doodle_ai.py --goal "simple house" --iterations 3

    # Use a reference image
    python tools/doodle_ai.py --goal "a palm tree" --reference photo.png

    # Refine a previous run
    python tools/doodle_ai.py --refine doodle_ai_output/20260203_143022 --instruction "add a bird on a branch"
    python tools/doodle_ai.py --refine doodle_ai_output/20260203_143022 --instruction "make trunk thicker" --iterations 3

    # Refine with a reference image
    python tools/doodle_ai.py --refine doodle_ai_output/20260203_143022 --instruction "make it look more like this" --reference palm_photo.jpg

Requirements:
    - ANTHROPIC_API_KEY environment variable
    - cairosvg for SVG to PNG conversion: pip install cairosvg
    - Or rsvg-convert / inkscape installed

Output (auto-generated timestamped folder):
    - screenshots/: SVG screenshots from each iteration
    - plan.json: The AI's drawing plan
    - actions.json: All actions taken
    - learnings.json: AI observations
    - generated_demo.py: Demo script for Purple Computer
        """
    )
    parser.add_argument("--goal", default=None, help="What to draw (required unless using --refine)")
    parser.add_argument("--refine", default=None, metavar="PREV_OUTPUT_DIR",
                        help="Refine a previous run's plan. Pass the output directory containing plan.json")
    parser.add_argument("--instruction", default=None,
                        help="How to refine the plan (required with --refine)")
    parser.add_argument("--reference", default=None, metavar="IMAGE_PATH",
                        help="Reference image to guide composition and style (png, jpg, gif, webp)")
    parser.add_argument("--iterations", type=int, default=5, help="Feedback iterations")
    parser.add_argument("--output", default=None, help="Output directory (default: auto-generated)")
    parser.add_argument("--execution-model", default="claude-sonnet-4-20250514",
                        help="Model for drawing execution (default: claude-sonnet-4-20250514)")
    parser.add_argument("--judge-model", default="claude-sonnet-4-20250514",
                        help="Model for judging comparisons (default: claude-sonnet-4-20250514)")
    parser.add_argument("--max-candidates", type=int, default=3,
                        help="Max candidates per iteration: mutation, informed regen, fresh regen (default: 3)")

    args = parser.parse_args()

    # Validate args
    if args.refine:
        if not args.instruction:
            parser.error("--instruction is required when using --refine")
        plan_path = os.path.join(args.refine, "plan.json")
        if not os.path.exists(plan_path):
            parser.error(f"No plan.json found in {args.refine}")
    elif not args.goal:
        parser.error("--goal is required (unless using --refine)")

    if args.reference and not os.path.exists(args.reference):
        parser.error(f"Reference image not found: {args.reference}")

    # Auto-generate output dir
    output_dir = args.output if args.output else generate_output_dir()

    # Handle refinement: load previous plan, refine it, then run
    existing_plan = None
    goal = args.goal
    if args.refine:
        plan_path = os.path.join(args.refine, "plan.json")
        with open(plan_path) as f:
            original_plan = json.load(f)
        goal = original_plan.get('description', 'drawing')

        # Load env/API key for refinement call
        load_env_file()
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            print("Error: Set ANTHROPIC_API_KEY in tools/.env or environment")
            sys.exit(1)

        existing_plan = call_plan_refinement_api(
            original_plan=original_plan,
            instruction=args.instruction,
            iterations=args.iterations,
            api_key=api_key,
            reference_image=args.reference,
        )

    print("="*60)
    print("Purple Computer AI Drawing Tool")
    print("="*60)
    if args.reference:
        print(f"Reference: {args.reference}")
    if args.refine:
        print(f"Refining: {args.refine}")
        print(f"Instruction: {args.instruction}")
    print(f"Goal: {goal}")
    print(f"Iterations: {args.iterations}")
    print(f"Max candidates per iteration: {args.max_candidates}")
    print(f"Execution model: {args.execution_model}")
    print(f"Judge model: {args.judge_model}")
    print(f"Output: {output_dir}/")
    print("="*60)
    print()

    run_visual_feedback_loop(
        goal=goal,
        iterations=args.iterations,
        output_dir=output_dir,
        execution_model=args.execution_model,
        judge_model=args.judge_model,
        existing_plan=existing_plan,
        reference_image=args.reference,
        max_candidates=args.max_candidates,
    )


if __name__ == "__main__":
    main()
