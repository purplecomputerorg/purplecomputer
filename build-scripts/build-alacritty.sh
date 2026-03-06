#!/usr/bin/env bash
# Build Alacritty 0.16.1 from source
#
# Ubuntu 24.04 ships Alacritty 0.12.2 which has broken emoji width handling.
# Alacritty 0.16.0+ uses unicode-width 0.2.0 which correctly treats
# emoji presentation sequences (base char + U+FE0F) as 2 cells wide.
#
# Usage:
#   ./build-alacritty.sh              # Build and install to /usr/local/bin
#   ./build-alacritty.sh /custom/path # Build and install to custom path
#   KEEP_RUST=1 ./build-alacritty.sh  # Don't remove Rust toolchain after build
#
# Can run as root (golden image build) or as user with sudo (test VM).

set -e

ALACRITTY_VERSION="0.16.1"
INSTALL_DIR="${1:-/usr/local/bin}"
CARGO_HOME="${CARGO_HOME:-/tmp/cargo-alacritty}"
RUSTUP_HOME="${RUSTUP_HOME:-/tmp/rustup-alacritty}"

export CARGO_HOME RUSTUP_HOME

GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[alacritty]${NC} $1"; }

# Check if already installed at correct version
if [ -x "$INSTALL_DIR/alacritty" ]; then
    INSTALLED_VER=$("$INSTALL_DIR/alacritty" --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
    if [ "$INSTALLED_VER" = "$ALACRITTY_VERSION" ]; then
        log_info "Alacritty $ALACRITTY_VERSION already installed at $INSTALL_DIR/alacritty"
        exit 0
    fi
    log_info "Found Alacritty $INSTALLED_VER, upgrading to $ALACRITTY_VERSION..."
fi

# Install build dependencies
log_info "Installing build dependencies..."
BUILD_DEPS="cmake g++ pkg-config libfontconfig1-dev libxcb-xfixes0-dev libxkbcommon-dev python3"
if command -v sudo &>/dev/null && [ "$EUID" -ne 0 ]; then
    sudo apt-get install -y $BUILD_DEPS
else
    apt-get install -y $BUILD_DEPS
fi

# Install Rust if not present
if ! command -v "$CARGO_HOME/bin/cargo" &>/dev/null && ! command -v cargo &>/dev/null; then
    log_info "Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --no-modify-path
fi

# Use our cargo
if [ -x "$CARGO_HOME/bin/cargo" ]; then
    export PATH="$CARGO_HOME/bin:$PATH"
fi

log_info "Building Alacritty $ALACRITTY_VERSION (this takes a few minutes)..."
cargo install alacritty --version "$ALACRITTY_VERSION" --root "$CARGO_HOME"

# Install binary
log_info "Installing to $INSTALL_DIR..."
if [ "$EUID" -ne 0 ] && [ ! -w "$INSTALL_DIR" ]; then
    sudo cp "$CARGO_HOME/bin/alacritty" "$INSTALL_DIR/alacritty"
else
    cp "$CARGO_HOME/bin/alacritty" "$INSTALL_DIR/alacritty"
fi

# Clean up Rust toolchain unless told to keep it
if [ "${KEEP_RUST:-0}" != "1" ]; then
    log_info "Cleaning up Rust toolchain..."
    rm -rf "$CARGO_HOME" "$RUSTUP_HOME"
fi

# Verify
FINAL_VER=$("$INSTALL_DIR/alacritty" --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
log_info "Alacritty $FINAL_VER installed at $INSTALL_DIR/alacritty"
