#!/bin/bash
# Purple Computer Setup Script
# Run this manually if you're installing Purple Computer on an existing Ubuntu system
# (instead of using the autoinstall ISO)

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
echo_info "Installing required packages..."
apt install -y \
    xorg \
    xinit \
    kitty \
    python3 \
    python3-pip \
    python3-venv \
    ipython3 \
    espeak-ng \
    python3-pyttsx3 \
    alsa-utils \
    pulseaudio \
    fonts-noto \
    fonts-noto-color-emoji \
    fonts-dejavu \
    git \
    curl \
    wget \
    vim \
    build-essential \
    python3-dev

# Install Python packages
echo_info "Installing Python packages..."
pip3 install --system colorama termcolor

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

# Also support legacy kiduser name
if ! id "kiduser" &>/dev/null; then
    echo_info "Creating kiduser account (legacy)..."
    useradd -m -s /bin/bash kiduser
    passwd -l kiduser
fi

# Add purple user to audio group
usermod -a -G audio purple

# Also add kiduser for backwards compatibility
if id "kiduser" &>/dev/null; then
    usermod -a -G audio kiduser
fi

# Create directory structure for both users
echo_info "Creating Purple Computer directories..."
mkdir -p /home/purple/.purple/modes
mkdir -p /home/purple/.purple/packs
mkdir -p /home/purple/.config/kitty
mkdir -p /usr/share/purple

# Also for kiduser (legacy)
if [ -d "/home/kiduser" ]; then
    mkdir -p /home/kiduser/.purple/modes
    mkdir -p /home/kiduser/.purple/packs
    mkdir -p /home/kiduser/.config/kitty
fi

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Copy Purple REPL files
echo_info "Installing Purple REPL..."
if [ -d "$SCRIPT_DIR/../../purple_repl" ]; then
    cp -r "$SCRIPT_DIR/../../purple_repl/"* /home/purple/.purple/
    # Also copy to kiduser if exists
    if [ -d "/home/kiduser" ]; then
        cp -r "$SCRIPT_DIR/../../purple_repl/"* /home/kiduser/.purple/
    fi
else
    echo_warn "Purple REPL files not found. You'll need to copy them manually."
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
    if [ -d "/home/kiduser" ]; then
        cp "$SCRIPT_DIR/xinit/xinitrc" /home/kiduser/.xinitrc
        chmod +x /home/kiduser/.xinitrc
    fi
fi

# Copy kitty config
echo_info "Installing Kitty configuration..."
if [ -f "$SCRIPT_DIR/kitty/kitty.conf" ]; then
    cp "$SCRIPT_DIR/kitty/kitty.conf" /home/purple/.config/kitty/kitty.conf
    if [ -d "/home/kiduser" ]; then
        cp "$SCRIPT_DIR/kitty/kitty.conf" /home/kiduser/.config/kitty/kitty.conf
    fi
fi

# Create .bash_profile for auto-startx
echo_info "Configuring auto-start..."
cat > /home/purple/.bash_profile <<'EOF'
# Purple Computer auto-start X11
if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = "1" ]; then
    exec startx
fi
EOF

if [ -d "/home/kiduser" ]; then
    cat > /home/kiduser/.bash_profile <<'EOF'
# Purple Computer auto-start X11
if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = "1" ]; then
    exec startx
fi
EOF
fi

# Copy IPython profile
echo_info "Installing IPython configuration..."
if [ -d "$SCRIPT_DIR/ipython" ]; then
    mkdir -p /home/purple/.ipython/profile_default/startup
    cp "$SCRIPT_DIR/ipython/"*.py /home/purple/.ipython/profile_default/startup/
    if [ -d "/home/kiduser" ]; then
        mkdir -p /home/kiduser/.ipython/profile_default/startup
        cp "$SCRIPT_DIR/ipython/"*.py /home/kiduser/.ipython/profile_default/startup/
    fi
fi

# Install Python dependencies for new modules
echo_info "Installing Python dependencies..."
pip3 install --system packaging 2>/dev/null || true

# Set ownership
echo_info "Setting file ownership..."
chown -R purple:purple /home/purple/.purple
chown -R purple:purple /home/purple/.config
chown purple:purple /home/purple/.xinitrc
chown purple:purple /home/purple/.bash_profile
chown -R purple:purple /home/purple/.ipython 2>/dev/null || true

if [ -d "/home/kiduser" ]; then
    chown -R kiduser:kiduser /home/kiduser/.purple
    chown -R kiduser:kiduser /home/kiduser/.config
    chown kiduser:kiduser /home/kiduser/.xinitrc 2>/dev/null || true
    chown kiduser:kiduser /home/kiduser/.bash_profile 2>/dev/null || true
    chown -R kiduser:kiduser /home/kiduser/.ipython 2>/dev/null || true
fi

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
echo_info "Parent mode: Press Ctrl+C (or Ctrl+Alt+P if configured)"
