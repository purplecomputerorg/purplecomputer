FROM ubuntu:noble

# Install build dependencies
RUN apt-get update && apt-get install -y \
    fai-server \
    fai-setup-storage \
    mmdebstrap \
    apt-utils \
    squashfs-tools \
    live-boot \
    syslinux \
    isolinux \
    xorriso \
    grub-pc-bin \
    grub-efi-amd64-bin \
    mtools \
    && rm -rf /var/lib/apt/lists/*

# Create build directories
RUN mkdir -p /srv/fai/{config,nfsroot} \
    /opt/purple-installer/{local-repo,iso-build,output}

# Set working directory
WORKDIR /build

# Entry point will be the build scripts
CMD ["/bin/bash"]
