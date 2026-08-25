#!/bin/bash
# Run Purple Computer locally in a window, driven by the window's own keyboard
# events instead of evdev (so it works on any dev machine, including macOS).
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_HOME="$PROJECT_ROOT/.test_home"

echo "Purple Computer, local test mode"
echo "Tap Escape: room picker | Hold Escape 1s: parent menu | Hold \\ 3s: parent menu"
echo

if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo "No .venv found. Run 'just setup' first."
    exit 1
fi
source "$PROJECT_ROOT/.venv/bin/activate"

mkdir -p "$TEST_HOME/.purple/packs"
for pack in core-emoji core-definitions core-sounds; do
    [ -d "$PROJECT_ROOT/packs/$pack" ] && cp -r "$PROJECT_ROOT/packs/$pack" "$TEST_HOME/.purple/packs/"
done

export HOME="$TEST_HOME"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export PURPLE_NO_EVDEV=1
export PYGAME_HIDE_SUPPORT_PROMPT=1
# Fullscreen for demo recording; a window otherwise (PURPLE_WINDOW_SIZE=WxH to pick one).
if [ -z "$PURPLE_DEMO_AUTOSTART" ] && [ -z "$PURPLE_FULLSCREEN" ]; then
    export PURPLE_WINDOWED=1
    export PURPLE_WINDOW_SIZE="${PURPLE_WINDOW_SIZE:-1366x768}"
fi

cd "$PROJECT_ROOT"
exec python -m purple_tui
