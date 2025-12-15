# Build environment for Purple Computer installer
# Architecture: Initramfs injection into Ubuntu Server ISO
FROM ubuntu:24.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    # Golden image building
    debootstrap \
    # ISO remastering
    xorriso \
    isolinux \
    syslinux-utils \
    # Initramfs manipulation
    initramfs-tools-core \
    cpio \
    # Bootloader tools (for golden image GRUB setup)
    grub-efi-amd64-bin \
    grub-pc-bin \
    mtools \
    # Disk utilities
    zstd \
    gdisk \
    parted \
    dosfstools \
    e2fsprogs \
    # Loop device support
    kpartx \
    # Download tools
    wget \
    curl \
    unzip \
    # File sync
    rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
