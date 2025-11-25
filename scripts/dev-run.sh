#!/bin/bash
# Purple Computer Development Runner
# Run the Purple REPL in your current terminal for testing

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Purple Computer - Development Mode${NC}"
echo "===================================="
echo ""

# Check if we're in the right directory
if [ ! -f "purple_repl/repl.py" ]; then
    echo -e "${YELLOW}Warning: purple_repl/repl.py not found${NC}"
    echo "Please run this script from the repository root:"
    echo "  ./scripts/dev-run.sh"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Check dependencies
echo ""
echo "Checking dependencies..."

check_dep() {
    if python3 -c "import $1" 2>/dev/null; then
        echo -e "  ✓ $1"
    else
        echo -e "  ✗ $1 (missing)"
        return 1
    fi
}

MISSING=0

check_dep "IPython" || MISSING=1
check_dep "colorama" || MISSING=1

if [ $MISSING -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}Some dependencies are missing.${NC}"
    echo "Install with:"
    echo "  pip3 install ipython colorama"
    echo ""
    read -p "Install now? (y/n) " -n 1 -r
    echo
    if [[ $REPL =~ ^[Yy]$ ]]; then
        pip3 install ipython colorama
    else
        echo "Exiting."
        exit 1
    fi
fi

# Set up Python path
export PYTHONPATH="${PWD}/purple_repl:${PYTHONPATH}"

# Create temporary IPython profile for development
DEV_IPYTHON_DIR="/tmp/purple_dev_ipython"
mkdir -p "$DEV_IPYTHON_DIR/profile_default/startup"

# Copy startup files
if [ -d "autoinstall/files/ipython" ]; then
    cp autoinstall/files/ipython/*.py "$DEV_IPYTHON_DIR/profile_default/startup/"
fi

export IPYTHONDIR="$DEV_IPYTHON_DIR"

echo ""
echo -e "${GREEN}Starting Purple Computer REPL...${NC}"
echo ""
echo "Development mode notes:"
echo "  • Running in your current terminal"
echo "  • Press Ctrl+D or type 'exit' to quit"
echo "  • TTS may not work without proper audio setup"
echo "  • Fullscreen not enabled (use actual install for that)"
echo ""
echo "===================================="
echo ""

# Run the REPL
cd purple_repl
python3 repl.py

# Cleanup
rm -rf "$DEV_IPYTHON_DIR"
