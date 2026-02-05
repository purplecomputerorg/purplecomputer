#!/usr/bin/env python3
"""Install an AI-generated doodle demo into Purple Computer.

Reads training output from doodle_ai.py and generates a demo script
that can be played back with PURPLE_DEMO_AUTOSTART=1.

Usage:
    ./tools/install-doodle-demo --from doodle_ai_output/20260202_143022
    ./tools/install-doodle-demo --from doodle_ai_output/20260202_143022/screenshots/iteration_2b_refinement_cropped.png
    ./tools/install-doodle-demo --from doodle_ai_output/20260202_143022 --iteration 3 --duration 12
"""

import argparse
import json
import os
import sys

# Add project root to path so we can import from tools/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def estimate_duration(actions: list[dict]) -> float:
    """Estimate playback duration in seconds from a list of raw actions.

    Uses the default delay values from the demo script dataclasses
    (MoveSequence, DrawPath, PressKey, etc.) to estimate total time.
    """
    total = 0.0
    for action in actions:
        t = action.get('type')
        if t == 'move':
            # Becomes PressKey with default pause_after=0.2
            total += 0.2
        elif t == 'move_to':
            # Becomes MoveSequence: 0.008s per step + 0.05s pause
            dx = abs(action.get('x', 0))
            dy = abs(action.get('y', 0))
            # Rough estimate (we don't track cursor, so use target coords as upper bound)
            steps = dx + dy
            total += steps * 0.008 + 0.05
        elif t == 'stamp':
            total += 0.2
        elif t == 'paint_at':
            # move_to + PressKey
            dx = abs(action.get('x', 0))
            dy = abs(action.get('y', 0))
            total += (dx + dy) * 0.008 + 0.05 + 0.2
        elif t == 'paint_line':
            length = action.get('length', 1)
            # move_to + DrawPath
            dx = abs(action.get('x', 0))
            dy = abs(action.get('y', 0))
            total += (dx + dy) * 0.008 + 0.05
            total += length * 0.02 + 0.3
        elif t == 'wait':
            total += action.get('seconds', 0.3)
    # Add fixed overhead: SwitchMode(0.3+0.5), PressKey tab(0.2), final Pause(1.0)
    total += 0.3 + 0.5 + 0.2 + 1.0
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Install an AI-generated doodle demo into Purple Computer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # From output directory (picks best iteration)
    ./tools/install-doodle-demo --from doodle_ai_output/20260202_143022

    # From a specific screenshot (uses that iteration)
    ./tools/install-doodle-demo --from doodle_ai_output/20260202_143022/screenshots/iteration_2b_refinement_cropped.png

    # Pick specific iteration, target 12s
    ./tools/install-doodle-demo --from doodle_ai_output/20260202_143022 --iteration 3 --duration 12

After installing, run:
    make run-demo
        """,
    )
    parser.add_argument("--from", dest="from_path", required=True, metavar="PATH",
                        help="Training output directory, or a screenshot PNG/SVG from it")
    parser.add_argument("--iteration", default=None,
                        help="Which iteration to use (default: best, or inferred from screenshot)")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Target playback duration in seconds (default: 10)")

    args = parser.parse_args()

    from_path = args.from_path
    iteration = args.iteration

    # Resolve --from to an output directory (and optionally an iteration)
    if os.path.isfile(from_path) and from_path.lower().endswith(('.png', '.svg')):
        from tools.doodle_ai import resolve_screenshot_to_output_dir, extract_iteration_label

        # For SVG, look for the corresponding _cropped.png
        if from_path.lower().endswith('.svg'):
            png_candidate = from_path.rsplit('.', 1)[0] + '_cropped.png'
            if os.path.exists(png_candidate):
                from_path = png_candidate

        output_dir = resolve_screenshot_to_output_dir(from_path)

        if iteration is None:
            iteration = extract_iteration_label(from_path)
            print(f"Using iteration from screenshot: {iteration}")
    elif os.path.isdir(from_path):
        output_dir = from_path
    else:
        print(f"Error: path not found: {from_path}")
        sys.exit(1)

    # Load iteration scripts
    scripts_path = os.path.join(output_dir, "iteration_scripts.json")
    if not os.path.exists(scripts_path):
        print(f"Error: iteration_scripts.json not found in {output_dir}")
        sys.exit(1)
    with open(scripts_path) as f:
        iteration_scripts = json.load(f)

    if not iteration_scripts:
        print("Error: iteration_scripts.json is empty")
        sys.exit(1)

    # Determine which iteration to use (if not already set from screenshot)
    if iteration is None:
        # Read best_iteration.json
        best_path = os.path.join(output_dir, "best_iteration.json")
        if os.path.exists(best_path):
            with open(best_path) as f:
                best_info = json.load(f)
            iteration = best_info.get("best_attempt")
            if iteration:
                print(f"Using best iteration: {iteration} ({best_info.get('reason', 'no reason')})")
        if iteration is None:
            # Fall back to last iteration
            iteration = iteration_scripts[-1]["iteration"]
            print(f"No best iteration found, using last: {iteration}")

    # Find the script for the chosen iteration
    actions = None
    for entry in iteration_scripts:
        if entry["iteration"] == iteration:
            actions = entry["actions"]
            break

    if actions is None:
        available = [e["iteration"] for e in iteration_scripts]
        print(f"Error: iteration {iteration} not found. Available: {available}")
        sys.exit(1)

    # Generate demo script
    from tools.doodle_ai import generate_demo_script
    demo_code = generate_demo_script(actions)

    # Estimate duration and calculate speed multiplier
    estimated = estimate_duration(actions)
    target = args.duration
    if estimated > 0:
        speed_multiplier = estimated / target
    else:
        speed_multiplier = 1.0

    # Build the output file content
    output_content = demo_code + "\n\n"
    output_content += f"SPEED_MULTIPLIER = {speed_multiplier:.4f}\n"

    # Write to purple_tui/demo/ai_generated_script.py
    dest_path = os.path.join(PROJECT_ROOT, "purple_tui", "demo", "ai_generated_script.py")
    with open(dest_path, 'w') as f:
        f.write(output_content)

    print("\nInstalled demo script:")
    print(f"  Source: {output_dir} (iteration {iteration})")
    print(f"  Destination: {dest_path}")
    print(f"  Actions: {len(actions)}")
    print(f"  Estimated duration: {estimated:.1f}s")
    print(f"  Target duration: {target:.1f}s")
    print(f"  Speed multiplier: {speed_multiplier:.4f}")
    print("\nTo run:")
    print("  make run-demo")


if __name__ == "__main__":
    main()
