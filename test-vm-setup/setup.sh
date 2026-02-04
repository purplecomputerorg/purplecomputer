#!/bin/bash
# Purple Computer Test VM Setup
# Run this after fresh Ubuntu Server install
#
# This is for VM-based testing only. Not for production.
# For production builds, see build-scripts/
#
# Safe to re-run: skips steps that are already done.

set -e

echo "=== Purple Computer Test VM Setup ==="
echo ""

# Check we're on Linux
if [[ "$(uname)" != "Linux" ]]; then
    echo "Error: This script requires Linux."
    exit 1
fi

# Check architecture
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" && "$ARCH" != "x86_64" ]]; then
    echo "Warning: Unexpected architecture: $ARCH"
fi

echo "Architecture: $ARCH"
echo ""

# --- Helper: install packages only if any are missing ---
install_if_needed() {
    local missing=()
    for pkg in "$@"; do
        if ! dpkg -s "$pkg" &>/dev/null; then
            missing+=("$pkg")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "  Installing: ${missing[*]}"
        sudo apt install -y "${missing[@]}"
    else
        echo "  All packages already installed, skipping."
    fi
}

# Update package lists (always, so install_if_needed can find new packages)
echo "[1/7] Updating package lists..."
sudo apt update -qq

# Install base packages
echo "[2/7] Base packages..."
install_if_needed \
    git make unzip curl fontconfig \
    python3 python3-venv python3-pip \
    build-essential gcc python3-dev

# Install X11 stack
echo "[3/7] X11, window managers, and terminal..."
install_if_needed \
    xorg xinit xauth x11-xserver-utils \
    xserver-xorg-core xserver-xorg-input-all \
    libgl1-mesa-dri \
    matchbox-window-manager dwm feh \
    alacritty xterm \
    libxkbcommon-x11-0 libgl1 libegl1 libgles2 \
    ncurses-term unclutter xkbset evtest

# Install audio (pygame/sound)
echo "[4/7] Audio and SDL libraries..."
install_if_needed \
    pulseaudio alsa-utils \
    libsdl2-2.0-0 libsdl2-mixer-2.0-0 \
    libsdl2-image-2.0-0 libsdl2-ttf-2.0-0

# Install fonts
echo "[5/7] Fonts..."
install_if_needed fontconfig fonts-noto-color-emoji

FONT_DIR="/usr/share/fonts/truetype/jetbrains-mono-nerd"
if [ ! -d "$FONT_DIR" ]; then
    echo "  Downloading JetBrainsMono Nerd Font..."
    sudo mkdir -p "$FONT_DIR"
    curl -fsSL https://github.com/ryanoasis/nerd-fonts/releases/download/v3.1.1/JetBrainsMono.zip -o /tmp/JetBrainsMono.zip
    sudo unzip -o /tmp/JetBrainsMono.zip -d "$FONT_DIR"
    rm /tmp/JetBrainsMono.zip
    sudo fc-cache -fv
else
    echo "  JetBrainsMono Nerd Font already installed, skipping."
fi

# --- System configuration ---
echo "[6/7] System configuration..."

# VirtioFS support (Apple Virtualization file sharing)
if ! grep -q "^virtiofs" /etc/initramfs-tools/modules 2>/dev/null; then
    echo "  Enabling virtiofs in initramfs..."
    echo "virtiofs" | sudo tee -a /etc/initramfs-tools/modules > /dev/null
    sudo update-initramfs -u
fi

# Mount point for shared folder
sudo mkdir -p /mnt/share
if ! grep -q "virtiofs" /etc/fstab 2>/dev/null; then
    echo "share /mnt/share virtiofs rw,nofail 0 0" | sudo tee -a /etc/fstab > /dev/null
fi

# Input group for evdev access
if ! id -nG "$USER" | grep -qw input; then
    echo "  Adding $USER to input group..."
    sudo usermod -aG input "$USER"
fi

# uinput permissions
UINPUT_RULE='KERNEL=="uinput", GROUP="input", MODE="0660"'
UINPUT_FILE="/etc/udev/rules.d/99-purple-uinput.rules"
if [ ! -f "$UINPUT_FILE" ] || ! grep -qF "$UINPUT_RULE" "$UINPUT_FILE"; then
    echo "$UINPUT_RULE" | sudo tee "$UINPUT_FILE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
fi

# X permissions for non-root users
sudo tee /etc/X11/Xwrapper.config > /dev/null << 'XWRAP'
allowed_users=anybody
needs_root_rights=yes
XWRAP

# --- X11 startup and helper scripts ---
echo "[7/7] Creating X11 startup files..."

# .xinitrc
cat > ~/.xinitrc << 'XINITRC'
#!/bin/bash
# Purple Computer Test VM X11 Startup

# Log for debugging
exec >> /tmp/xinitrc.log 2>&1
echo "=== $(date) ==="

sleep 1

# Disable screen blanking
xset s off -dpms s noblank b off

# Disable XKB accessibility (avoids accidental sticky keys)
command -v xkbset &>/dev/null && xkbset -a

# Keyboard repeat
xset r rate 300 30

# Hide cursor when idle
command -v unclutter &>/dev/null && unclutter -idle 2 &

# Purple background
xsetroot -solid "#2d1b4e"

# Window manager: WM=tiling for side-by-side (dwm), matchbox (default) for fullscreen
WM="${WM:-matchbox}"
echo "Starting WM: $WM"
if [ "$WM" = "tiling" ]; then
    dwm &
else
    matchbox-window-manager -use_titlebar no &
fi
sleep 0.5

# Launch Alacritty (user runs Purple manually)
exec alacritty
XINITRC
chmod +x ~/.xinitrc

# startx-tiling: launches X with i3 tiling WM
sudo tee /usr/local/bin/startx-tiling > /dev/null << 'STILING'
#!/bin/bash
# Start X with dwm tiling WM (for doodle_ai --human, image review, etc.)
# dwm shows all windows side-by-side automatically (master+stack layout)
WM=tiling exec startx
STILING
sudo chmod +x /usr/local/bin/startx-tiling

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Reboot:  sudo reboot"
echo "  2. Log into VM console (not SSH)"
echo "  3. Run:     startx"
echo "  4. Clone:   git clone https://github.com/purplecomputerorg/purplecomputer.git"
echo "  5. Setup:   cd purplecomputer && make setup"
echo "  6. Run:     make run"
echo ""
echo "For doodle AI human judging: startx-tiling (uses i3 tiling WM)"
echo ""
echo "Remember: SSH is for editing. Use VM console for testing keyboard."
echo ""
