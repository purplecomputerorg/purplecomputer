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

def svg_to_png_base64(svg_path: str) -> str:
    """Convert SVG file to base64-encoded PNG."""
    try:
        from cairosvg import svg2png
        png_data = svg2png(url=svg_path)
        return base64.standard_b64encode(png_data).decode('utf-8')
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
        return base64.standard_b64encode(png_data).decode('utf-8')


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

    def clear_canvas(self, max_retries: int = 3) -> bool:
        """Clear the entire canvas. Returns True if verified clear, False otherwise."""
        for attempt in range(max_retries):
            print(f"[Clear] Attempt {attempt + 1}/{max_retries}...")

            # Send clear command and wait for it to be consumed
            consumed = self.send_commands(
                [{"action": "clear", "value": ""}],
                wait_for_consumption=True
            )
            if not consumed:
                print("[Clear] Command not consumed by app!")
                continue

            time.sleep(0.2)  # Give time for clear to take effect

            # Take a screenshot to verify
            svg_path = self.take_screenshot()
            if svg_path and self._verify_canvas_clear(svg_path):
                print("[Clear] Canvas verified clear")
                return True
            else:
                print(f"[Clear] Canvas not clear, retrying...")
                time.sleep(0.2)

        print("[Clear] WARNING: Could not verify canvas was cleared")
        return False

    def _verify_canvas_clear(self, svg_path: str) -> bool:
        """Check if the canvas SVG shows a mostly blank canvas."""
        try:
            with open(svg_path, 'r') as f:
                svg_content = f.read()

            # Count colored rectangles (painted cells)
            # Blank canvas has mostly the default purple background
            # Painted cells have different fill colors
            import re

            # Look for rect elements with fill colors that aren't the default purple background
            # Default background is around #2a1845 (dark) or #e8daf0 (light)
            default_colors = ['#2a1845', '#e8daf0', '#1e1033', '#f0e8f8', 'none']

            # Find all fill colors in the SVG
            fills = re.findall(r'fill="(#[0-9a-fA-F]{6})"', svg_content)

            # Count non-default colors
            painted_count = sum(1 for f in fills if f.lower() not in [c.lower() for c in default_colors])

            # Allow a small number of non-default colors (cursor, UI elements)
            is_clear = painted_count < 20
            print(f"[Clear] Found {painted_count} painted cells (clear={is_clear})")
            return is_clear
        except Exception as e:
            print(f"[Clear] Verification error: {e}")
            return False

    def execute_action(self, action: dict) -> None:
        """Execute a single drawing action using batched commands for speed."""
        action_type = action.get('type')

        if action_type == 'move':
            self.send_command("key", action['direction'])

        elif action_type == 'move_to':
            # Batch all movement commands for speed
            commands = []
            # First go to top-left (112 left + 32 up to be safe)
            commands.extend([{"action": "key", "value": "left"} for _ in range(112)])
            commands.extend([{"action": "key", "value": "up"} for _ in range(32)])
            # Then navigate to target
            commands.extend([{"action": "key", "value": "right"} for _ in range(action.get('x', 0))])
            commands.extend([{"action": "key", "value": "down"} for _ in range(action.get('y', 0))])
            self.send_commands(commands)

        elif action_type == 'select_color':
            # Shift+key to select without stamping (uppercase letter)
            key = action['key'].upper()
            self.send_command("key", key)

        elif action_type == 'stamp':
            self.send_command("key", "space")

        elif action_type == 'paint_line':
            key = action['key'].upper()  # Uppercase for shift (select without stamp)
            direction = action['direction']
            length = action.get('length', 1)

            # Batch: select color, then stamp+move repeatedly
            commands = [{"action": "key", "value": key}]  # Select color
            for _ in range(length):
                commands.append({"action": "key", "value": "space"})
                commands.append({"action": "key", "value": direction})
            self.send_commands(commands)

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
The canvas is **112 cells wide × 32 cells tall**.
- X coordinates: 0 (left) to 111 (right)
- Y coordinates: 0 (top) to 31 (bottom)
- Origin (0,0) is TOP-LEFT corner

