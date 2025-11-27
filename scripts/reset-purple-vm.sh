#!/bin/bash
# Purple Computer VM Reset Script
# Wipes user state and launches fresh Purple Computer environment
#
# Usage: Copy this script to ~/reset-purple.sh inside your VM
#        chmod +x ~/reset-purple.sh
#        ./reset-purple.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[✓]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

echo_error() {
    echo -e "${RED}[✗]${NC} $1"
}

echo_step() {
    echo -e "${PURPLE}[→]${NC} $1"
}

clear
echo "╔════════════════════════════════════════════════════════╗"
echo "║  Purple Computer VM Reset - Fresh User Environment    ║"
echo "╔════════════════════════════════════════════════════════╗"
echo ""

# Configuration
REPO_PATH="/mnt/purple"
HOME_DIR="$HOME"
PURPLE_DIR="$HOME_DIR/.purple"
IPYTHON_DIR="$HOME_DIR/.ipython"
VENV_DIR="$HOME_DIR/.purple_venv"

# Step 1: Check repo is accessible
echo_step "Checking repository mount..."
if [ ! -d "$REPO_PATH" ]; then
    echo_error "Repository not mounted at $REPO_PATH"
    echo "Please ensure the shared folder is mounted."
    echo ""
    echo "UTM: Check VM settings → Sharing"
    echo "VirtualBox: Check Devices → Shared Folders"
    exit 1
fi

if [ ! -f "$REPO_PATH/purple_repl/repl.py" ]; then
    echo_error "Purple Computer files not found in $REPO_PATH"
    echo "Please check the shared folder configuration."
    exit 1
fi

echo_info "Repository found at $REPO_PATH"

# Step 2: Wipe existing Purple Computer state
echo_step "Wiping existing Purple Computer state..."

if [ -d "$PURPLE_DIR" ]; then
    rm -rf "$PURPLE_DIR"
    echo_info "Removed $PURPLE_DIR"
fi

if [ -d "$IPYTHON_DIR" ]; then
    rm -rf "$IPYTHON_DIR"
    echo_info "Removed $IPYTHON_DIR"
fi

# Step 3: Recreate directory structure
echo_step "Creating fresh directory structure..."
mkdir -p "$PURPLE_DIR/packs"
mkdir -p "$PURPLE_DIR/modes"
mkdir -p "$IPYTHON_DIR/profile_default/startup"
echo_info "Created Purple Computer directories"

# Step 4: Copy Purple REPL files
echo_step "Copying Purple REPL files..."
cp -r "$REPO_PATH/purple_repl"/*.py "$PURPLE_DIR/" 2>/dev/null || true
cp -r "$REPO_PATH/purple_repl/modes" "$PURPLE_DIR/" 2>/dev/null || true

if [ -d "$REPO_PATH/purple_repl/startup" ]; then
    cp "$REPO_PATH/purple_repl/startup"/*.py "$IPYTHON_DIR/profile_default/startup/"
    echo_info "Copied IPython startup files"
fi

echo_info "Copied REPL files"

# Step 5: Setup Python virtual environment
echo_step "Setting up Python virtual environment..."

if [ -d "$VENV_DIR" ]; then
    echo_warn "Removing existing virtual environment..."
    rm -rf "$VENV_DIR"
fi

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo_info "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet ipython colorama termcolor packaging traitlets simple-term-menu

echo_info "Virtual environment ready"

# Step 6: Install example packs
echo_step "Installing example packs..."

if [ -f "$REPO_PATH/packs/core-emoji.purplepack" ]; then
    cd "$PURPLE_DIR"
    python << 'EOFPYTHON'
from pack_manager import PackManager, get_registry
from pathlib import Path
import os

repo_path = os.environ.get('REPO_PATH', '/mnt/purple')
purple_dir = os.environ.get('PURPLE_DIR')

packs_dir = Path(purple_dir) / 'packs'
registry = get_registry()
manager = PackManager(packs_dir, registry)

# Install core emoji pack
pack_path = Path(repo_path) / 'packs' / 'core-emoji.purplepack'
if pack_path.exists():
    success, msg = manager.install_pack_from_file(pack_path)
    if success:
        print("✓ Installed core-emoji pack")
    else:
        print(f"! Failed to install core-emoji: {msg}")

# Install education basics pack
pack_path = Path(repo_path) / 'packs' / 'education-basics.purplepack'
if pack_path.exists():
    success, msg = manager.install_pack_from_file(pack_path)
    if success:
        print("✓ Installed education-basics pack")
    else:
        print(f"! Failed to install education-basics: {msg}")

# Install music mode pack
pack_path = Path(repo_path) / 'packs' / 'music_mode_basic.purplepack'
if pack_path.exists():
    success, msg = manager.install_pack_from_file(pack_path)
    if success:
        print("✓ Installed music_mode_basic pack")
    else:
        print(f"! Failed to install music_mode_basic: {msg}")
EOFPYTHON
    echo_info "Packs installed"
else
    echo_warn "No pre-built packs found. Building them..."
    cd "$REPO_PATH"
    source "$VENV_DIR/bin/activate"

    if [ -d "$REPO_PATH/packs/core-emoji" ]; then
        python scripts/build_pack.py packs/core-emoji packs/core-emoji.purplepack
        python scripts/build_pack.py packs/education-basics packs/education-basics.purplepack
        python scripts/build_pack.py packs/music_mode_basic packs/music_mode_basic.purplepack 2>/dev/null || true
        echo_info "Built packs"

        # Now install them
        cd "$PURPLE_DIR"
        python << 'EOFPYTHON2'
from pack_manager import PackManager, get_registry
from pathlib import Path
import os

repo_path = os.environ.get('REPO_PATH', '/mnt/purple')
purple_dir = os.environ.get('PURPLE_DIR')

packs_dir = Path(purple_dir) / 'packs'
registry = get_registry()
manager = PackManager(packs_dir, registry)

for pack_name in ['core-emoji', 'education-basics', 'music_mode_basic']:
    pack_path = Path(repo_path) / 'packs' / f'{pack_name}.purplepack'
    if pack_path.exists():
        success, msg = manager.install_pack_from_file(pack_path)
        if success:
            print(f"✓ Installed {pack_name}")
EOFPYTHON2
    fi
fi

# Step 7: Launch Purple Computer in Kitty
echo ""
echo_info "Fresh environment ready!"
echo ""
echo_step "Launching Purple Computer in Kitty..."
sleep 1

# Launch kitty with Purple Computer
cd "$PURPLE_DIR"
export HOME="$HOME_DIR"
export IPYTHONDIR="$IPYTHON_DIR"

# Check if kitty is available
if command -v kitty &> /dev/null; then
    # Launch in kitty
    kitty --title "Purple Computer" --start-as=maximized bash -c "
        source '$VENV_DIR/bin/activate'
        cd '$PURPLE_DIR'
        python repl.py
        read -p 'Press Enter to close...'
    "
else
    # Fallback to current terminal
    echo_warn "Kitty not found, launching in current terminal..."
    source "$VENV_DIR/bin/activate"
    cd "$PURPLE_DIR"
    python repl.py
fi

echo ""
echo_info "Purple Computer session ended."
echo ""
