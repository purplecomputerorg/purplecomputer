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
        env['PURPLE_DEMO_AUTOSTART'] = '0'  # Don't auto-run demo
        # Add project root to PYTHONPATH so purple_tui can be found
        project_root = str(Path(__file__).parent.parent)
        env['PYTHONPATH'] = project_root + ':' + env.get('PYTHONPATH', '')

        # Start the app
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'purple_tui.purple_tui'],
            stdin=pty_slave,
            stdout=pty_slave,
            stderr=subprocess.DEVNULL,
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
        print(f"[App] Debug log: {self.screenshot_dir}/dev_commands.log")
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
        command_path = os.path.join(self.screenshot_dir, 'command')
        cmd = json.dumps({"action": action, "value": value})
        print(f"[Debug] Writing command to {command_path}: {cmd}")
        with open(command_path, 'w') as f:
            f.write(cmd + '\n')
        # Wait for app to process (checks every 0.1s)
        time.sleep(0.2)
        # Check if command was consumed
        if os.path.exists(command_path):
            print(f"[Debug] WARNING: Command file still exists (not consumed)")
        else:
            print(f"[Debug] Command consumed")

    def send_key(self, key: str) -> None:
        """Send a single key to the app via command file."""
        # Handle shift+key -> uppercase letter
        if key.startswith('shift+'):
            char = key[6:].upper()
            print(f"[Key] shift+{key[6:]} -> {char}")
            self.send_command("key", char)
        else:
            print(f"[Key] {key}")
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
        time.sleep(0.3)

    def enter_paint_mode(self) -> None:
        """Enter paint mode (Tab in Doodle mode)."""
        self.send_key('tab')
        time.sleep(0.2)

    def execute_action(self, action: dict) -> None:
        """Execute a single drawing action."""
        action_type = action.get('type')

        if action_type == 'move':
            self.send_key(action['direction'])

        elif action_type == 'move_to':
            # Move to position via repeated arrows
            # First go to top-left, then navigate
            for _ in range(50):
                self.send_key('left')
            for _ in range(30):
                self.send_key('up')
            time.sleep(0.1)
            for _ in range(action.get('x', 0)):
                self.send_key('right')
            for _ in range(action.get('y', 0)):
                self.send_key('down')

        elif action_type == 'select_color':
            # Shift+key to select without stamping (uppercase letter)
            self.send_key(f"shift+{action['key']}")

        elif action_type == 'stamp':
            self.send_key('space')

        elif action_type == 'paint_line':
            key = action['key']
            direction = action['direction']
            length = action.get('length', 1)

            # Select color (uppercase to select without stamping)
            self.send_key(f"shift+{key}")
            time.sleep(0.02)

            # Stamp and move repeatedly
            for _ in range(length):
                self.send_key('space')
                self.send_key(direction)

        elif action_type == 'type_text':
            # Exit paint mode first
            self.send_key('tab')
            time.sleep(0.1)
            for char in action.get('text', ''):
                self.send_key(char)
            # Re-enter paint mode
            self.send_key('tab')
            time.sleep(0.1)

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

## What You See
You're looking at a screenshot of the Purple Computer app in Doodle/Paint mode.
The canvas is a grid of colored cells. The cursor shows your current position.

## How Painting Works
- You're in PAINT mode (not text mode)
- Select color with shift+key (doesn't stamp)
- Press space to stamp at cursor
- Arrow keys move the cursor
- Or use paint_line to draw multiple cells at once

## Color Keys (KEYBOARD ROW = COLOR FAMILY)
Left keys are LIGHT, right keys are DARK:
- QWERTY (q,w,e,r,t,y,u,i,o,p): RED/PINK family
- ASDF (a,s,d,f,g,h,j,k,l): YELLOW/ORANGE family
- ZXCV (z,x,c,v,b,n,m): BLUE family
- Numbers 1-0: Grayscale (1=white, 0=black)

## Color Mixing (IMPORTANT!)
When you paint over existing paint, colors MIX like real paint:
- Yellow (f) + Blue (c) = GREEN
- Red (r) + Blue (c) = PURPLE
- Red (r) + Yellow (f) = ORANGE

## Available Actions (respond with JSON array)
- {"type": "move", "direction": "up|down|left|right"}
- {"type": "move_to", "x": 10, "y": 5}
- {"type": "select_color", "key": "f"}
- {"type": "stamp"}
- {"type": "paint_line", "key": "f", "direction": "right", "length": 5}
- {"type": "wait", "seconds": 0.3}

## Tips for Good Art
1. Background first (sky, ground), then details
2. Use color mixing! Yellow then blue = green grass/leaves
3. Darker shades for shadows, lighter for highlights
4. Build shapes with multiple paint_line actions
5. Leave some negative space

Respond with a JSON array of 10-20 actions. Start with // comment explaining your plan."""


def call_vision_api(
    image_base64: str,
    goal: str,
    iteration: int,
    max_iterations: int,
    api_key: str,
) -> list[dict]:
    """Call Claude vision API with screenshot and get next actions."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    user_message = f"""## Goal: {goal}

## Progress: Iteration {iteration} of {max_iterations}

Look at the current canvas. What has been drawn? What's missing?
Generate 10-20 actions to continue toward the goal.

Respond with:
1. // Brief comment about what you'll draw
2. JSON array of actions"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
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

    # Print the AI's comment
    for line in text.split('\n'):
        if line.strip().startswith('//'):
            print(f"[AI] {line.strip()}")
            break

    # Extract JSON array
    try:
        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError as e:
        print(f"[Error] JSON parse failed: {e}")

    return []


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
        time.sleep(0.5)

        all_actions = []

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

            # Get actions from AI
            actions = call_vision_api(
                image_base64=png_base64,
                goal=goal,
                iteration=i + 1,
                max_iterations=iterations,
                api_key=api_key,
            )

            if not actions:
                print("[Warning] No actions returned")
                continue

            print(f"[Actions] Executing {len(actions)} actions:")
            for j, act in enumerate(actions):
                print(f"  {j+1}. {act}")
            all_actions.extend(actions)

            # Execute actions
            controller.execute_actions(actions)
            time.sleep(0.3)

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
