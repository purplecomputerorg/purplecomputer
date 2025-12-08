# Minimal build environment for PurpleOS installer
FROM ubuntu:24.04

# Install only required build tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    debootstrap \
    xorriso \
    isolinux \
    syslinux-utils \
    grub-efi-amd64-bin \
    busybox-static \
    zstd \
    gdisk \
    parted \
    dosfstools \
    e2fsprogs \
    cpio \
    gzip \
    kpartx \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
