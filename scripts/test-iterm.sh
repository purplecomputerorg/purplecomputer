#!/bin/bash
#
# Purple Computer - iTerm2 Testing Script
# Resizes iTerm2 to the correct dimensions and runs Purple Computer or specific modes
#
# Usage:
#   ./scripts/test-iterm.sh              # Run full Purple Computer
#   ./scripts/test-iterm.sh music        # Run music mode directly
#   ./scripts/test-iterm.sh emoji        # Run emoji mode directly
#   ./scripts/test-iterm.sh math         # Run math mode directly
#

set -e

# Change to repo root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Activate venv if it exists
if [ -d "$REPO_ROOT/.venv" ]; then
    source "$REPO_ROOT/.venv/bin/activate"
else
    echo "Error: No .venv found. Run 'make setup' first."
    exit 1
fi

# Set up Python path
export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

# Purple Computer standard terminal size
# Optimized for typical laptop screens (16:9 and 16:10)
COLS=100
ROWS=30

echo "Resizing iTerm2 to ${COLS}x${ROWS}..."

# Resize iTerm2 window using AppleScript
osascript <<EOF
tell application "iTerm2"
    tell current window
        tell current session
            set columns to $COLS
            set rows to $ROWS
        end tell
    end tell
end tell
EOF

sleep 0.5

# Verify the resize worked
ACTUAL_COLS=$(tput cols)
ACTUAL_ROWS=$(tput lines)
echo "Terminal size: ${ACTUAL_COLS}x${ACTUAL_ROWS}"

if [ $ACTUAL_COLS -lt $COLS ] || [ $ACTUAL_ROWS -lt $ROWS ]; then
    echo "Warning: Terminal size is smaller than expected!"
    echo "Try manually resizing the window or adjusting iTerm2 font size."
fi

echo ""

# Determine what to run
MODE="${1:-}"

case "$MODE" in
    music)
        echo "Running Music Mode..."
        python3 packs/music_mode_basic/data/music_mode.py
        ;;
    emoji)
        echo "Running Emoji Mode..."
        python3 -c "from purple_repl.modes.emoji import mode; mode()"
        ;;
    math)
        echo "Running Math Mode..."
        python3 -c "from purple_repl.modes.math import mode; mode()"
        ;;
    rainbow)
        echo "Running Rainbow Mode..."
        python3 -c "from purple_repl.modes.rainbow import mode; mode()"
        ;;
    speech)
        echo "Running Speech Mode..."
        python3 -c "from purple_repl.modes.speech import mode; mode()"
        ;;
    surprise)
        echo "Running Surprise Mode..."
        python3 -c "from purple_repl.modes.surprise import mode; mode()"
        ;;
    "")
        echo "Starting Purple Computer..."
        echo "Press Ctrl+D to exit"
        echo ""
        python3 -m purple_repl.repl
        ;;
    *)
        echo "Unknown mode: $MODE"
        echo ""
        echo "Available modes:"
        echo "  music     - Musical keyboard"
        echo "  emoji     - Emoji mode"
        echo "  math      - Math mode"
        echo "  rainbow   - Rainbow text mode"
        echo "  speech    - Speech mode"
        echo "  surprise  - Surprise mode"
        echo ""
        echo "Or run without arguments to start full Purple Computer"
        exit 1
        ;;
esac
