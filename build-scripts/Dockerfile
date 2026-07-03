# Build environment for Purple Computer
# Architecture: Live boot + optional install
FROM ubuntu:24.04

# Override to a faster mirror only when it's healthy; archive.ubuntu.com is the reliable default.
ARG APT_MIRROR=http://archive.ubuntu.com
RUN sed -i "s|http://archive.ubuntu.com|${APT_MIRROR}|g" /etc/apt/sources.list.d/ubuntu.sources && \
    apt-get update && \
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
