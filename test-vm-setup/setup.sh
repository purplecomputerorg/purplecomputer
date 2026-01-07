#!/bin/bash
# Purple Computer Test VM Setup
# Run this after fresh Ubuntu Server install
#
# This is for VM-based testing only. Not for production.
# For production builds, see build-scripts/

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

# Update package lists
echo "[1/6] Updating packages..."
sudo apt update

# Install base packages
echo "[2/6] Installing base packages..."
sudo apt install -y \
    git \
    make \
    unzip \
    curl \
    fontconfig \
    python3 \
    python3-venv \
    python3-pip \
    build-essential \
    gcc \
    python3-dev

# Install X11 stack
echo "[3/6] Installing X11 and Alacritty..."
sudo apt install -y \
    xorg \
    xinit \
    xauth \
    x11-xserver-utils \
    xserver-xorg-core \
    xserver-xorg-input-all \
    libgl1-mesa-dri \
    matchbox-window-manager \
    alacritty \
    xterm \
    libxkbcommon-x11-0 \
    libgl1 \
    libegl1 \
    libgles2 \
    ncurses-term \
    unclutter \
    xkbset

# Install audio (pygame/sound)
echo "[3.5/6] Installing audio and SDL libraries..."
sudo apt install -y \
    pulseaudio \
    alsa-utils \
    libsdl2-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-ttf-2.0-0

# Install fonts
echo "[3.6/6] Installing fonts..."
sudo apt install -y \
    fontconfig \
    fonts-noto-color-emoji

# Install JetBrainsMono Nerd Font (for UI icons)
FONT_DIR="/usr/share/fonts/truetype/jetbrains-mono-nerd"
if [ ! -d "$FONT_DIR" ]; then
    echo "  Downloading JetBrainsMono Nerd Font..."
    sudo mkdir -p "$FONT_DIR"
    curl -fsSL https://github.com/ryanoasis/nerd-fonts/releases/download/v3.1.1/JetBrainsMono.zip -o /tmp/JetBrainsMono.zip
    sudo unzip -o /tmp/JetBrainsMono.zip -d "$FONT_DIR"
    rm /tmp/JetBrainsMono.zip
    sudo fc-cache -fv
fi

# Install evtest for debugging
sudo apt install -y evtest

# Set up VirtioFS support (Apple Virtualization file sharing)
# This adds virtiofs to initramfs so it loads early enough to mount shares
if ! grep -q "^virtiofs" /etc/initramfs-tools/modules 2>/dev/null; then
    echo "  Enabling virtiofs in initramfs..."
    echo "virtiofs" | sudo tee -a /etc/initramfs-tools/modules > /dev/null
    sudo update-initramfs -u
fi

# Create mount point for shared folder
sudo mkdir -p /mnt/share
# Add fstab entry (won't fail if share doesn't exist)
if ! grep -q "virtiofs" /etc/fstab 2>/dev/null; then
    echo "share /mnt/share virtiofs rw,nofail 0 0" | sudo tee -a /etc/fstab > /dev/null
fi

# Add user to input group
echo "[4/6] Configuring input permissions..."
sudo usermod -aG input "$USER"

# Set up uinput permissions (persistent)
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-purple-uinput.rules > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

# Fix X permissions for non-root users
echo "[5/6] Configuring X permissions..."
sudo tee /etc/X11/Xwrapper.config > /dev/null << 'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF

# Create .xinitrc
echo "[6/6] Creating .xinitrc..."
cat > ~/.xinitrc << 'EOF'
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

# Window manager
matchbox-window-manager -use_titlebar no &
sleep 0.5

# Launch Alacritty (user runs Purple manually)
exec alacritty
EOF
chmod +x ~/.xinitrc

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
echo "Remember: SSH is for editing. Use VM console for testing keyboard."
echo ""
