#!/bin/bash
# Local Purple Computer Runner
# Run Purple Computer REPL on Mac/Linux for testing
# This simulates the kid experience without full installation

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PURPLE_DIR="$PROJECT_ROOT/purple_repl"
TEST_HOME="$PROJECT_ROOT/.test_home"

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
echo "║   Purple Computer - Local Test Mode         ║"
echo "╔══════════════════════════════════════════════╗"
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

# Create test home directory
echo_info "Creating test environment at $TEST_HOME"
mkdir -p "$TEST_HOME/.purple/packs"
mkdir -p "$TEST_HOME/.purple/modes"
mkdir -p "$TEST_HOME/.ipython/profile_default/startup"

# Copy Purple REPL files to test home
echo_info "Copying Purple REPL files..."
cp -r "$PURPLE_DIR"/*.py "$TEST_HOME/.purple/" 2>/dev/null || true
cp -r "$PURPLE_DIR/modes" "$TEST_HOME/.purple/" 2>/dev/null || true

# Copy IPython startup files
echo_info "Setting up IPython environment..."
if [ -d "$PROJECT_ROOT/autoinstall/files/ipython" ]; then
    cp "$PROJECT_ROOT/autoinstall/files/ipython"/*.py "$TEST_HOME/.ipython/profile_default/startup/"
fi

# Install example packs if available
if [ -f "$PROJECT_ROOT/packs/core-emoji.purplepack" ]; then
    echo_info "Installing core emoji pack..."
    cd "$TEST_HOME/.purple"
    python <<EOF
from pack_manager import PackManager, get_registry
from pathlib import Path

packs_dir = Path('$TEST_HOME/.purple/packs')
registry = get_registry()
manager = PackManager(packs_dir, registry)

success, msg = manager.install_pack_from_file(Path('$PROJECT_ROOT/packs/core-emoji.purplepack'))
print(f"Core emoji pack: {msg}")

if Path('$PROJECT_ROOT/packs/education-basics.purplepack').exists():
    success, msg = manager.install_pack_from_file(Path('$PROJECT_ROOT/packs/education-basics.purplepack'))
    print(f"Education pack: {msg}")
EOF
fi

# Check dependencies
echo_info "Checking Python dependencies..."
MISSING_DEPS=()

python3 -c "import IPython" 2>/dev/null || MISSING_DEPS+=("ipython")
python3 -c "import colorama" 2>/dev/null || MISSING_DEPS+=("colorama")
python3 -c "import termcolor" 2>/dev/null || MISSING_DEPS+=("termcolor")
python3 -c "import packaging" 2>/dev/null || MISSING_DEPS+=("packaging")

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
echo_info "Starting Purple Computer REPL..."
echo_info "Press Ctrl+C to access parent mode"
echo_info "Type 'exit()' to quit"
echo ""
sleep 1

# Set environment variables
export HOME="$TEST_HOME"
export IPYTHONDIR="$TEST_HOME/.ipython"

# Run the REPL (use 'python' since venv is activated)
cd "$TEST_HOME/.purple"
python repl.py

echo ""
echo_info "Purple Computer session ended."
