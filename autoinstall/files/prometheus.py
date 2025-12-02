#!/usr/bin/env python3
"""
Prometheus - Purple Computer Installer Display

Minimal, beautiful purple installation experience.
Runs in raw terminal mode with ANSI escape codes - no dependencies.
"""
import sys
import os
import time

# Purple theme colors (ANSI 256-color)
BG = "\033[48;2;45;27;78m"      # #2d1b4e - deep purple
FG = "\033[38;2;245;243;255m"   # #f5f3ff - soft white
DIM = "\033[38;2;139;92;246m"   # #8b5cf6 - muted purple
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

def get_terminal_size():
    try:
        cols, rows = os.get_terminal_size()
        return cols, rows
    except:
        return 80, 24

def fill_background(cols, rows):
    """Fill entire screen with purple background."""
    sys.stdout.write(HIDE_CURSOR + CLEAR)
    for _ in range(rows):
        sys.stdout.write(BG + " " * cols + RESET + "\n")
    sys.stdout.flush()

def center_text(text, cols):
    """Center text horizontally."""
    padding = (cols - len(text)) // 2
    return " " * max(0, padding) + text

def draw(lines, subtitle=""):
    """Draw centered content on purple background."""
    cols, rows = get_terminal_size()
    fill_background(cols, rows)

    # Position content vertically centered
    content_height = len(lines) + (2 if subtitle else 0)
    start_row = (rows - content_height) // 2

    for i, line in enumerate(lines):
        row = start_row + i
        sys.stdout.write(f"\033[{row};1H")  # Move cursor to row
        sys.stdout.write(BG + FG + center_text(line, cols) + RESET)

    if subtitle:
        row = start_row + len(lines) + 1
        sys.stdout.write(f"\033[{row};1H")
        sys.stdout.write(BG + DIM + center_text(subtitle, cols) + RESET)

    sys.stdout.flush()

def spinner_frame(frame):
    """Simple dot spinner."""
    dots = ["   ", ".  ", ".. ", "..."]
    return dots[frame % 4]

def progress(message, duration=0):
    """Show progress message with optional spinner."""
    cols, rows = get_terminal_size()

    if duration > 0:
        frames = int(duration * 4)
        for i in range(frames):
            draw([
                "Purple Computer",
                "",
                message + spinner_frame(i)
            ])
            time.sleep(0.25)
    else:
        draw([
            "Purple Computer",
            "",
            message
        ])

def installing():
    """Main installation display sequence."""
    draw([
        "Purple Computer",
        "",
        "Installing..."
    ], "A computer for curious kids")

def ready():
    """Show ready message."""
    draw([
        "Purple Computer",
        "",
        "Ready!"
    ])
    time.sleep(1)

def cleanup():
    """Restore terminal state."""
    sys.stdout.write(SHOW_CURSOR + RESET + CLEAR)
    sys.stdout.flush()

def main():
    """Run as standalone or handle commands."""
    if len(sys.argv) < 2:
        # Demo mode
        try:
            installing()
            time.sleep(2)
            progress("Setting up files", 2)
            progress("Configuring system", 2)
            ready()
        except KeyboardInterrupt:
            pass
        finally:
            cleanup()
        return

    cmd = sys.argv[1]

    if cmd == "start":
        installing()
    elif cmd == "progress":
        msg = sys.argv[2] if len(sys.argv) > 2 else "Working"
        dur = float(sys.argv[3]) if len(sys.argv) > 3 else 0
        progress(msg, dur)
    elif cmd == "ready":
        ready()
    elif cmd == "cleanup":
        cleanup()
    else:
        # Just display the message
        draw(["Purple Computer", "", cmd])

if __name__ == "__main__":
    main()