## COLOR SYSTEM
- **QWERTY row (q-p)**: RED family (light to dark)
- **ASDF row (a-l)**: YELLOW family (light to dark)
- **ZXCV row (z-m)**: BLUE family (light to dark)
- **Number row (1-0)**: GRAYSCALE (white to black)

## COLOR MIXING
When you paint OVER an already-painted cell, colors MIX:
- Yellow + Blue = GREEN
- Red + Blue = PURPLE
- Red + Yellow = ORANGE

## YOUR TASK
Create a detailed PLAN for drawing the requested image. You will have multiple iterations to execute this plan.

The plan should include:
1. **Composition**: Where elements go on the 112x32 canvas
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
The canvas is **112 cells wide × 32 cells tall**.
- X coordinates: 0 (left) to 111 (right)
- Y coordinates: 0 (top) to 31 (bottom)
- Origin (0,0) is TOP-LEFT corner

## WHAT YOU SEE IN SCREENSHOTS
- Colored cells are painted areas
- Letters visible on cells (like "F", "C", "R") are just labels showing which key painted that cell
- The cursor is a 3×3 blinking ring of box-drawing characters (┌━┐ etc.)
- Purple background = unpainted canvas

## COLOR SYSTEM (KEYBOARD ROWS)

Each keyboard row produces a COLOR FAMILY. Within each row, LEFT keys are LIGHTER, RIGHT keys are DARKER.

