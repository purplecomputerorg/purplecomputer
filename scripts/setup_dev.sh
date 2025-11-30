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

# Install Python dependencies
echo_step "Installing Python dependencies into venv..."
pip install --upgrade pip
pip install textual rich wcwidth

echo_info "✓ Python dependencies installed in virtual environment"

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

# Install JetBrains Mono font (for Alacritty)
echo_step "Checking JetBrains Mono font..."
install_jetbrains_mono() {
    local FONT_VERSION="2.304"
    local FONT_URL="https://github.com/JetBrains/JetBrainsMono/releases/download/v${FONT_VERSION}/JetBrainsMono-${FONT_VERSION}.zip"
    local TEMP_DIR=$(mktemp -d)

    echo_info "Downloading JetBrains Mono..."
    curl -sL "$FONT_URL" -o "$TEMP_DIR/jetbrains-mono.zip"
    unzip -q "$TEMP_DIR/jetbrains-mono.zip" -d "$TEMP_DIR"

    if [ "$OS" = "mac" ]; then
        mkdir -p ~/Library/Fonts
        cp "$TEMP_DIR/fonts/ttf/"*.ttf ~/Library/Fonts/
        echo_info "✓ JetBrains Mono installed to ~/Library/Fonts/"
    else
        mkdir -p ~/.local/share/fonts
        cp "$TEMP_DIR/fonts/ttf/"*.ttf ~/.local/share/fonts/
        fc-cache -f ~/.local/share/fonts
        echo_info "✓ JetBrains Mono installed to ~/.local/share/fonts/"
    fi

    rm -rf "$TEMP_DIR"
}

if [ "$OS" = "mac" ]; then
    if ls ~/Library/Fonts/JetBrainsMono-* &> /dev/null 2>&1; then
        echo_info "✓ JetBrains Mono already installed"
    else
        install_jetbrains_mono
    fi
elif [ "$OS" = "linux" ]; then
    if fc-list | grep -qi "JetBrains Mono" 2>/dev/null; then
        echo_info "✓ JetBrains Mono already installed"
    else
        install_jetbrains_mono
    fi
fi

# Check Alacritty (optional but recommended)
echo_step "Checking Alacritty installation (optional)..."
ALACRITTY_AVAILABLE=false
if command -v alacritty &> /dev/null; then
    echo_info "✓ Alacritty is installed"
    ALACRITTY_AVAILABLE=true
elif [[ "$OSTYPE" == "darwin"* ]] && [ -d "/Applications/Alacritty.app" ]; then
    echo_info "✓ Alacritty.app is installed"
    ALACRITTY_AVAILABLE=true
else
    echo_warn "Alacritty not found (optional but recommended)"
    if [ "$OS" = "mac" ]; then
        echo_warn "Install with: brew install --cask alacritty"
    else
        echo_warn "Install with: sudo apt install alacritty"
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
if [ "$ALACRITTY_AVAILABLE" = true ]; then
    echo_info "Alacritty detected - 'make run' will use Purple theme"
else
    echo_warn "For the full Purple experience, install Alacritty:"
    if [ "$OS" = "mac" ]; then
        echo "  brew install --cask alacritty"
    else
        echo "  sudo apt install alacritty"
    fi
    echo ""
fi
echo_info "You can now run Purple Computer:"
echo ""
echo "  make run"
echo "  (or ./scripts/run_local.sh)"
echo ""
echo_info "Controls:"
echo "  F1-F4: Switch modes (Ask, Play, Listen, Write)"
echo "  Ctrl+V: Cycle views (Screen, Line, Ears)"
echo "  F12: Toggle dark/light theme"
echo ""
