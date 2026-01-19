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

    def send_commands(self, commands: list[dict]) -> None:
        """Send multiple commands to the app in a single batch."""
        command_path = os.path.join(self.screenshot_dir, 'command')
        # Write all commands as newline-separated JSON
        content = '\n'.join(json.dumps(cmd) for cmd in commands)
        with open(command_path, 'w') as f:
            f.write(content + '\n')
        # Brief wait for app to process
        time.sleep(0.05)

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

SYSTEM_PROMPT = """You are an AI artist creating pixel art in Purple Computer's Doodle mode.

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

## LAYERED PAINTING STRATEGY

To demonstrate color mixing, paint in LAYERS rather than final colors:

**Phase 1 - YELLOW BASE**: Paint yellow (d, f, g keys) everywhere you want:
- Green (grass, leaves, trees)
- Orange (sun, flowers)
- Brown (trunks, ground)

**Phase 2 - BLUE OVERLAY**: Paint blue (c, v, b keys) OVER yellow areas:
- Yellow + Blue = Green (for grass, leaves)

**Phase 3 - RED OVERLAY**: Paint red (r, t, e keys):
- Over yellow = Orange (for sun, flowers)
- Over blue = Purple (for shadows, flowers)

Example for "tree on grass":
1. Paint yellow rectangle for grass area (y=25 to y=31)
2. Paint yellow oval for tree foliage (around y=8-18)
3. Paint blue OVER the grass (makes it green)
4. Paint blue OVER the foliage (makes it green)
5. Paint yellow vertical line for trunk
6. Paint red OVER trunk (makes it brown/orange)

## TIPS

1. Plan your composition: what goes where on the 112×32 canvas
2. Use paint_line for efficiency (one action = many cells)
3. Work in layers: base colors first, then overlay to mix
4. Center your art: start around x=40-60, y=10-20
5. Keep it simple: large shapes read better than tiny details

## RESPONSE FORMAT

Respond with a JSON object containing TWO fields:

```json
{
  "observations": [
    "What I learned or noticed this iteration",
    "What worked or didn't work",
    "Insights about coordinates, colors, or mixing"
  ],
  "actions": [
    {"type": "paint_line", "key": "f", "direction": "right", "length": 10},
    ...
  ]
}
```

**observations**: 2-5 short notes about what you see and learn. These will be shown to you in future iterations so you can build understanding.

**actions**: 20-40 drawing actions to execute.

IMPORTANT: Response must be valid JSON. No comments inside the JSON."""


def call_vision_api(
    image_base64: str,
    goal: str,
    iteration: int,
    max_iterations: int,
    api_key: str,
    accumulated_learnings: list[str] = None,
) -> tuple[list[str], list[dict]]:
    """Call Claude vision API with screenshot and get observations + actions.

    Returns:
        (observations, actions) tuple
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Build user message with accumulated learnings
    learnings_section = ""
    if accumulated_learnings:
        learnings_section = "\n## LEARNINGS FROM PREVIOUS ITERATIONS\n"
        for i, learning in enumerate(accumulated_learnings, 1):
            learnings_section += f"- {learning}\n"
        learnings_section += "\nUse these insights to improve your approach.\n"

    user_message = f"""## Goal: {goal}

## Progress: Iteration {iteration} of {max_iterations}
{learnings_section}
Look at the current canvas. What has been drawn? What's missing?
Based on what you see and any previous learnings, plan your next actions.

Respond with a JSON object containing "observations" and "actions" fields."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
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

    # Parse JSON response (object with observations and actions)
    try:
        # Find the JSON object
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            observations = data.get('observations', [])
            actions = data.get('actions', [])

            # Print observations
            if observations:
                print("[AI Observations]")
                for obs in observations:
                    print(f"  - {obs}")

            return observations, actions
    except json.JSONDecodeError as e:
        print(f"[Error] JSON parse failed: {e}")
        print(f"[Debug] Raw response:\n{text[:500]}...")

        # Fallback: try to extract just an array (old format)
        try:
            start = text.find('[')
            end = text.rfind(']') + 1
            if start >= 0 and end > start:
                actions = json.loads(text[start:end])
                return [], actions
        except json.JSONDecodeError:
            pass

    return [], []


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

        # Switch to Doodle mode and enter paint mode
        print("[Setup] Switching to Doodle mode...")
        controller.switch_to_doodle()
        controller.enter_paint_mode()
        time.sleep(0.2)

        all_actions = []
        all_learnings = []  # Accumulated observations across iterations

        for i in range(iterations):
            print(f"\n{'='*50}")
            print(f"Iteration {i + 1}/{iterations}")
            print('='*50)

            # Take screenshot
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

            # Get observations and actions from AI
            observations, actions = call_vision_api(
                image_base64=png_base64,
                goal=goal,
                iteration=i + 1,
                max_iterations=iterations,
                api_key=api_key,
                accumulated_learnings=all_learnings,
            )

            # Accumulate learnings for next iteration
            if observations:
                all_learnings.extend(observations)

            if not actions:
                print("[Warning] No actions returned")
                continue

            print(f"[Actions] Executing {len(actions)} actions:")
            for j, act in enumerate(actions):
                print(f"  {j+1}. {act}")
            all_actions.extend(actions)

            # Execute actions
            controller.execute_actions(actions)
            time.sleep(0.1)

        # Take final screenshot
        print("\n[Final] Taking final screenshot...")
        final_svg = controller.take_screenshot()
        if final_svg:
            print(f"[Final] {final_svg}")

        # Save action log
        actions_path = os.path.join(output_dir, "actions.json")
        with open(actions_path, 'w') as f:
            json.dump(all_actions, f, indent=2)
        print(f"\n[Saved] Actions: {actions_path}")

        # Save learnings log
        if all_learnings:
            learnings_path = os.path.join(output_dir, "learnings.json")
            with open(learnings_path, 'w') as f:
                json.dump(all_learnings, f, indent=2)
            print(f"[Saved] Learnings: {learnings_path}")

        # Generate demo script
        demo_script = generate_demo_script(all_actions)
        script_path = os.path.join(output_dir, "generated_demo.py")
        with open(script_path, 'w') as f:
            f.write(demo_script)
        print(f"[Saved] Demo script: {script_path}")

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

Output:
    - screenshots/: SVG screenshots from each iteration
    - actions.json: All actions taken
    - generated_demo.py: Demo script for Purple Computer
        """
    )
    parser.add_argument("--goal", required=True, help="What to draw")
    parser.add_argument("--iterations", type=int, default=5, help="Feedback iterations")
    parser.add_argument("--output", default="doodle_ai_output", help="Output directory")

    args = parser.parse_args()

    print("="*60)
    print("Purple Computer AI Drawing Tool")
    print("="*60)
    print(f"Goal: {args.goal}")
    print(f"Iterations: {args.iterations}")
    print(f"Output: {args.output}/")
    print("="*60)
    print()

    run_visual_feedback_loop(
        goal=args.goal,
        iterations=args.iterations,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()
