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
echo_step "Setting up Piper TTS voice..."
PIPER_VOICES_DIR="$HOME/.local/share/piper-voices"
VOICE_MODEL="en_US-libritts-high"
if [ -f "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx" ]; then
    echo_info "✓ Piper voice model already downloaded"
else
    mkdir -p "$PIPER_VOICES_DIR"
    echo_info "Downloading Piper voice model ($VOICE_MODEL)..."
    # Download from Hugging Face
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/$VOICE_MODEL.onnx" -o "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/$VOICE_MODEL.onnx.json" -o "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx.json"
    if [ -f "$PIPER_VOICES_DIR/$VOICE_MODEL.onnx" ]; then
        echo_info "✓ Piper voice model downloaded"
    else
        echo_warn "Could not download Piper voice model (TTS may not work)"
    fi
fi

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

# Install JetBrainsMono Nerd Font (for UI icons in Alacritty)
echo_step "Checking JetBrainsMono Nerd Font..."
install_nerd_font() {
    local FONT_VERSION="3.3.0"
    local FONT_URL="https://github.com/ryanoasis/nerd-fonts/releases/download/v${FONT_VERSION}/JetBrainsMono.zip"
    local TEMP_DIR=$(mktemp -d)

    echo_info "Downloading JetBrainsMono Nerd Font..."
    curl -sL "$FONT_URL" -o "$TEMP_DIR/jetbrains-mono-nerd.zip"
    unzip -q "$TEMP_DIR/jetbrains-mono-nerd.zip" -d "$TEMP_DIR/fonts"

    if [ "$OS" = "mac" ]; then
        mkdir -p ~/Library/Fonts
        cp "$TEMP_DIR/fonts/"*.ttf ~/Library/Fonts/ 2>/dev/null || true
        echo_info "✓ JetBrainsMono Nerd Font installed to ~/Library/Fonts/"
    else
        mkdir -p ~/.local/share/fonts
        cp "$TEMP_DIR/fonts/"*.ttf ~/.local/share/fonts/ 2>/dev/null || true
        fc-cache -f ~/.local/share/fonts
        echo_info "✓ JetBrainsMono Nerd Font installed to ~/.local/share/fonts/"
    fi

    rm -rf "$TEMP_DIR"
}

if [ "$OS" = "mac" ]; then
    if ls ~/Library/Fonts/JetBrainsMonoNerdFont-* &> /dev/null 2>&1; then
        echo_info "✓ JetBrainsMono Nerd Font already installed"
    else
        install_nerd_font
    fi
elif [ "$OS" = "linux" ]; then
    if fc-list | grep -qi "JetBrainsMono Nerd Font" 2>/dev/null; then
        echo_info "✓ JetBrainsMono Nerd Font already installed"
    else
        install_nerd_font
    fi
fi

# Install Noto Color Emoji (for Unicode emoji)
echo_step "Checking Noto Color Emoji font..."
if [ "$OS" = "mac" ]; then
    # macOS has built-in emoji support via Apple Color Emoji
    echo_info "✓ macOS has built-in emoji support"
elif [ "$OS" = "linux" ]; then
    if fc-list | grep -qi "Noto Color Emoji" 2>/dev/null; then
        echo_info "✓ Noto Color Emoji already installed"
    else
        echo_info "Installing Noto Color Emoji..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get install -y fonts-noto-color-emoji
            echo_info "✓ Noto Color Emoji installed"
        else
            echo_warn "Could not install Noto Color Emoji (apt not available)"
            echo_warn "Install manually: https://fonts.google.com/noto/specimen/Noto+Color+Emoji"
        fi
    fi

    # Install fontconfig rule to prioritize Noto Color Emoji
    # Without this, some emoji may render as monochrome outlines
    echo_step "Installing emoji fontconfig rule..."
    FONTCONFIG_DIR="/etc/fonts/conf.d"
    EMOJI_CONF="$PROJECT_ROOT/config/fontconfig/99-emoji.conf"
    if [ -f "$EMOJI_CONF" ]; then
        if [ ! -f "$FONTCONFIG_DIR/99-emoji.conf" ]; then
            sudo cp "$EMOJI_CONF" "$FONTCONFIG_DIR/"
            sudo fc-cache -f
            echo_info "✓ Emoji fontconfig rule installed"
        else
            echo_info "✓ Emoji fontconfig rule already installed"
        fi
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
echo "  F1-F3: Switch modes (Ask, Play, Write)"
echo "  Ctrl+V: Cycle views (Screen, Line, Ears)"
echo "  F12: Toggle dark/light theme"
echo ""
