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
"""

import argparse
import base64
import hashlib
import io
import json
import os
import pty
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
                color = line[1]
                coords = line[2:].split(',')
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
                color = line[1]
                coords = line[2:].split(',')
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

    # Import constants for fallback
    try:
        from purple_tui.constants import REQUIRED_TERMINAL_COLS, REQUIRED_TERMINAL_ROWS
    except ImportError:
        REQUIRED_TERMINAL_COLS = 114
        REQUIRED_TERMINAL_ROWS = 39

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
            # Fallback: approximate Doodle mode canvas area
            # Rows 7-31 (25 rows), Cols 4-104 (100 cols)
            left = int(4 * cell_width)
            top = int(7 * cell_height)
            right = int(105 * cell_width)
            bottom = int(32 * cell_height)

        drawable_width = right - left
        drawable_height = bottom - top
        print(f"[Crop] Drawable area: {drawable_width}x{drawable_height} pixels")
        print(f"[Crop] Crop box: left={left}, top={top}, right={right}, bottom={bottom}")

        # Crop the image
        cropped = img.crop((left, top, right, bottom))
        print(f"[Crop] Cropped to: {cropped.size[0]}x{cropped.size[1]}")

        # Resize if larger than needed to reduce API token costs
        # Canvas is 101x25 cells, so ~500x200 pixels is plenty of resolution
        MAX_WIDTH = 500
        MAX_HEIGHT = 200
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

    def send_commands(self, commands: list[dict], wait_for_consumption: bool = False) -> bool:
        """Send multiple commands to the app in a single batch.

        Args:
            commands: List of command dicts
            wait_for_consumption: If True, wait until command file is consumed

        Returns:
            True if command was consumed (or wait_for_consumption=False), False if timeout
        """
        command_path = os.path.join(self.screenshot_dir, 'command')
        # Write all commands as newline-separated JSON
        content = '\n'.join(json.dumps(cmd) for cmd in commands)
        with open(command_path, 'w') as f:
            f.write(content + '\n')

        if wait_for_consumption:
            # Wait for command to be consumed (file deleted)
            for _ in range(20):  # 2 second timeout
                time.sleep(0.1)
                if not os.path.exists(command_path):
                    return True
            print(f"[Warning] Command not consumed after 2s")
            return False
        else:
            # Brief wait for app to start processing
            time.sleep(0.05)
            return True

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

    def clear_canvas(self) -> bool:
        """Clear the entire canvas. Returns True if command was consumed."""
        print("[Clear] Sending clear command...")

        # Send clear command and wait for it to be consumed
        consumed = self.send_commands(
            [{"action": "clear", "value": ""}],
            wait_for_consumption=True
        )

        if consumed:
            print("[Clear] Command consumed, canvas cleared")
            time.sleep(0.1)  # Brief wait for render
            return True
        else:
            print("[Clear] ERROR: Command not consumed by app!")
            return False

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
        # Batch paint_at commands to avoid race conditions
        # (individual sends can be overwritten before app reads them)
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
                        time.sleep(0.1)  # Wait for batch to process
                    # Execute non-paint_at action
                    self.execute_action(action)
            except Exception as e:
                print(f"[Warning] Action failed: {action} - {e}")

        # Flush remaining paint_at batch
        if paint_at_batch:
            print(f"[Execute] Sending batch of {len(paint_at_batch)} paint_at commands")
            self.send_commands(paint_at_batch)
            time.sleep(0.3)  # Wait for large batch to process

            # Verify commands were received
            response_path = os.path.join(self.screenshot_dir, "command_response")
            try:
                if os.path.exists(response_path):
                    with open(response_path, "r") as f:
                        processed = int(f.read().strip())
                    os.unlink(response_path)
                    if processed != len(paint_at_batch):
                        raise RuntimeError(
                            f"Command loss detected! Sent {len(paint_at_batch)}, app processed {processed}. "
                            f"Lost {len(paint_at_batch) - processed} commands."
                        )
                    else:
                        print(f"[Execute] Verified: all {processed} commands processed")
            except RuntimeError:
                raise  # Re-raise our own error
            except Exception as e:
                print(f"[Warning] Could not verify command count: {e}")


# =============================================================================
# AI VISION FEEDBACK LOOP
# =============================================================================

PLANNING_PROMPT = """You are an AI artist planning a pixel art drawing in Purple Computer's Doodle mode.

