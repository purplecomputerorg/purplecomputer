#!/usr/bin/env bash
# Purple Computer Build Configuration
# Single source of truth for distribution settings

DIST_NAME="noble"
DIST_FULL="Ubuntu 24.04.3 LTS"
SECTIONS="main restricted universe multiverse"
ARCH="amd64"
UBUNTU_MIRROR="http://archive.ubuntu.com/ubuntu"

# Essential packages for nfsroot (installer environment)
# live-boot: Required for initramfs to boot from squashfs
# casper: Live system infrastructure
NFSROOT_PACKAGES="linux-image-generic,linux-firmware,live-boot,casper,systemd,lvm2,parted,e2fsprogs,ntfs-3g,grub-pc-bin,grub-efi-amd64-bin"

# Essential base packages (always needed)
BASE_PACKAGES="ubuntu-minimal base-files libc6 dpkg apt systemd udev"
