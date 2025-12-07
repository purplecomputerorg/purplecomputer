#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

REPO_BASE="/opt/purple-installer/local-repo"
MIRROR_DIR="${REPO_BASE}/mirror"
CACHE_DIR="${REPO_BASE}/cache"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# STAGE 1: Download complete dependency closure with debootstrap
download_base_system() {
    log_info "Stage 1: Downloading complete dependency closure..."

    local TEMP_ROOT="${CACHE_DIR}/temp-root"
    local DEB_CACHE="${CACHE_DIR}/debs"
    mkdir -p "${MIRROR_DIR}/pool"
    mkdir -p "$DEB_CACHE"
    rm -rf "$TEMP_ROOT"

    # Use debootstrap with --make-tarball to download all .debs
    # debootstrap downloads ALL packages including Essential ones
    log_info "Downloading base system with debootstrap..."
    debootstrap \
        --arch=amd64 \
        --variant=minbase \
        --components=main,restricted,universe,multiverse \
        --include="${NFSROOT_PACKAGES}" \
        --download-only \
        "${DIST_NAME}" \
        "$TEMP_ROOT" \
        "${UBUNTU_MIRROR}"

    # Copy all downloaded .debs to pool
    log_info "Copying .debs to pool..."
    find "$TEMP_ROOT/var/cache/apt/archives" -name "*.deb" -exec cp {} "${MIRROR_DIR}/pool/" \;

    rm -rf "$TEMP_ROOT"
    log_info "Downloaded .debs: $(ls -1 ${MIRROR_DIR}/pool/*.deb 2>/dev/null | wc -l)"
}

# Add Purple-specific packages to pool
add_purple_packages() {
    log_info "Adding Purple-specific packages..."

    # Collect from FAI configs
    local pkg_list="${CACHE_DIR}/packages.list"
    > "$pkg_list"

    for config in /home/tavi/purplecomputer/fai-config/package_config/*; do
        grep -v '^#\|^PACKAGES\|^$' "$config" | awk '{print $1}' >> "$pkg_list"
    done

    sort -u "$pkg_list" -o "$pkg_list"
    local PURPLE_PKGS=$(tr '\n' ',' < "$pkg_list" | sed 's/,$//')
    log_info "Purple packages to add: $(wc -l < $pkg_list)"

    # Use debootstrap again to download Purple packages with same versions
    local TEMP_ROOT2="${CACHE_DIR}/temp-root2"
    rm -rf "$TEMP_ROOT2"

    debootstrap \
        --arch=amd64 \
        --variant=minbase \
        --components=main,restricted,universe,multiverse \
        --include="${PURPLE_PKGS}" \
        --download-only \
        "${DIST_NAME}" \
        "$TEMP_ROOT2" \
        "${UBUNTU_MIRROR}"

    # Copy Purple package .debs to pool
    find "$TEMP_ROOT2/var/cache/apt/archives" -name "*.deb" -exec cp {} "${MIRROR_DIR}/pool/" \;
    rm -rf "$TEMP_ROOT2"

    log_info "Total packages in pool: $(ls -1 ${MIRROR_DIR}/pool/*.deb 2>/dev/null | wc -l)"
}

# STAGE 2: Build proper offline repository
create_repository() {
    log_info "Stage 2: Building offline repository metadata..."

    mkdir -p "${MIRROR_DIR}/dists/${DIST_NAME}/main/binary-${ARCH}"
    cd "$MIRROR_DIR"

    # Generate Packages file with dpkg-scanpackages
    dpkg-scanpackages pool > "dists/${DIST_NAME}/main/binary-${ARCH}/Packages"
    gzip -9c "dists/${DIST_NAME}/main/binary-${ARCH}/Packages" > "dists/${DIST_NAME}/main/binary-${ARCH}/Packages.gz"

    # Generate Release file with hashes using apt-ftparchive
    cat > /tmp/apt-release.conf <<EOF
APT::FTPArchive::Release::Origin "Purple Computer";
APT::FTPArchive::Release::Label "PurpleOS Offline";
APT::FTPArchive::Release::Suite "${DIST_NAME}";
APT::FTPArchive::Release::Codename "${DIST_NAME}";
APT::FTPArchive::Release::Architectures "${ARCH}";
APT::FTPArchive::Release::Components "main";
APT::FTPArchive::Release::Description "${DIST_FULL} Offline";
EOF

    apt-ftparchive -c /tmp/apt-release.conf release "dists/${DIST_NAME}" > "dists/${DIST_NAME}/Release"

    log_info "Repository created at: ${MIRROR_DIR}"
}

# Main
main() {
    log_info "Creating PurpleOS offline repository using mmdebstrap"
    log_info "Distribution: ${DIST_FULL} (${DIST_NAME})"

    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi

    mkdir -p "$CACHE_DIR"

    download_base_system
    add_purple_packages
    create_repository

    log_info ""
    log_info "✓ Offline repository ready"
    log_info "  Location: ${MIRROR_DIR}"
    log_info "  Packages: $(ls -1 ${MIRROR_DIR}/pool/*.deb 2>/dev/null | wc -l)"
    log_info "  Size: $(du -sh ${MIRROR_DIR} | cut -f1)"
}

main
