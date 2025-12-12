#!/bin/bash
# Local Purple Computer Runner
# Run Purple Computer TUI on Mac/Linux for testing

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PURPLE_TUI="$PROJECT_ROOT/purple_tui"
TEST_HOME="$PROJECT_ROOT/.test_home"
ALACRITTY_CONFIG="$PROJECT_ROOT/config/alacritty/alacritty-dev.toml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Purple Computer - Local Test Mode          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo_info "Using Python $PYTHON_VERSION"

# Activate venv if it exists
if [ -d "$PROJECT_ROOT/.venv" ]; then
    echo_info "Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/bin/activate"
else
    echo_warn "No .venv found. Run 'make setup' first."
    echo ""
    read -p "Run setup now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        "$PROJECT_ROOT/scripts/setup_dev.sh"
        source "$PROJECT_ROOT/.venv/bin/activate"
    else
        echo "Exiting. Run 'make setup' to create virtual environment."
        exit 1
    fi
fi

# Create test home directory for packs
echo_info "Creating test environment at $TEST_HOME"
mkdir -p "$TEST_HOME/.purple/packs"

# Copy packs to test environment
echo_info "Copying content packs..."
if [ -d "$PROJECT_ROOT/packs/core-emoji" ]; then
    cp -r "$PROJECT_ROOT/packs/core-emoji" "$TEST_HOME/.purple/packs/"
fi
if [ -d "$PROJECT_ROOT/packs/core-definitions" ]; then
    cp -r "$PROJECT_ROOT/packs/core-definitions" "$TEST_HOME/.purple/packs/"
fi
if [ -d "$PROJECT_ROOT/packs/core-sounds" ]; then
    cp -r "$PROJECT_ROOT/packs/core-sounds" "$TEST_HOME/.purple/packs/"
fi

# Check dependencies
echo_info "Checking Python dependencies..."
MISSING_DEPS=()

python3 -c "import textual" 2>/dev/null || MISSING_DEPS+=("textual")
python3 -c "import rich" 2>/dev/null || MISSING_DEPS+=("rich")
python3 -c "import wcwidth" 2>/dev/null || MISSING_DEPS+=("wcwidth")

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo_warn "Missing dependencies: ${MISSING_DEPS[*]}"
    echo_warn "Install with: pip3 install ${MISSING_DEPS[*]}"
    echo ""
    read -p "Install dependencies now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip3 install ${MISSING_DEPS[*]}
    else
        echo "You can install them later and run this script again."
        exit 0
    fi
fi

echo ""
echo_info "Starting Purple Computer TUI..."
echo_info "F1-F4: Switch modes | Ctrl+V: Cycle views | F12: Theme"
echo ""

# Set environment variables
export HOME="$TEST_HOME"
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Check for Alacritty
USE_ALACRITTY=false
if command -v alacritty &> /dev/null; then
    USE_ALACRITTY=true
    echo_info "Alacritty found - launching with Purple theme"
elif [[ "$OSTYPE" == "darwin"* ]] && [ -d "/Applications/Alacritty.app" ]; then
    USE_ALACRITTY=true
    echo_info "Alacritty.app found - launching with Purple theme"
else
    echo_warn "Alacritty not found - running in current terminal"
    echo_warn "Install Alacritty for the full Purple experience: brew install alacritty"
fi

cd "$PROJECT_ROOT"

if [ "$USE_ALACRITTY" = true ]; then
    # Create a launcher script for Alacritty to run
    LAUNCHER=$(mktemp)
    cat > "$LAUNCHER" << EOF
#!/bin/bash
source "$PROJECT_ROOT/.venv/bin/activate"
export HOME="$TEST_HOME"
export PYTHONPATH="$PROJECT_ROOT:\$PYTHONPATH"
# Pass through test/demo environment variables
export PURPLE_TEST_BATTERY="${PURPLE_TEST_BATTERY:-}"
export PURPLE_SLEEP_DEMO="${PURPLE_SLEEP_DEMO:-}"
cd "$PROJECT_ROOT"
python -m purple_tui.purple_tui
EOF
    chmod +x "$LAUNCHER"

    # Launch Alacritty with our config
    if [[ "$OSTYPE" == "darwin"* ]] && [ -d "/Applications/Alacritty.app" ]; then
        /Applications/Alacritty.app/Contents/MacOS/alacritty --config-file "$ALACRITTY_CONFIG" -e "$LAUNCHER"
    else
        alacritty --config-file "$ALACRITTY_CONFIG" -e "$LAUNCHER"
    fi

    rm -f "$LAUNCHER"
else
    sleep 1
    python -m purple_tui.purple_tui
fi

echo ""
echo_info "Purple Computer session ended."
