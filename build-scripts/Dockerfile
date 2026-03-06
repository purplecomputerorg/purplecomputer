# Build environment for Purple Computer
# Architecture: Live boot + optional install
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
    squashfs-tools \
    # Loop device support
    kpartx \
    # Download tools
    wget \
    curl \
    unzip \
    # File sync
    rsync \
    # Alacritty build deps (0.16.1 built from source for emoji width fix)
    cmake \
    g++ \
    pkg-config \
    libfontconfig1-dev \
    libxcb-xfixes0-dev \
    libxkbcommon-dev \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
