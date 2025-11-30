#!/bin/bash
# Purple Computer Setup Script
# Run this manually if you're installing Purple Computer on an existing Ubuntu system
# (instead of using the autoinstall ISO)
#
# Architecture: Ubuntu Server + minimal Xorg (no desktop environment) + Alacritty fullscreen
# No GUI, no window manager, no desktop bloat - just a fullscreen terminal with Textual TUI

set -e

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

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo_info "This script needs root privileges. Please run with sudo."
    exit 1
fi

echo_info "Installing Purple Computer on this system..."

# Update package list
echo_info "Updating package list..."
apt update

# Install required packages
# IMPORTANT: Minimal Xorg only - NO desktop environment, NO window manager
echo_info "Installing required packages..."
apt install -y \
    xorg \
    xinit \
    alacritty \
    python3 \
    python3-pip \
    python3-venv \
    alsa-utils \
    pulseaudio \
    fonts-noto \
    fonts-noto-color-emoji \
    fonts-dejavu \
    fonts-jetbrains-mono \
    git \
    curl \
    wget \
    vim \
    build-essential \
    python3-dev \
    unclutter

# Install Nerd Font for icons
echo_info "Installing JetBrainsMono Nerd Font..."
FONT_DIR="/usr/share/fonts/truetype/jetbrains-mono-nerd"
if [ ! -d "$FONT_DIR" ]; then
    mkdir -p "$FONT_DIR"
    cd /tmp
    wget -q https://github.com/ryanoasis/nerd-fonts/releases/download/v3.3.0/JetBrainsMono.zip
    unzip -q JetBrainsMono.zip -d "$FONT_DIR"
    rm JetBrainsMono.zip
    fc-cache -f
    cd -
    echo_info "Nerd Font installed"
else
    echo_info "Nerd Font already installed, skipping"
fi

# Install Piper TTS for speech synthesis
echo_info "Installing Piper TTS..."
# Piper binary and voice model will be installed to /opt/piper
mkdir -p /opt/piper
cd /opt/piper
# Download latest piper release for linux
if [ ! -f piper ]; then
    wget -q https://github.com/rhasspy/piper/releases/latest/download/piper_linux_x86_64.tar.gz
    tar -xzf piper_linux_x86_64.tar.gz
    rm piper_linux_x86_64.tar.gz
fi
# Download a kid-friendly voice (en_US-lessac-medium)
if [ ! -f en_US-lessac-medium.onnx ]; then
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
fi
cd -

# Install Python packages
echo_info "Installing Python packages..."
pip3 install --system textual rich wcwidth

# Create purple user if doesn't exist
# Note: Changed from 'kiduser' to 'purple' for cleaner branding
# NO PASSWORD is set - auto-login only, parent mode protected separately
if ! id "purple" &>/dev/null; then
    echo_info "Creating purple user account..."
    useradd -m -s /bin/bash purple
    # Lock the password (no password login possible)
    passwd -l purple
    echo_info "Purple user created (no password, auto-login only)"
else
    echo_info "User purple already exists, skipping."
fi

# Add purple user to audio group
usermod -a -G audio purple

# Create directory structure
echo_info "Creating Purple Computer directories..."
mkdir -p /home/purple/.purple/modes
mkdir -p /home/purple/.purple/packs
mkdir -p /home/purple/.config/alacritty
mkdir -p /usr/share/purple

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Copy Purple TUI files
echo_info "Installing Purple TUI..."
if [ -d "$SCRIPT_DIR/../../purple_tui" ]; then
    cp -r "$SCRIPT_DIR/../../purple_tui/"* /home/purple/.purple/
else
    echo_warn "Purple TUI files not found. You'll need to copy them manually."
fi

# Copy systemd service files
echo_info "Installing systemd service..."
if [ -f "$SCRIPT_DIR/systemd/getty-override.conf" ]; then
    mkdir -p /etc/systemd/system/getty@tty1.service.d
    cp "$SCRIPT_DIR/systemd/getty-override.conf" /etc/systemd/system/getty@tty1.service.d/override.conf
    systemctl daemon-reload
fi

# Copy xinitrc
echo_info "Installing X11 startup configuration..."
if [ -f "$SCRIPT_DIR/xinit/xinitrc" ]; then
    cp "$SCRIPT_DIR/xinit/xinitrc" /home/purple/.xinitrc
    chmod +x /home/purple/.xinitrc
fi

# Copy Alacritty config
echo_info "Installing Alacritty configuration..."
if [ -f "$SCRIPT_DIR/alacritty/alacritty.toml" ]; then
    cp "$SCRIPT_DIR/alacritty/alacritty.toml" /home/purple/.config/alacritty/alacritty.toml
fi

# Create .bash_profile for auto-startx
echo_info "Configuring auto-start..."
cat > /home/purple/.bash_profile <<'EOF'
# Purple Computer auto-start X11
if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = "1" ]; then
    exec startx
fi
EOF

# Set ownership
echo_info "Setting file ownership..."
# Fix /home/purple directory itself first (prevents .Xauthority and log issues)
chown purple:purple /home/purple
chown -R purple:purple /home/purple/.purple
chown -R purple:purple /home/purple/.config
chown purple:purple /home/purple/.xinitrc
chown purple:purple /home/purple/.bash_profile

# Disable unnecessary services
echo_info "Disabling unnecessary services..."
systemctl disable systemd-networkd-wait-online.service 2>/dev/null || true
systemctl disable NetworkManager.service 2>/dev/null || true
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

# Set GRUB timeout
echo_info "Configuring fast boot..."
if [ -f /etc/default/grub ]; then
    sed -i 's/GRUB_TIMEOUT=.*/GRUB_TIMEOUT=1/' /etc/default/grub
    update-grub
fi

echo_info "================================================"
echo_info "Purple Computer installation complete!"
echo_info "================================================"
echo ""
echo_info "To start Purple Computer:"
echo_info "1. Reboot the system"
echo_info "2. Or login as 'purple' user on TTY1"
echo ""
echo_info "User 'purple' has NO SYSTEM PASSWORD (auto-login only)"
echo_info "Parent features are protected by a separate parent password"
echo_info "You'll be prompted to create a parent password on first parent mode access"
echo ""
echo_info "Parent mode: Hold Ctrl and press V"
