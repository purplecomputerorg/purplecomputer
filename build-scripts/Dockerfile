# Build environment for PurpleOS installer (Ubuntu ISO Remaster architecture)
FROM ubuntu:24.04

# Install build tools for:
# - Golden image creation (debootstrap)
# - ISO remastering (squashfs-tools, xorriso)
# - No initramfs/casper building - we use Ubuntu's as-is
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    # Golden image building
    debootstrap \
    # ISO remastering
    squashfs-tools \
    xorriso \
    isolinux \
    syslinux-utils \
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
    # Download tools (for fetching Ubuntu ISO)
    wget \
    curl \
    unzip \
    # File sync
    rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
