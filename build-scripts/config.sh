#!/usr/bin/env bash
# Purple Computer Build Configuration
# Single source of truth for distribution settings
#
# ARCHITECTURE: Ubuntu ISO Remaster
# - We take an official Ubuntu Server ISO as a black box
# - We do NOT build initramfs, casper, or the boot stack
# - We just add our payload and disable Subiquity

DIST_NAME="noble"
DIST_FULL="Ubuntu 24.04.1 LTS"
ARCH="amd64"

# Ubuntu Server ISO to use as base (downloaded during build)
UBUNTU_ISO_URL="https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-24.04.1-live-server-amd64.iso"

# Essential base packages for golden image (the installed system)
GOLDEN_PACKAGES="linux-image-generic grub-efi-amd64 systemd sudo"