## CANVAS SIZE
The canvas is **101 cells wide × 25 cells tall**.
- X coordinates: 0 (left) to 100 (right)
- Y coordinates: 0 (top) to 24 (bottom)
- Origin (0,0) is TOP-LEFT corner

## HOW THIS WORKS (REGENERATIVE MODEL)

Each iteration draws a COMPLETE image from scratch. The canvas is cleared between iterations.
You are planning what the FINAL DRAWING should look like, not how to build it incrementally.

The execution AI will see its previous attempt and try to improve, but each attempt is a complete redraw.

## COLOR SYSTEM

Each row provides a color family:
- **Number row (` 1 2 3 4 5 6 7 8 9 0 - =)**: GRAYSCALE (white to black)
- **QWERTY row (q w e r t y u i o p [ ] \\)**: RED family (pink to burgundy)
- **ASDF row (a s d f g h j k l ; ')**: YELLOW family (gold to brown)
- **ZXCV row (z x c v b n m , . /)**: BLUE family (periwinkle to navy)

## COLOR MIXING

Colors MIX when painted on the SAME cell:
- Yellow + Blue = GREEN
- Red + Blue = PURPLE
- Red + Yellow = ORANGE

**To get green:** Paint yellow on an area, then paint blue on the SAME area.

## YOUR TASK

Create a plan describing what the FINAL drawing should look like:
1. **Composition**: Where each element goes (x/y coordinates)
2. **Colors**: What final color each area should be
3. **Mixing recipe**: For mixed colors, which base colors to use
4. **Style**: Simple, clean shapes with SOLID color regions (no stripes!)

## KEY RULES FOR SUCCESS

- Keep the main subject RECOGNIZABLE (a 4-year-old should identify it)
- Use LARGE, BOLD features that fill the canvas
- Add SHADING for depth (lighter colors for highlights, darker for shadows)
- Use color mixing to create greens, oranges, and purples

## RESPONSE FORMAT

```json
{
  "plan": {
    "description": "Brief description of the final drawing",
    "composition": {
      "element_name": {
        "x_range": [start, end],
        "y_range": [start, end],
        "final_color": "green (or red, blue, yellow, brown, etc.)",
        "mixing_recipe": "yellow base + blue overlay" or null for pure colors,
        "description": "what this element is"
      }
    },
    "style_notes": "Key points about the visual style - emphasize CURVED, ORGANIC shapes (e.g., 'round fluffy foliage, not rectangular')",
    "recognition_test": "A 4-year-old should see: [what they should recognize]"
  }
}
```

Be specific about coordinates. The execution AI will use this as a reference for composition."""


EXECUTION_PROMPT = """You are an AI artist creating pixel art in Purple Computer's Doodle mode.

## GOALS
Your drawings should be:
1. **Colorful** - use lots of pretty colors across the whole image
2. **Shaded** - use lighter and darker shades for depth and dimension
3. **Detailed** - add texture, highlights, gradients, and fine details
4. **Organic** - use varied shapes, not just rectangles
5. **Recognizable** - a 4-year-old should be able to identify what it is

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
The canvas is **101 cells wide × 25 cells tall**.
- X coordinates: 0 (left) to 100 (right)
- Y coordinates: 0 (top) to 24 (bottom)
- Origin (0,0) is TOP-LEFT corner

## WHAT YOU SEE IN SCREENSHOTS
- Colored cells are painted areas
- Letters visible on cells (like "F", "C", "R") are just labels showing which key painted that cell
- The cursor is a 3×3 blinking ring of box-drawing characters (┌━┐ etc.)
- Purple background = unpainted canvas

## COLOR SYSTEM (KEYBOARD ROWS)

Each keyboard row produces a COLOR FAMILY. Within each row, keys go from LIGHTER (left) to DARKER (right).
**Use this for SHADING:** paint lighter keys (left side of row) for highlights, darker keys (right side) for shadows.

**GRAYSCALE (Number row: ` 1 2 3 4 5 6 7 8 9 0 - =):**
- ` (backtick) = pure white (highlight)
- 1-3 = light grays
- 4-6 = medium grays
- 7-9 = dark grays
- 0, -, = = near/pure black (shadow)

**RED FAMILY (QWERTY row: q w e r t y u i o p [ ] \\):**
- q, w = lightest pink (highlight)
- e, r, t, y = medium red (primary)
- u, i, o, p = dark red
- [, ], \\ = darkest burgundy (shadow)

**YELLOW FAMILY (ASDF row: a s d f g h j k l ; '):**
- a, s = lightest gold (highlight)
- d, f, g = medium yellow (primary)
- h, j, k, l = dark gold/brown
- ;, ' = darkest brown (shadow)

**BLUE FAMILY (ZXCV row: z x c v b n m , . /):**
- z, x = lightest periwinkle (highlight)
- c, v, b = medium blue (primary)
- n, m = dark blue
- ,, ., / = darkest navy (shadow)

## SHADING TECHNIQUE

To create 3D depth and realism, use DIFFERENT keys from the same row:
- **Highlights**: Use leftmost keys (q, a, z, `)
- **Midtones**: Use middle keys (t, f, b, 5)
- **Shadows**: Use rightmost keys (\\, ', /, =)

Example for a tree trunk: paint 'd' for lit side, 'j' for middle, "'" (apostrophe) for shadow side.

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

**Remember:** Vary the x-range per row to create curves. Don't use the same x-range for every row (that makes rectangles).

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

## LAYERED PAINTING (within each attempt)

To get mixed colors, you MUST paint in layers within your script:

**STEP 1: Paint ALL yellow areas first**
Paint yellow ("f", "g", "d") on every cell that will become green, orange, OR brown.
This includes: grass, leaves, tree trunks, ground.

**STEP 2: Paint blue OVER yellow to make GREEN**
Go back and paint blue ("c", "v", "b") over the yellow cells that should be green.
The blue mixes with underlying yellow = GREEN.

**STEP 3: Paint red OVER yellow to make ORANGE**
Paint red ("r", "e") over yellow cells that should be orange.
The red mixes with underlying yellow = ORANGE.

**STEP 4: Add details and pure colors**
Now add any pure red, pure blue, or grayscale elements.

**Example: Green grass with brown path**
```json
// Step 1: Yellow everywhere (grass + path area)
{"type": "paint_line", "x": 0, "y": 22, "key": "f", "direction": "right", "length": 101},
{"type": "paint_line", "x": 0, "y": 23, "key": "f", "direction": "right", "length": 101},
// Step 2: Blue over grass ONLY (not path) = GREEN
{"type": "paint_line", "x": 0, "y": 22, "key": "c", "direction": "right", "length": 45},
{"type": "paint_line", "x": 55, "y": 22, "key": "c", "direction": "right", "length": 46},
// Path (x=45-55) keeps yellow, becomes brown with darker overlays
{"type": "paint_line", "x": 45, "y": 22, "key": "l", "direction": "right", "length": 10}
```

For SHADING mixed colors, vary the shade of the overlay:
- Bright green highlight: light yellow ("a") + light blue ("z")
- Medium green: medium yellow ("f") + medium blue ("b")
- Dark green shadow: dark yellow ("k") + dark blue (".")

## RESPONSE FORMAT

Respond with a JSON object followed by a compact actions block:

```json
{
  "analysis": "What I see from the previous attempt and what to improve",
  "strategy_summary": {
    "composition": {
      "element_name": {"x_range": [start, end], "y_range": [start, end], "description": "what this element is"}
    },
    "layering_order": ["Step 1: Yellow base", "Step 2: Blue overlay", "Step 3: Details"],
    "keep_next_time": ["trunk position at x=48-52"],
    "change_next_time": ["make trunk wider"]
  },
  "learnings": "Key insight from this attempt"
}
```

```actions
Lf0,5,100,5
Lf0,6,100,6
Lc0,5,50,5
Pk25,10
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
3. No gaps - every row from y_start to y_end is covered?

**IMPORTANT: All fields are REQUIRED. Use the compact action format, NOT JSON arrays.**"""


def call_planning_api(
    goal: str,
    iterations: int,
    api_key: str,
) -> dict:
    """Call Claude API to create a drawing plan.

    Returns:
        Plan dict with phases and composition details
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    user_message = f"""## Goal: {goal}

## Available Iterations: {iterations}

Create a detailed plan for drawing this image across {iterations} iterations.
Divide the work into phases that fit within the iteration count.

Respond with a JSON object containing a "plan" field."""

    print("[Planning] Creating drawing plan...")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=PLANNING_PROMPT,
        messages=[{
            "role": "user",
            "content": user_message,
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
Feel free to add detail - more actions create richer, more interesting drawings."""

    elif progress <= 0.5:
        return """## ITERATION PHASE: Development
Build out the drawing with more colors and shading. Add texture and visual interest.
Use the full range of colors - lights for highlights, darks for shadows."""

    elif progress <= 0.75:
        return """## ITERATION PHASE: Refinement
Add fine details, highlights, and finishing touches. Make it rich and visually interesting.
Don't hold back on detail - the more texture and shading, the better."""

    else:
        return """## ITERATION PHASE: Polish
Perfect the details. Add any missing highlights, shadows, or textures.
Make every part of the drawing interesting to look at."""


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
            judge_section = f"\n## JUDGE FEEDBACK (Your last attempt WON)\n"
            judge_section += f"Your Attempt {compared_new} beat the previous best (Attempt {compared_best}).\n"
            judge_section += f"Judge's reasoning: {reasoning}\n"
            judge_section += "Keep doing what worked! Build on this success.\n"
        elif winner == "A":
            # Previous attempt was worse than the best
            judge_section = f"\n## JUDGE FEEDBACK (Your last attempt LOST)\n"
            judge_section += f"Your Attempt {compared_new} was worse than Attempt {compared_best}.\n"
            judge_section += f"Judge's reasoning: {reasoning}\n"
            judge_section += "Change your approach. The current best is still Attempt {compared_best}.\n"

    # Build plan summary
    plan_section = ""
    if plan:
        plan_section = f"\n## DRAWING PLAN\n{plan.get('description', goal)}\n"
        if plan.get('composition'):
            comp = plan['composition']
            if comp.get('main_element'):
                me = comp['main_element']
                plan_section += f"Main element: {me.get('description', '')} at x={me.get('x_range')}, y={me.get('y_range')}\n"

    # Option D: Get progressive complexity guidance
    complexity_section = get_complexity_guidance(iteration, max_iterations)

    # First iteration vs subsequent
    if iteration == 1:
        instruction = """This is your FIRST attempt. Generate a complete drawing script based on the plan.
The canvas is blank. Your script should include:
1. Yellow base layer for areas that will become green/brown
2. Blue overlay on yellow to create greens
3. Red overlay for oranges/purples
4. Any additional details"""
    else:
        instruction = """The screenshot shows your PREVIOUS attempt's result.
Analyze what worked and what needs improvement, then generate a BETTER complete script.
The canvas will be CLEARED and your new script executed from scratch."""

    user_message = f"""## Goal: {goal}

## Attempt: {iteration} of {max_iterations}

{complexity_section}
{plan_section}{learnings_section}{strategy_section}{judge_section}
{instruction}

Respond with JSON metadata followed by a compact ```actions``` block."""

    # Build message content with single image
    message_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_base64,
            },
        },
        {"type": "text", "text": user_message},
    ]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,  # More tokens for complete scripts
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
        print(f"[Warning] Only extracted actions array, no metadata")
    elif not result["actions"]:
        print(f"[Error] Could not parse actions from response")
        print(f"[Debug] Raw response:\n{text[:500]}...")

    return result


def call_judge_api(
    image_a_base64: str,
    image_b_base64: str,
    goal: str,
    iteration_a: int,
    iteration_b: int,
    api_key: str,
) -> dict:
    """Separate API call to judge which image is better.

    Uses a fresh context and focused prompt to get an objective comparison.
    Uses Haiku for cost efficiency since this is just evaluation, not generation.

    Args:
        image_a_base64: Current best image (PNG base64)
        image_b_base64: Latest attempt image (PNG base64)
        goal: What we're trying to draw
        iteration_a: Which iteration produced image A
        iteration_b: Which iteration produced image B
        api_key: Anthropic API key

    Returns:
        Dict with keys: winner ("A" or "B"), reasoning, confidence
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    judge_prompt = f"""You are judging pixel art drawings. Your ONLY job is to decide which image better represents the goal.

GOAL: "{goal}"

You will see two images:
- Image A (iteration {iteration_a})
- Image B (iteration {iteration_b})

Evaluate based on:
1. Does it look like the goal? (most important)
2. Recognizable shape/structure
3. Appropriate colors
4. Overall quality and completeness

Be OBJECTIVE. Newer is not always better. Simpler is not always worse.
A messy attempt with stripes everywhere is WORSE than a clean simple drawing.

Respond with JSON only:
```json
{{
  "winner": "A" or "B",
  "reasoning": "Brief explanation of why the winner is better",
  "confidence": "high" or "medium" or "low"
}}
```"""

    message_content = [
        {"type": "text", "text": f"**Image A (iteration {iteration_a}):**"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_a_base64,
            },
        },
        {"type": "text", "text": f"**Image B (iteration {iteration_b}):**"},
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
        model="claude-haiku-4-5-20251001",  # Haiku 4.5: fast, cheap, good vision
        max_tokens=300,  # Short response needed
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
    }

    data = parse_json_robust(text)

    if data and isinstance(data, dict):
        winner = data.get("winner", "")
        result["winner"] = winner.upper() if isinstance(winner, str) else None
        result["reasoning"] = data.get("reasoning", "")
        result["confidence"] = data.get("confidence", "low")
    else:
        print(f"[Judge] Could not parse JSON, trying text extraction")
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
) -> None:
    """Run the AI drawing loop with real visual feedback."""

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

    # Start the app
    controller = PurpleController()

    try:
        controller.start(screenshot_dir)

        # Create drawing plan FIRST (before any drawing)
        print("\n" + "="*50)
        print("PLANNING PHASE")
        print("="*50)
        plan = call_planning_api(goal, iterations, api_key)

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
            if canvas_shows_attempt:
                print(f"Canvas currently shows: Attempt {canvas_shows_attempt}'s result")
            print('='*50)

            # Take screenshot (shows previous attempt's result, or blank for first)
            svg_path = controller.take_screenshot()
            if not svg_path:
                print("[Error] Failed to capture screenshot")
                continue

            # Extract screenshot number from filename for clarity
            screenshot_num_match = re.search(r'screenshot_(\d+)', svg_path)
            screenshot_num = screenshot_num_match.group(1) if screenshot_num_match else "?"

            if i == 0:
                print(f"[Screenshot] {svg_path}")
                print(f"[Screenshot] screenshot_{screenshot_num} = blank canvas (before any drawing)")
            else:
                print(f"[Screenshot] {svg_path}")
                print(f"[Screenshot] screenshot_{screenshot_num} = Attempt {i}'s result")


            # Convert to PNG for vision API (with cropping to canvas area)
            png_base64 = svg_to_png_base64(svg_path)
            if not png_base64:
                print("[Error] Failed to convert SVG to PNG")
                continue

            # Save the cropped PNG so user can see what Claude sees
            png_path = svg_path.replace('.svg', '_cropped.png')
            with open(png_path, 'wb') as f:
                f.write(base64.standard_b64decode(png_base64))
            print(f"[Cropped PNG] {png_path}")

            # Get analysis and NEW complete script from AI
            # Pass accumulated learnings (not full scripts) for efficient context
            # Retry up to 3 times if we get no actions (JSON parse failure, etc.)
            actions = []
            result = {}
            max_retries = 3
            for retry in range(max_retries):
                if retry > 0:
                    print(f"[Retry] Attempt {retry + 1}/{max_retries} for iteration {i + 1}...")
                    time.sleep(1)  # Brief pause before retry

                result = call_vision_api(
                    image_base64=png_base64,
                    goal=goal,
                    iteration=i + 1,
                    max_iterations=iterations,
                    api_key=api_key,
                    plan=plan,
                    accumulated_learnings=accumulated_learnings,
                    previous_strategy=previous_strategy,
                    judge_feedback=last_judge_feedback,
                )

                actions = result.get("actions", [])
                if actions:
                    break  # Got actions, exit retry loop
                else:
                    print(f"[Warning] No actions returned (attempt {retry + 1}/{max_retries})")

            # Store full result
            all_results.append({
                "iteration": i + 1,
                "analysis": result.get("analysis", ""),
                "strategy_summary": result.get("strategy_summary", ""),
                "learnings": result.get("learnings", ""),
            })

            if not actions:
                print(f"[Error] Failed to get actions after {max_retries} retries")
                # Don't clear - keep the canvas as-is to preserve progress
                # canvas_shows_attempt stays unchanged, so judge will skip automatically
                print(f"[Skip] Canvas still shows Attempt {canvas_shows_attempt}'s result (no new execution)")
                continue

            # Debug: show action summary to verify they're different each iteration
            actions_str = json.dumps(actions, sort_keys=True)
            actions_hash = hashlib.md5(actions_str.encode()).hexdigest()[:8]
            first_action = actions[0] if actions else None
            last_action = actions[-1] if actions else None
            print(f"[Script] Generated {len(actions)} actions (hash: {actions_hash})")
            print(f"[Script] First action: {first_action}")
            print(f"[Script] Last action: {last_action}")

            # Store this iteration's script
            iteration_scripts.append({"iteration": i + 1, "actions": actions})

            # Save debug info: raw response and compact actions
            debug_dir = os.path.join(output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)

            # Save raw AI response
            raw_response_path = os.path.join(debug_dir, f"iteration_{i+1:02d}_raw_response.txt")
            with open(raw_response_path, 'w') as f:
                f.write(result.get("raw_response", ""))

            # Save compact actions (the L/P commands before expansion)
            compact_path = os.path.join(debug_dir, f"iteration_{i+1:02d}_compact_actions.txt")
            with open(compact_path, 'w') as f:
                f.write(result.get("compact_actions_text", ""))
            print(f"[Debug] Saved raw response and compact actions to {debug_dir}")

            # Accumulate learnings for next iteration (compact, not full scripts)
            learning = result.get("learnings")
            strategy = result.get("strategy_summary")

            print(f"[Debug] Learnings returned: {bool(learning)} - {repr(learning)[:100] if learning else 'None'}")
            print(f"[Debug] Strategy returned: {bool(strategy)} - type={type(strategy).__name__}")

            if learning:
                accumulated_learnings.append({
                    "iteration": i + 1,
                    "learning": learning,
                })
                # Save learnings incrementally so user can monitor progress
                learnings_path = os.path.join(output_dir, "learnings.json")
                with open(learnings_path, 'w') as f:
                    json.dump(accumulated_learnings, f, indent=2)
                print(f"[Saved] Learnings ({len(accumulated_learnings)} total): {learnings_path}")

            previous_strategy = strategy if strategy else ""

            # Also save strategy incrementally
            if strategy:
                strategy_path = os.path.join(output_dir, "latest_strategy.json")
                with open(strategy_path, 'w') as f:
                    json.dump({
                        "iteration": i + 1,
                        "strategy": strategy
                    }, f, indent=2)
                print(f"[Saved] Strategy: {strategy_path}")

            # Update best tracking using SEPARATE judge call
            # IMPORTANT: We use canvas_shows_attempt to track what's ACTUALLY on the canvas
            # This prevents comparing the same image when iterations fail

            # Only judge if:
            # 1. Canvas has content (canvas_shows_attempt is set)
            # 2. Canvas shows something different from best (or no best yet)
            # 3. Canvas has actually changed since last comparison

            if canvas_shows_attempt is None:
                # Canvas is blank (first iteration), nothing to judge yet
                print(f"[Judge] Canvas is blank, nothing to compare yet")
            elif best_attempt is None:
                # First real result, set as initial best
                best_attempt = canvas_shows_attempt
                best_image_base64 = png_base64
                best_reason = "Initial drawing (first result)"
                print(f"[Best] Setting Attempt {best_attempt} as initial best (first drawing)")
            elif canvas_shows_attempt == best_attempt:
                # Canvas still shows the best attempt (no new successful execution)
                print(f"[Judge] Skipping - canvas still shows Attempt {canvas_shows_attempt} (same as best)")
            elif canvas_shows_attempt != best_attempt and best_image_base64:
                # Canvas shows a NEW result different from best - time to judge!
                print(f"[Judge] Comparing Attempt {canvas_shows_attempt} (on canvas) vs Attempt {best_attempt} (current best)...")
                judge_result = call_judge_api(
                    image_a_base64=best_image_base64,
                    image_b_base64=png_base64,
                    goal=goal,
                    iteration_a=best_attempt,
                    iteration_b=canvas_shows_attempt,
                    api_key=api_key,
                )
                winner = judge_result.get("winner")
                reasoning = judge_result.get("reasoning", "")
                confidence = judge_result.get("confidence", "low")

                # Record judgment for monitoring
                judgment_record = {
                    "judged_during_attempt": i + 1,
                    "compared_a_attempt": best_attempt,
                    "compared_b_attempt": canvas_shows_attempt,
                    "winner": winner,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "new_best_attempt": None,
                }

                if winner == "B":
                    # Canvas result is better - old best becomes runner-up
                    runner_up_attempt = best_attempt
                    runner_up_image_base64 = best_image_base64
                    runner_up_reason = best_reason

                    best_attempt = canvas_shows_attempt
                    best_image_base64 = png_base64
                    best_reason = reasoning
                    judgment_record["new_best_attempt"] = canvas_shows_attempt
                    print(f"[Judge] ✓ Attempt {best_attempt} is the new best ({confidence} confidence)")
                    print(f"[Judge]   Reason: {reasoning}")
                    if runner_up_attempt:
                        print(f"[Judge]   Runner-up: Attempt {runner_up_attempt}")
                elif winner == "A":
                    # Current best stays - canvas result becomes runner-up if better than current runner-up
                    # (For simplicity, we just track the most recent loser as potential runner-up)
                    if runner_up_attempt is None or canvas_shows_attempt != runner_up_attempt:
                        runner_up_attempt = canvas_shows_attempt
                        runner_up_image_base64 = png_base64
                        runner_up_reason = reasoning

                    judgment_record["new_best_attempt"] = best_attempt
                    print(f"[Judge] ✗ Keeping Attempt {best_attempt} as best ({confidence} confidence)")
                    print(f"[Judge]   Reason: {reasoning}")
                    print(f"[Judge]   Runner-up: Attempt {runner_up_attempt}")
                else:
                    judgment_record["new_best_attempt"] = best_attempt
                    print(f"[Judge] ⚠ Could not determine winner, keeping Attempt {best_attempt}")

                # Save judge history incrementally so user can monitor
                judge_history.append(judgment_record)
                judge_path = os.path.join(output_dir, "judge_history.json")
                with open(judge_path, 'w') as f:
                    json.dump(judge_history, f, indent=2)
                print(f"[Saved] Judge history: {judge_path}")

                # Option A: Store judge feedback to pass to next execution call
                last_judge_feedback = {
                    "winner": winner,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "compared_best_attempt": best_attempt if winner == "A" else judgment_record["compared_a_attempt"],
                    "compared_new_attempt": canvas_shows_attempt,
                }

            # Clear canvas before executing (except first iteration which starts blank)
            if i > 0:
                print("[Clear] Clearing canvas for fresh attempt...")
                clear_success = controller.clear_canvas()
                print(f"[Clear] Clear result: {clear_success}")
                if not clear_success:
                    print("[ERROR] Failed to clear canvas after retries. Aborting.")
                    print("This may indicate the 'clear' command is not being processed.")
                    break
                # Extra wait after clear to ensure it takes effect
                time.sleep(0.3)

            # Execute the complete script
            print(f"[Execute] Running {len(actions)} actions...")
            controller.execute_actions(actions)
            print(f"[Execute] Done executing actions")

            # Update what's on the canvas - this attempt's result will be visible
            canvas_shows_attempt = i + 1  # Attempt number (1-indexed)
            print(f"[Canvas] Now showing Attempt {canvas_shows_attempt}'s result")

            # Wait for canvas to fully render before next screenshot
            time.sleep(0.5)

        # Take final screenshot
        print("\n[Final] Taking final screenshot...")
        final_svg = controller.take_screenshot()
        if final_svg:
            print(f"[Final] {final_svg}")

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


def generate_demo_script(actions: list[dict]) -> str:
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

    def move_to(target_x: int, target_y: int) -> list[str]:
        """Generate movement commands to reach target position (L-shaped path)."""
        nonlocal cursor_x, cursor_y
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
            lines.append(f'    PressKey("{action["direction"]}"),')
            # Update cursor position
            if action["direction"] == "right": cursor_x += 1
            elif action["direction"] == "left": cursor_x -= 1
            elif action["direction"] == "down": cursor_y += 1
            elif action["direction"] == "up": cursor_y -= 1

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
            # Paint: lowercase key stamps and advances, so we use it directly
            lines.append(f'    PressKey("{color.lower()}"),')
            cursor_x += 1  # Painting advances cursor right by default

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
            lines.append(f'    DrawPath(directions={dirs}, color_key="{key}", delay_per_step=0.02),')

            # Update cursor position based on direction
            if direction == 'right': cursor_x += length
            elif direction == 'left': cursor_x -= length
            elif direction == 'down': cursor_y += length
            elif direction == 'up': cursor_y -= length

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
    parser.add_argument("--goal", required=True, help="What to draw")
    parser.add_argument("--iterations", type=int, default=5, help="Feedback iterations")
    parser.add_argument("--output", default=None, help="Output directory (default: auto-generated)")

    args = parser.parse_args()

    # Auto-generate output dir if not specified
    output_dir = args.output if args.output else generate_output_dir()

    print("="*60)
    print("Purple Computer AI Drawing Tool")
    print("="*60)
    print(f"Goal: {args.goal}")
    print(f"Iterations: {args.iterations}")
    print(f"Output: {output_dir}/")
    print("="*60)
    print()

    run_visual_feedback_loop(
        goal=args.goal,
        iterations=args.iterations,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()
