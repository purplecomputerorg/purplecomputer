#!/bin/bash
# Build FAI nfsroot (installation environment)
# This creates the live environment used during installation

set -e

# Configuration
FAI_CONFIG_DIR="/home/tavi/purplecomputer/fai-config"
FAI_BASE="/srv/fai"
NFSROOT="${FAI_BASE}/nfsroot"
MIRROR_DIR="/opt/purple-installer/local-repo/mirror"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

install_fai() {
    log_info "Installing FAI packages..."

    apt-get update
    apt-get install -y \
        fai-server \
        fai-setup-storage \
        debootstrap \
        squashfs-tools \
        live-boot \
        syslinux \
        isolinux \
        xorriso \
        grub-pc-bin \
        grub-efi-amd64-bin \
        mtools

    log_info "FAI packages installed."
}

setup_fai_config() {
    log_info "Setting up FAI configuration..."

    # Create FAI directory structure
    mkdir -p "${FAI_BASE}"
    mkdir -p "${FAI_BASE}/config"
    mkdir -p "${FAI_BASE}/nfsroot"

    # Copy our configuration
    log_info "Copying FAI configuration from ${FAI_CONFIG_DIR}..."
    cp -r "${FAI_CONFIG_DIR}"/* "${FAI_BASE}/config/"

    # Ensure scripts are executable
    find "${FAI_BASE}/config/scripts" -type f -exec chmod +x {} \;
    find "${FAI_BASE}/config/hooks" -type f -exec chmod +x {} \;
    find "${FAI_BASE}/config/class" -type f -exec chmod +x {} \;

    log_info "FAI configuration installed."
}

configure_fai() {
    log_info "Configuring FAI..."

    # Create main FAI configuration
    cat > /etc/fai/fai.conf <<EOF
# Purple Computer FAI Configuration

# FAI configuration space
FAI_CONFIG_SRC="file:///srv/fai/config"

# Installation logs
LOGUSER="fai"
FAI_LOGPROTO="file:///"

# Server settings
FAI_DEBOOTSTRAP="bookworm file:${MIRROR_DIR}"

# Classes to always apply
FAI_CLASSES="FAIBASE DEBIAN AMD64 PURPLECOMPUTER LAPTOP MINIMAL_X"

# Default action
FAI_ACTION="install"

# Flags
FAI_FLAGS="verbose"
EOF

    # Configure make-fai-nfsroot
    cat > /etc/fai/make-fai-nfsroot.conf <<EOF
# Purple Computer nfsroot configuration

# Use local mirror
FAI_DEBOOTSTRAP="noble file://${MIRROR_DIR}"

# Architecture
FAI_DEBOOTSTRAP_OPTS="--arch amd64"

# Kernel package
KERNELPACKAGE="linux-image-amd64"

# Additional packages for nfsroot
NFSROOT_PACKAGES="
    systemd-sysv
    live-boot
    live-boot-initramfs-tools
    lvm2
    parted
    gdisk
    dosfstools
    e2fsprogs
    btrfs-progs
    ntfs-3g
    grub-pc
    grub-efi-amd64
    firmware-linux-free
    ssh
    vim
    "

# NFS root location
NFSROOT="${NFSROOT}"

# Make nfsroot read-write during installation
FAI_NFSROOT_MODE="666"
EOF

    log_info "FAI configured."
}

setup_local_repository() {
    log_info "Setting up local repository access..."

    # Create sources.list for FAI build environment
    cat > /etc/apt/sources.list.d/purple-local.list <<EOF
# Purple Computer local repository
deb [trusted=yes] file://${MIRROR_DIR} bookworm main contrib non-free non-free-firmware
EOF

    # Update apt cache
    apt-get update

    log_info "Local repository configured."
}

build_nfsroot() {
    log_info "Building FAI nfsroot (this will take several minutes)..."

    # Clean old nfsroot if exists
    if [ -d "$NFSROOT" ]; then
        log_warn "Removing old nfsroot..."
        rm -rf "$NFSROOT"
    fi

    # Build nfsroot
    fai-make-nfsroot -v

    if [ $? -eq 0 ]; then
        log_info "FAI nfsroot built successfully at: ${NFSROOT}"
    else
        log_error "Failed to build FAI nfsroot"
        exit 1
    fi
}

customize_nfsroot() {
    log_info "Customizing nfsroot..."

    # Copy local repository list into nfsroot
    mkdir -p "${NFSROOT}/etc/apt/sources.list.d"
    cat > "${NFSROOT}/etc/apt/sources.list.d/purple-local.list" <<EOF
deb [trusted=yes] file:///media/purple-repo bookworm main contrib non-free non-free-firmware
EOF

    # Disable online repositories in nfsroot
    if [ -f "${NFSROOT}/etc/apt/sources.list" ]; then
        sed -i 's/^deb /#deb /g' "${NFSROOT}/etc/apt/sources.list"
    fi

    # Add Purple Computer branding
    cat > "${NFSROOT}/etc/issue" <<'EOF'
Purple Computer Installation Environment
Fully Automatic Installation (FAI)

EOF

    log_info "Nfsroot customization complete."
}

main() {
    log_info "Starting FAI nfsroot build..."

    check_root
    install_fai
    setup_fai_config
    configure_fai
    setup_local_repository
    build_nfsroot
    customize_nfsroot

    log_info ""
    log_info "FAI nfsroot build complete!"
    log_info "Nfsroot location: ${NFSROOT}"
    log_info ""
    log_info "Next step: Run 03-build-iso.sh to create bootable ISO"
}

main "$@"
