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

# Create kiduser if doesn't exist
if ! id "kiduser" &>/dev/null; then
    echo_info "Creating kiduser account..."
    useradd -m -s /bin/bash kiduser
    echo "kiduser:purplecomputer" | chpasswd
    echo_warn "Default password is 'purplecomputer' - please change it!"
else
    echo_info "User kiduser already exists, skipping."
fi

# Add kiduser to audio group
usermod -a -G audio kiduser

# Create directory structure
echo_info "Creating Purple Computer directories..."
mkdir -p /home/kiduser/.purple/modes
mkdir -p /home/kiduser/.config/kitty
mkdir -p /usr/share/purple

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Copy Purple REPL files
echo_info "Installing Purple REPL..."
if [ -d "$SCRIPT_DIR/../../purple_repl" ]; then
    cp -r "$SCRIPT_DIR/../../purple_repl/"* /home/kiduser/.purple/
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
    cp "$SCRIPT_DIR/xinit/xinitrc" /home/kiduser/.xinitrc
    chmod +x /home/kiduser/.xinitrc
fi

# Copy kitty config
echo_info "Installing Kitty configuration..."
if [ -f "$SCRIPT_DIR/kitty/kitty.conf" ]; then
    cp "$SCRIPT_DIR/kitty/kitty.conf" /home/kiduser/.config/kitty/kitty.conf
fi

# Create .bash_profile for auto-startx
echo_info "Configuring auto-start..."
cat > /home/kiduser/.bash_profile <<'EOF'
# Purple Computer auto-start X11
if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = "1" ]; then
    exec startx
fi
EOF

# Copy IPython profile
echo_info "Installing IPython configuration..."
if [ -d "$SCRIPT_DIR/ipython" ]; then
    mkdir -p /home/kiduser/.ipython/profile_default/startup
    cp "$SCRIPT_DIR/ipython/"*.py /home/kiduser/.ipython/profile_default/startup/
fi

# Set ownership
echo_info "Setting file ownership..."
chown -R kiduser:kiduser /home/kiduser/.purple
chown -R kiduser:kiduser /home/kiduser/.config
chown kiduser:kiduser /home/kiduser/.xinitrc
chown kiduser:kiduser /home/kiduser/.bash_profile
chown -R kiduser:kiduser /home/kiduser/.ipython 2>/dev/null || true

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
echo_info "2. Or login as kiduser on TTY1"
echo ""
echo_warn "Remember to change the default password!"
echo_warn "Default credentials: kiduser / purplecomputer"
echo ""
echo_info "Parent escape: Ctrl+Alt+P"
