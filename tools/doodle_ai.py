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
import io
import json
import os
import pty
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
        """Execute a list of actions."""
        for action in actions:
            try:
                self.execute_action(action)
            except Exception as e:
                print(f"[Warning] Action failed: {action} - {e}")


# =============================================================================
# AI VISION FEEDBACK LOOP
# =============================================================================

PLANNING_PROMPT = """You are an AI artist planning a pixel art drawing in Purple Computer's Doodle mode.

## CANVAS SIZE
The canvas is **101 cells wide × 25 cells tall**.
- X coordinates: 0 (left) to 100 (right)
- Y coordinates: 0 (top) to 24 (bottom)
- Origin (0,0) is TOP-LEFT corner

## COLOR SYSTEM (with SHADING)

Each row provides a color family with SHADING from light (left) to dark (right):
- **QWERTY row (q-p, then [ ] \\)**: RED family (pink → burgundy)
- **ASDF row (a-l, then ; ')**: YELLOW family (gold → brown)
- **ZXCV row (z-m, then , . /)**: BLUE family (periwinkle → navy)
- **Number row (` 1-0 - =)**: GRAYSCALE (pure white → pure black)

**SHADING:** Use left keys for highlights, middle for midtones, right for shadows.

## COLOR MIXING (LAYERED PAINTING)

When you paint OVER an already-painted cell, colors MIX:
- Yellow + Blue = GREEN
- Red + Blue = PURPLE
- Red + Yellow = ORANGE

**CRITICAL:** To mix colors, paint the ENTIRE area with one color FIRST, then paint the SAME area with the second color. Do NOT alternate cell by cell.

## YOUR TASK
Create a detailed PLAN for drawing the requested image. You will have multiple iterations to execute this plan.

The plan should include:
1. **Composition**: Where elements go on the 101x25 canvas
2. **Phases**: Break the work into phases, each assigned to specific iterations
3. **Color strategy**: Which base colors to paint first, which overlays to add

## RESPONSE FORMAT
Respond with a JSON object:

```json
{
  "plan": {
    "description": "Brief description of what we're drawing",
    "composition": {
      "main_element": {"x_range": [40, 70], "y_range": [5, 25], "description": "..."},
      "other_elements": [...]
    },
    "phases": [
      {
        "name": "Phase 1: Yellow base",
        "iterations": [1, 2, 3],
        "goal": "Paint yellow in all areas that will become green or brown",
        "color_keys": ["f", "g", "d"],
        "target_areas": "foliage area (y=5-18), trunk area (x=54-58, y=18-28)"
      },
      {
        "name": "Phase 2: Blue overlay",
        "iterations": [4, 5, 6],
        "goal": "Paint blue over yellow foliage to create green",
        "color_keys": ["c", "v"],
        "target_areas": "foliage area only (y=5-18)"
      },
      {
        "name": "Phase 3: Details",
        "iterations": [7, 8, 9, 10],
        "goal": "Add red apples, brown trunk details",
        "color_keys": ["r", "e"],
        "target_areas": "scattered in foliage for apples, trunk for brown"
      }
    ]
  }
}
```

Be specific about coordinates and areas. The execution AI will follow this plan."""


