#!/usr/bin/env bash
# Purple Computer Build Configuration

# Paths
INSTALLER_BASE="/opt/purple-installer"
BUILD_DIR="$INSTALLER_BASE/build"
OUTPUT_DIR="$INSTALLER_BASE/output"
TEST_DIR="$INSTALLER_BASE/test-results"

DIST_NAME="noble"
DIST_FULL="Ubuntu 24.04.1 LTS"
ARCH="amd64"

# Ubuntu Server ISO (initramfs injection architecture)
UBUNTU_ISO_URL="https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-24.04.1-live-server-amd64.iso"

# Essential base packages for golden image (the installed system)
GOLDEN_PACKAGES="linux-image-generic grub-efi-amd64 systemd sudo"
