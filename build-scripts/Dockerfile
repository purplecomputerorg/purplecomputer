# Build environment for PurpleOS installer (module-free architecture)
FROM ubuntu:24.04

# Install build tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    bc \
    bison \
    flex \
    libelf-dev \
    libssl-dev \
    debootstrap \
    xorriso \
    isolinux \
    syslinux-utils \
    grub-efi-amd64-bin \
    mtools \
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