EXECUTION_PROMPT = """You are an AI artist creating pixel art in Purple Computer's Doodle mode.

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
**Use this for SHADING:** paint lighter keys for highlights, darker keys for shadows.

**GRAYSCALE (Number row: ` 1 2 3 4 5 6 7 8 9 0 - =):**
- ` (backtick) = pure white
- 1 = near white
- 5 = medium gray
- 0 = near black
- = (equals) = pure black

**RED FAMILY (QWERTY row: q w e r t y u i o p [ ] \\):**
- q = lightest pink/salmon (highlight)
- e, r = medium red (primary)
- p = dark red/burgundy
- ], \\ = darkest burgundy (shadow)

**YELLOW FAMILY (ASDF row: a s d f g h j k l ; '):**
- a = lightest gold (highlight)
- d, f = medium yellow/gold (primary)
- l = dark brown-gold
- ; ' = darkest brown (shadow)

**BLUE FAMILY (ZXCV row: z x c v b n m , . /):**
- z = lightest periwinkle (highlight)
- c, v = medium blue (primary)
- m = dark navy
- , . / = darkest navy (shadow)

## SHADING TECHNIQUE

To create 3D depth and realism, use DIFFERENT keys from the same row:
- **Highlights**: Use leftmost keys (q, a, z, 1-2)
- **Midtones**: Use middle keys (r, f, v, 5)
- **Shadows**: Use rightmost keys (p, l, m, 9-0)

Example for a tree trunk: paint 'd' for lit side, 'h' for middle, 'l' for shadow side.

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

The mixing is realistic (Kubelka-Munk spectral mixing), not just RGB blending.

## AVAILABLE ACTIONS

Respond with a JSON array of actions:

**paint_at** - Paint a color at specific coordinates (MOST EFFICIENT!)
```json
{"type": "paint_at", "x": 50, "y": 15, "color": "f"}
```
This instantly paints at the given position. Use this for most painting.

**paint_line** - Draw a horizontal or vertical line
```json
{"type": "paint_line", "x": 40, "y": 10, "key": "f", "direction": "right", "length": 20}
```
Starts at (x,y) and draws `length` cells in `direction`.
Directions: "up", "down", "left", "right"

**move_to** - Position cursor without painting (for visual feedback)
```json
{"type": "move_to", "x": 50, "y": 15}
```

**wait** - Pause (rarely needed)
```json
{"type": "wait", "seconds": 0.3}
```

## REGENERATIVE APPROACH

You are generating a COMPLETE drawing script from scratch each iteration.
The canvas is CLEARED before each attempt. You will see a screenshot of your PREVIOUS attempt's result.

Your goal: Generate a BETTER complete script than last time, learning from what worked and what didn't.

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
- Bright green highlight: yellow + light blue ("z")
- Medium green: yellow + medium blue ("c")
- Dark green shadow: yellow + dark blue ("m")

## RESPONSE FORMAT

Respond with a JSON object:

```json
{
  "analysis": "What I see from the previous attempt and what to improve",
  "strategy_summary": {
    "composition": {
      "element_name": {"x_range": [start, end], "y_range": [start, end], "description": "what this element is"},
      "another_element": {"x_range": [start, end], "y_range": [start, end], "description": "..."}
    },
    "layering_order": [
      "Step 1: Yellow 'f' base on foliage + trunk area (y=5-24)",
      "Step 2: Blue 'c' overlay on foliage only (y=5-18) → green",
      "Step 3: Dark 'l' on trunk (x=48-52) for brown"
    ],
    "color_results": {
      "worked": ["f+c = good green", "l alone = nice brown"],
      "failed": ["c over l = muddy purple"]
    },
    "keep_next_time": ["trunk position at x=48-52", "foliage shape"],
    "change_next_time": ["make trunk wider (x=46-54)", "add more foliage density at edges"]
  },
  "learnings": "Key insight: Blue over brown makes mud. Layer yellow FIRST on all areas, then overlay blue only where green is needed.",
  "actions": [...]
}
```

**analysis**: What you observe in the previous screenshot and your plan to improve.

**strategy_summary**: Structured description of your approach with:
- **composition**: Where each element is positioned (x_range, y_range)
- **layering_order**: Step-by-step painting sequence with colors and coordinates
- **color_results**: What color combinations worked or failed
- **keep_next_time**: Specific things that worked well (with coordinates)
- **change_next_time**: Specific improvements to make (with coordinates)

**learnings**: One key insight that should inform ALL future attempts.

**actions**: Generate 100-500 paint actions for the COMPLETE drawing (canvas starts fresh).
Use paint_line for fills and paint_at for details. More actions = more detail!

Include ALL phases in one script: base colors, overlays for mixing, and details."""


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


