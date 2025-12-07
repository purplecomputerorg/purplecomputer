FROM debian:bookworm

# Install build dependencies
RUN apt-get update && apt-get install -y \
    fai-server \
    fai-setup-storage \
    fai-client \
    debootstrap \
    squashfs-tools \
    live-boot \
    live-boot-doc \
    syslinux \
    syslinux-common \
    isolinux \
    xorriso \
    genisoimage \
    grub-pc-bin \
    grub-efi-amd64-bin \
    grub-efi-ia32-bin \
    mtools \
    dosfstools \
    dpkg-dev \
    apt-utils \
    reprepro \
    rsync \
    wget \
    curl \
    git \
    vim \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create build directories
RUN mkdir -p /srv/fai/{config,nfsroot} \
    /opt/purple-installer/{local-repo,iso-build,output}

# Set working directory
WORKDIR /build

# Entry point will be the build scripts
CMD ["/bin/bash"]
