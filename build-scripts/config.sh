#!/usr/bin/env bash
# Purple Computer Build Configuration
# Single source of truth for distribution settings
#
# MODULE-FREE ARCHITECTURE NOTES:
# - Custom kernel with built-in drivers (no runtime modules)
# - No live-boot/casper needed (direct USB boot)
# - Simplified installer environment

DIST_NAME="noble"
DIST_FULL="Ubuntu 24.04.3 LTS"
SECTIONS="main restricted universe multiverse"
ARCH="amd64"
UBUNTU_MIRROR="http://archive.ubuntu.com/ubuntu"

# Custom kernel configuration
KERNEL_VERSION="6.8.12"              # Upstream kernel version
KERNEL_MAJOR="6.x"                   # Kernel.org download path

# Essential packages for installer environment (simplified, no live-boot)
# Module-free architecture eliminates need for:
# - linux-modules-* (drivers built into kernel)
# - live-boot, casper (no live system)
INSTALLER_PACKAGES="systemd,lvm2,parted,e2fsprogs,ntfs-3g,grub-pc-bin,grub-efi-amd64-bin,zstd,gdisk,dosfstools"

# Essential base packages (always needed)
BASE_PACKAGES="ubuntu-minimal base-files libc6 dpkg apt systemd udev"