**GRAYSCALE (Number row 1-0):**
- 1 = white (#FFFFFF)
- 5 = medium gray (#808080)
- 0 = black (#000000)

**RED FAMILY (QWERTY row: q w e r t y u i o p):**
- q = lightest pink/salmon
- e, r = medium red (good primary red)
- p = darkest burgundy

**YELLOW FAMILY (ASDF row: a s d f g h j k l):**
- a = lightest gold
- d, f = medium yellow/gold (good primary yellow)
- l = darkest brown-gold

**BLUE FAMILY (ZXCV row: z x c v b n m):**
- z = lightest periwinkle
- c, v = medium blue (good primary blue)
- m = darkest navy

## COLOR MIXING

When you paint OVER an already-painted cell, colors MIX like real paint:
- Yellow + Blue = GREEN
- Red + Blue = PURPLE
- Red + Yellow = ORANGE

The mixing is realistic (Kubelka-Munk spectral mixing), not just RGB blending.

## AVAILABLE ACTIONS

Respond with a JSON array. Each action is an object:

**move** - Move cursor without painting
```json
{"type": "move", "direction": "up"}
```
Directions: "up", "down", "left", "right"

**move_to** - Jump to absolute coordinates
```json
{"type": "move_to", "x": 50, "y": 15}
```
Note: x must be 0-111, y must be 0-31

**select_color** - Load brush with color (no painting)
```json
{"type": "select_color", "key": "f"}
```

**stamp** - Paint one cell at cursor position
```json
{"type": "stamp"}
```

**paint_line** - Draw a line of cells (MOST USEFUL!)
```json
{"type": "paint_line", "key": "f", "direction": "right", "length": 10}
```
This selects color, then stamps and moves repeatedly.
The line starts at current position and extends in direction.

**wait** - Pause (rarely needed)
```json
{"type": "wait", "seconds": 0.3}
```

## REGENERATIVE APPROACH

You are generating a COMPLETE drawing script from scratch each iteration.
The canvas is CLEARED before each attempt. You will see a screenshot of your PREVIOUS attempt's result.

Your goal: Generate a BETTER complete script than last time, learning from what worked and what didn't.

## LAYERED PAINTING (within each attempt)

To get mixed colors, you must paint in layers WITHIN your script:
1. First paint YELLOW in areas that will be green, orange, or brown
2. Then paint BLUE over yellow areas to create GREEN
3. Then paint RED over yellow for ORANGE, or over blue for PURPLE

Example sequence for green foliage:
- paint_line with key="f" (yellow) to fill the area
- paint_line with key="c" (blue) over the SAME area to mix into green

## RESPONSE FORMAT

Respond with a JSON object:

```json
{
  "analysis": "What I see from the previous attempt and what to improve",
  "actions": [
    {"type": "move_to", "x": 50, "y": 10},
    {"type": "paint_line", "key": "f", "direction": "right", "length": 20},
    ...
  ]
}
```

**analysis**: Brief analysis of the previous result and your improvement strategy.

**actions**: 50-100 actions for the COMPLETE drawing (this is a fresh canvas).

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
    previous_actions: list[dict] = None,
) -> tuple[str, list[dict]]:
    """Call Claude vision API with screenshot and get analysis + complete action script.

    Returns:
        (analysis, actions) tuple
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Build previous actions section (ALL actions from last iteration)
    prev_actions_section = ""
    if previous_actions:
        prev_actions_section = f"\n## PREVIOUS ATTEMPT'S SCRIPT ({len(previous_actions)} actions)\n"
        prev_actions_section += "These actions were executed on the previous attempt. The screenshot shows the result.\n"
        prev_actions_section += "```json\n"
        # Show all actions (they need to see what they did)
        for act in previous_actions:
            prev_actions_section += f"{json.dumps(act)}\n"
        prev_actions_section += "```\n"
        prev_actions_section += "\nAnalyze what worked and what didn't. Generate an IMPROVED complete script.\n"

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
{plan_section}{prev_actions_section}
{instruction}

Respond with a JSON object containing "analysis" and "actions" fields."""

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

    # Parse JSON response (object with analysis and actions)
    try:
        # Find the JSON object
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            analysis = data.get('analysis', '')
            actions = data.get('actions', [])

            # Print analysis
            if analysis:
                print(f"[AI Analysis] {analysis}")

            return analysis, actions
    except json.JSONDecodeError as e:
        print(f"[Error] JSON parse failed: {e}")
        print(f"[Debug] Raw response:\n{text[:500]}...")

        # Fallback: try to extract just an array (old format)
        try:
            start = text.find('[')
            end = text.rfind(']') + 1
            if start >= 0 and end > start:
                actions = json.loads(text[start:end])
                return "", actions
        except json.JSONDecodeError:
            pass

    return "", []


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

        all_analyses = []  # Store analysis from each iteration
        iteration_scripts = []  # Store each iteration's complete script
        previous_actions = []  # Actions from previous iteration

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

            # Convert to PNG for vision API
            png_base64 = svg_to_png_base64(svg_path)
            if not png_base64:
                print("[Error] Failed to convert SVG to PNG")
                continue

            # Get analysis and NEW complete script from AI
            analysis, actions = call_vision_api(
                image_base64=png_base64,
                goal=goal,
                iteration=i + 1,
                max_iterations=iterations,
                api_key=api_key,
                plan=plan,
                previous_actions=previous_actions,
            )

            # Store analysis
            if analysis:
                all_analyses.append({"iteration": i + 1, "analysis": analysis})

            if not actions:
                print("[Warning] No actions returned")
                continue

            print(f"[Script] Generated {len(actions)} actions")

            # Store this iteration's script
            iteration_scripts.append({"iteration": i + 1, "actions": actions})
            previous_actions = actions  # Save for next iteration's learning

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

        # Save analyses
        if all_analyses:
            analyses_path = os.path.join(output_dir, "analyses.json")
            with open(analyses_path, 'w') as f:
                json.dump(all_analyses, f, indent=2)
            print(f"[Saved] Analyses: {analyses_path}")

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
    """Convert actions to a Purple Computer demo script."""
    lines = [
        '"""AI-generated drawing demo."""',
        '',
        'from purple_tui.demo.script import (',
        '    PressKey, SwitchMode, Pause, DrawPath, Comment,',
        ')',
        '',
        'AI_DRAWING = [',
        '    Comment("=== AI GENERATED DRAWING ==="),',
        '    SwitchMode("doodle"),',
        '    Pause(0.3),',
        '    PressKey("tab"),  # Enter paint mode',
        '',
    ]

    for action in actions:
        t = action.get('type')

        if t == 'move':
            lines.append(f'    PressKey("{action["direction"]}"),')
        elif t == 'stamp':
            lines.append('    PressKey("space"),')
        elif t == 'paint_line':
            key = action['key']
            direction = action['direction']
            length = action.get('length', 1)
            dirs = [direction] * length
            lines.append(f'    DrawPath(directions={dirs}, color_key="{key}", delay_per_step=0.05),')
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
