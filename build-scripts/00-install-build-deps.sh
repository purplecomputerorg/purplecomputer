#!/bin/bash
# Install all dependencies required to build Purple Computer installer
# Run this first on a Debian/Ubuntu build machine

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
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

install_dependencies() {
    log_info "Installing build dependencies..."

    apt-get update

    # Core FAI and build tools
    apt-get install -y \
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
        dosfstools

    # Repository management
    apt-get install -y \
        dpkg-dev \
        apt-utils \
        reprepro

    # Utilities
    apt-get install -y \
        rsync \
        wget \
        curl \
        git \
        vim

    log_info "All dependencies installed successfully."
}

create_directories() {
    log_info "Creating build directory structure..."

    mkdir -p /srv/fai/{config,nfsroot}
    mkdir -p /opt/purple-installer/{local-repo,iso-build,output}

    log_info "Directories created."
}

set_permissions() {
    log_info "Setting permissions..."

    # Make build scripts executable
    if [ -d "/home/tavi/purplecomputer/build-scripts" ]; then
        chmod +x /home/tavi/purplecomputer/build-scripts/*.sh
    fi

    log_info "Permissions set."
}

print_next_steps() {
    cat <<EOF

${GREEN}════════════════════════════════════════════════════════════${NC}
  Build Dependencies Installed Successfully!
${GREEN}════════════════════════════════════════════════════════════${NC}

Next steps:

1. Create local repository:
   ${YELLOW}sudo ./01-create-local-repo.sh${NC}

2. Build FAI nfsroot:
   ${YELLOW}sudo ./02-build-fai-nfsroot.sh${NC}

3. Build bootable ISO:
   ${YELLOW}sudo ./03-build-iso.sh${NC}

All scripts are located in: /home/tavi/purplecomputer/build-scripts/

For more information, see: /home/tavi/purplecomputer/fai-config/README.md

${GREEN}════════════════════════════════════════════════════════════${NC}

EOF
}

main() {
    log_info "Installing Purple Computer build dependencies..."

    check_root
    install_dependencies
    create_directories
    set_permissions
    print_next_steps

    log_info "Setup complete!"
}

main "$@"
