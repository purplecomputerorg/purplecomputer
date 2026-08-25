#!/bin/bash
# Purple Computer Development Setup
# Quick setup for local development and testing

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Purple Computer Development Setup          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

cd "$PROJECT_ROOT"

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="mac"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
fi

echo_info "Detected OS: $OS"

# Check Python
echo_step "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found."
    if [ "$OS" = "mac" ]; then
        echo "Install with: brew install python3"
    else
        echo "Install with: sudo apt install python3 python3-pip"
    fi
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo_info "✓ Python $PYTHON_VERSION found"

# Create virtual environment
echo_step "Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo_info "✓ Created .venv"
else
    echo_info "✓ .venv already exists"
fi

# Activate venv
source .venv/bin/activate

# Install system dependencies for evdev (Linux only)
if [ "$OS" = "linux" ]; then
    echo_step "Checking system build dependencies for evdev..."
    if ! command -v gcc &> /dev/null || [ ! -f /usr/include/python3*/Python.h ] 2>/dev/null; then
        echo_info "Installing gcc and python3-dev (required to build evdev)..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get install -y gcc python3-dev
        else
            echo_warn "Please install gcc and python3-dev manually"
        fi
    else
        echo_info "✓ Build dependencies already installed"
    fi

    echo_step "Setting up input device permissions..."
    # Add user to input group
    if ! groups | grep -q '\binput\b'; then
        echo_info "Adding $USER to input group..."
        sudo usermod -a -G input "$USER"
        echo_warn "You'll need to log out and back in for group changes to take effect"
    else
        echo_info "✓ Already in input group"
    fi

    # Set up uinput permissions (needed for keyboard normalizer)
    if [ ! -w /dev/uinput ] 2>/dev/null; then
        echo_info "Setting up /dev/uinput permissions..."
        # Create persistent udev rule
        UDEV_RULE='KERNEL=="uinput", GROUP="input", MODE="0660"'
        UDEV_FILE="/etc/udev/rules.d/99-purple-uinput.rules"
        if [ ! -f "$UDEV_FILE" ]; then
            echo "$UDEV_RULE" | sudo tee "$UDEV_FILE" > /dev/null
            sudo udevadm control --reload-rules
            sudo udevadm trigger
        fi
        # Also fix it immediately for this session
        sudo chmod 660 /dev/uinput
        sudo chown root:input /dev/uinput
        echo_info "✓ uinput permissions configured"
    else
        echo_info "✓ uinput already accessible"
    fi
fi

# Install Python dependencies
echo_step "Installing Python dependencies into venv..."
pip install --upgrade pip
pip install -r requirements.txt

echo_info "✓ Python dependencies installed in virtual environment"

# Download Piper voice model
"$SCRIPT_DIR/install_piper_voice.sh"

# Build content packs
echo_step "Building content packs..."
if [ -d "packs/core-emoji" ]; then
    cd packs/core-emoji
    tar -czvf ../core-emoji.purplepack manifest.json content/
    cd "$PROJECT_ROOT"
    echo_info "✓ Built core-emoji.purplepack"
fi

if [ -d "packs/core-definitions" ]; then
    cd packs/core-definitions
    tar -czvf ../core-definitions.purplepack manifest.json content/
    cd "$PROJECT_ROOT"
    echo_info "✓ Built core-definitions.purplepack"
fi

# Color emoji for the UI (the ISO installs fonts-noto-color-emoji; a dev box
# needs the file where purple_tui/gfx.py looks for it). macOS uses its own.
echo_step "Checking Noto Color Emoji..."
if [ "$OS" = "linux" ]; then
    EMOJI_FONT="$HOME/.local/share/fonts/NotoColorEmoji.ttf"
    if [ -f "$EMOJI_FONT" ] || [ -f /usr/share/fonts/truetype/noto/NotoColorEmoji.ttf ]; then
        echo_info "✓ Noto Color Emoji present"
    else
        mkdir -p "$(dirname "$EMOJI_FONT")"
        curl -fsSL https://github.com/googlefonts/noto-emoji/raw/main/fonts/NotoColorEmoji.ttf -o "$EMOJI_FONT" \
            && echo_info "✓ Noto Color Emoji installed to $EMOJI_FONT" \
            || echo_warn "Could not download Noto Color Emoji; emoji will render from the text font"
    fi
fi

# Summary
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Setup Complete!                            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo_info "Virtual environment created at .venv/"
echo_info "Activate it with: source .venv/bin/activate"
echo ""
echo_info "You can now run Purple Computer:"
echo ""
echo "  make run"
echo "  (or ./scripts/run_local.sh)"
echo ""
echo_info "Controls:"
echo "  Tap Escape: room picker (Play, Music, Art)"
echo "  Hold Escape 1s: parent menu"
echo "  Hold \\ 3s: parent menu (alternate)"
echo ""
