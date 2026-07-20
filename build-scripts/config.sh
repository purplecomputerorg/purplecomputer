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

# Human-readable list of the ISO files a build will produce, given current
# FAST_BUILD / PURPLE_WITH_BACKUP_ISO. Mirrors the naming in 01-remaster-iso.sh.
planned_iso_names() {
    local tag="" stem
    [ "${FAST_BUILD:-0}" = "1" ] && tag="-fast"
    stem="purple-installer-$(date +%Y%m%d)${tag}"
    echo "${stem}.iso  (standard)"
    [ "${PURPLE_WITH_BACKUP_ISO:-0}" = "1" ] && echo "${stem}.with-backup.iso  (standard + backup image, for shipped USBs)"
    echo "${stem}.debug.iso  (debug boot menu)"
    return 0
}
