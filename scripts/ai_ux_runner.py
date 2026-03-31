#!/usr/bin/env python3
"""Interactive launcher for AI UX testing.

Friendly terminal UI that walks you through choosing a persona, room,
and settings, then kicks off the AI agent testing session.

Usage: just ux
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_ux_config import DEFAULT_MAX_STEPS, DEFAULT_MODEL

# ANSI colors
BOLD = "\033[1m"
DIM = "\033[2m"
PURPLE = "\033[35m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

PERSONAS = {
    "explorer": {
        "label": "Curious 5yo",
        "desc": "Explores everything, presses keys to see what happens, tries all rooms",
    },
    "keymash": {
        "label": "Key masher (4yo)",
        "desc": "Slams keys randomly via raw evdev, tests crash resistance",
    },
    "methodical": {
        "label": "Careful 7yo",
        "desc": "Reads prompts, types math in Play, draws shapes in Art, plays notes",
    },
    "coder": {
        "label": "Code kid (8yo)",
        "desc": "Focuses on the code panel/REPL, types commands, tests errors",
    },
    "parent": {
        "label": "Parent",
        "desc": "Non-technical adult evaluating the app for their kid",
    },
    "shift": {
        "label": "Shift tester (6yo)",
        "desc": "Tests physical shift, sticky shift, caps lock via raw evdev",
    },
}

ROOMS = {
    "play": "Play room (math, typing, questions)",
    "music": "Music room (keyboard notes, melodies)",
    "art": "Art room (drawing, turtle graphics)",
}


def print_header():
    print()
    print(f"  {PURPLE}{BOLD}AI UX Testing for Purple Computer{RESET}")
    print(f"  {DIM}Let a Claude agent pretend to be a kid and find bugs{RESET}")
    print()


def print_divider():
    print(f"  {DIM}{'~' * 50}{RESET}")


def pick_option(prompt, options, default=None):
    """Show numbered options and get user choice. Returns the key."""
    keys = list(options.keys())
    print(f"  {BOLD}{prompt}{RESET}")
    print()
    for i, key in enumerate(keys, 1):
        opt = options[key]
        if isinstance(opt, dict):
            label = opt.get("label", key)
            desc = opt.get("desc", "")
            marker = f"{CYAN}>{RESET} " if key == default else "  "
            print(f"  {marker}{BOLD}{i}{RESET}. {label}")
            if desc:
                print(f"       {DIM}{desc}{RESET}")
        else:
            marker = f"{CYAN}>{RESET} " if key == default else "  "
            print(f"  {marker}{BOLD}{i}{RESET}. {key} {DIM}- {opt}{RESET}")
    print()

    default_num = keys.index(default) + 1 if default else 1
    while True:
        try:
            hint = f" [{default_num}]" if default else ""
            raw = input(f"  Choice{hint}: ").strip()
            if not raw and default:
                return default
            num = int(raw)
            if 1 <= num <= len(keys):
                return keys[num - 1]
            print(f"  {RED}Pick 1-{len(keys)}{RESET}")
        except ValueError:
            # Maybe they typed the key name
            if raw.lower() in keys:
                return raw.lower()
            print(f"  {RED}Pick 1-{len(keys)}{RESET}")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)


def ask_number(prompt, default, lo, hi):
    """Ask for a number with a default."""
    while True:
        try:
            raw = input(f"  {prompt} [{default}]: ").strip()
            if not raw:
                return default
            val = int(raw)
            if lo <= val <= hi:
                return val
            print(f"  {RED}{lo}-{hi} please{RESET}")
        except ValueError:
            print(f"  {RED}Enter a number{RESET}")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)


def check_api_key():
    """Check for ANTHROPIC_API_KEY."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    # Check .env file
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        os.environ["ANTHROPIC_API_KEY"] = key
                        return True
    return False


def estimate_cost(max_steps):
    """Rough cost estimate for a session."""
    # ~2K input tokens per step (system + history), ~200 output tokens
    # Sonnet pricing: $3/M input, $15/M output
    avg_input_per_step = 3000  # grows with history, average over session
    avg_output_per_step = 250
    total_input = avg_input_per_step * max_steps
    total_output = avg_output_per_step * max_steps
    cost = (total_input / 1_000_000 * 3) + (total_output / 1_000_000 * 15)
    return cost


def main():
    print_header()

    # Check API key
    if not check_api_key():
        print(f"  {RED}No ANTHROPIC_API_KEY found.{RESET}")
        print(f"  Set it in your environment or in .env")
        print()
        sys.exit(1)
    print(f"  {GREEN}API key found{RESET}")
    print()
    print_divider()
    print()

    # Pick persona
    persona = pick_option("Who should test the app?", PERSONAS, default="explorer")
    print()
    print_divider()
    print()

    # Pick room
    room = pick_option("Starting room?", ROOMS, default="play")
    print()
    print_divider()
    print()

    # Max steps
    max_steps = ask_number("Max steps (each step = one API call)", DEFAULT_MAX_STEPS, 5, 200)
    print()
    print_divider()
    print()

    # Model choice
    models = {
        "claude-sonnet-4-6": {"label": "Sonnet 4.6", "desc": "Fast, cheap, good for most testing (~$0.50/50 steps)"},
        "claude-opus-4-6": {"label": "Opus 4.6", "desc": "Smarter, finds subtler issues, ~5x more expensive"},
        "claude-haiku-4-5-20251001": {"label": "Haiku 4.5", "desc": "Cheapest, good for keymash/crash testing"},
    }
    model = pick_option("Model?", models, default=DEFAULT_MODEL)
    print()
    print_divider()
    print()

    # Summary
    cost = estimate_cost(max_steps)
    persona_info = PERSONAS[persona]
    print(f"  {BOLD}Ready to run:{RESET}")
    print(f"    Persona:  {persona_info['label']} ({persona})")
    print(f"    Room:     {room}")
    print(f"    Steps:    {max_steps}")
    print(f"    Model:    {model}")
    print(f"    Est cost: ~${cost:.2f}")
    print()

    try:
        confirm = input(f"  {BOLD}Start? [Y/n]{RESET} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    if confirm and confirm not in ("y", "yes"):
        print(f"  {DIM}Cancelled.{RESET}")
        sys.exit(0)

    print()
    print(f"  {GREEN}Launching...{RESET}")
    print()

    # Run the test script
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_ux_test.py")
    cmd = [
        sys.executable, script,
        "--persona", persona,
        "--room", room,
        "--max-steps", str(max_steps),
        "--model", model,
    ]

    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print()
        print(f"  {YELLOW}Interrupted. Partial results may be in /tmp/purple_ux_test/{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