def call_vision_api(
    image_base64: str,
    goal: str,
    iteration: int,
    max_iterations: int,
    api_key: str,
    plan: dict = None,
    accumulated_learnings: list[dict] = None,
    previous_strategy: str = None,
) -> dict:
    """Call Claude vision API with screenshot and get analysis + complete action script.

    Args:
        image_base64: Screenshot as base64 PNG
        goal: What to draw
        iteration: Current iteration number (1-indexed)
        max_iterations: Total iterations
        api_key: Anthropic API key
        plan: Drawing plan from planning phase
        accumulated_learnings: List of {iteration, learning} from previous attempts
        previous_strategy: Strategy summary from previous attempt

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

    # Build plan summary
    plan_section = ""
    if plan:
        plan_section = f"\n## DRAWING PLAN\n{plan.get('description', goal)}\n"
        if plan.get('composition'):
            comp = plan['composition']
            if comp.get('main_element'):
                me = comp['main_element']
                plan_section += f"Main element: {me.get('description', '')} at x={me.get('x_range')}, y={me.get('y_range')}\n"

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
{plan_section}{learnings_section}{strategy_section}
{instruction}

Respond with a JSON object containing "analysis", "strategy_summary", "learnings", and "actions" fields."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,  # More tokens for complete scripts
        system=EXECUTION_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64,
                    },
                },
                {"type": "text", "text": user_message},
            ],
        }],
    )

    text = response.content[0].text

    # Parse JSON response
    result = {
        "analysis": "",
        "strategy_summary": "",
        "learnings": "",
        "actions": [],
    }

    try:
        # Find the JSON object
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            result["analysis"] = data.get('analysis', '')
            result["strategy_summary"] = data.get('strategy_summary', '')
            result["learnings"] = data.get('learnings', '')
            result["actions"] = data.get('actions', [])

            # Print feedback
            if result["analysis"]:
                print(f"[AI Analysis] {result['analysis']}")
            if result["strategy_summary"]:
                strat = result["strategy_summary"]
                if isinstance(strat, dict):
                    if strat.get("keep_next_time"):
                        print(f"[AI Keep] {', '.join(strat['keep_next_time'])}")
                    if strat.get("change_next_time"):
                        print(f"[AI Change] {', '.join(strat['change_next_time'])}")
            if result["learnings"]:
                print(f"[AI Learning] {result['learnings']}")

            return result
    except json.JSONDecodeError as e:
        print(f"[Error] JSON parse failed: {e}")
        print(f"[Debug] Raw response:\n{text[:500]}...")

        # Fallback: try to extract just an array (old format)
        try:
            start = text.find('[')
            end = text.rfind(']') + 1
            if start >= 0 and end > start:
                result["actions"] = json.loads(text[start:end])
                return result
        except json.JSONDecodeError:
            pass

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
    output_dir: str = "doodle_ai_output",
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

        for i in range(iterations):
            print(f"\n{'='*50}")
            print(f"ATTEMPT {i + 1}/{iterations}")
            print('='*50)

            # Take screenshot (shows previous attempt's result, or blank for first)
            svg_path = controller.take_screenshot()
            if not svg_path:
                print("[Error] Failed to capture screenshot")
                continue

            print(f"[Screenshot] {svg_path}")

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
            result = call_vision_api(
                image_base64=png_base64,
                goal=goal,
                iteration=i + 1,
                max_iterations=iterations,
                api_key=api_key,
                plan=plan,
                accumulated_learnings=accumulated_learnings,
                previous_strategy=previous_strategy,
            )

            actions = result.get("actions", [])

            # Store full result
            all_results.append({
                "iteration": i + 1,
                "analysis": result.get("analysis", ""),
                "strategy_summary": result.get("strategy_summary", ""),
                "learnings": result.get("learnings", ""),
            })

            if not actions:
                print("[Warning] No actions returned")
                continue

            print(f"[Script] Generated {len(actions)} actions")

            # Store this iteration's script
            iteration_scripts.append({"iteration": i + 1, "actions": actions})

            # Accumulate learnings for next iteration (compact, not full scripts)
            if result.get("learnings"):
                accumulated_learnings.append({
                    "iteration": i + 1,
                    "learning": result["learnings"],
                })
            previous_strategy = result.get("strategy_summary", "")

            # Clear canvas before executing (except first iteration which starts blank)
            if i > 0:
                print("[Clear] Clearing canvas for fresh attempt...")
                if not controller.clear_canvas():
                    print("[ERROR] Failed to clear canvas after retries. Aborting.")
                    print("This may indicate the 'clear' command is not being processed.")
                    break

            # Execute the complete script
            print(f"[Execute] Running script...")
            controller.execute_actions(actions)
            time.sleep(0.1)

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

        # Generate demo script from the FINAL (best) iteration
        if iteration_scripts:
            final_actions = iteration_scripts[-1]["actions"]
            demo_script = generate_demo_script(final_actions)
            script_path = os.path.join(output_dir, "generated_demo.py")
            with open(script_path, 'w') as f:
                f.write(demo_script)
            print(f"[Saved] Demo script (from final attempt): {script_path}")

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
