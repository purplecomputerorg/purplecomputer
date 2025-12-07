#!/bin/bash
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

# Use mmdebstrap to download complete base system (Docker-safe)
download_base_system() {
    log_info "Downloading complete base system with mmdebstrap..."
    log_info "This gets ALL dependencies (~500MB)"

    local TEMP_ROOT="${CACHE_DIR}/temp-root"
    mkdir -p "${CACHE_DIR}/base-downloads"
    rm -rf "$TEMP_ROOT"

    # Build to temp directory - customize-hook copies .debs AFTER apt downloads
    mmdebstrap \
        --mode=unshare \
        --variant=minbase \
        --architecture=amd64 \
        --components=main,restricted,universe,multiverse \
        --include="${NFSROOT_PACKAGES}" \
        --aptopt='APT::Install-Recommends "false"' \
        --aptopt='APT::Install-Suggests "false"' \
        --customize-hook='cp -v "$1"/var/cache/apt/archives/*.deb '"${CACHE_DIR}/base-downloads/"' || true' \
        "${DIST_NAME}" \
        "$TEMP_ROOT" \
        "${UBUNTU_MIRROR}"

    # Clean up temp root
    rm -rf "$TEMP_ROOT"

    log_info "Base packages: $(ls -1 ${CACHE_DIR}/base-downloads/*.deb 2>/dev/null | wc -l)"
}

# Add Purple-specific packages
add_purple_packages() {
    log_info "Downloading Purple-specific packages..."

    # Collect from FAI configs
    local pkg_list="${CACHE_DIR}/packages.list"
    > "$pkg_list"

    for config in /home/tavi/purplecomputer/fai-config/package_config/*; do
        grep -v '^#\|^PACKAGES\|^$' "$config" | awk '{print $1}' >> "$pkg_list"
    done

    sort -u "$pkg_list" -o "$pkg_list"
    log_info "Purple packages to add: $(wc -l < $pkg_list)"

    # Download Purple packages using apt-get download
    mkdir -p "${CACHE_DIR}/purple-downloads"
    cd "${CACHE_DIR}/purple-downloads"

    apt-get update
    xargs -a "$pkg_list" apt-get download 2>/dev/null || true

    log_info "Purple packages: $(ls -1 *.deb 2>/dev/null | wc -l)"
}

# Create offline repo from downloaded .debs
create_repository() {
    log_info "Creating repository structure..."

    mkdir -p "${MIRROR_DIR}/pool"
    mkdir -p "${MIRROR_DIR}/dists/${DIST_NAME}/main/binary-${ARCH}"

    # Copy all debs to pool
    cp "${CACHE_DIR}/base-downloads"/*.deb "${MIRROR_DIR}/pool/" 2>/dev/null || true
    cp "${CACHE_DIR}/purple-downloads"/*.deb "${MIRROR_DIR}/pool/" 2>/dev/null || true

    cd "$MIRROR_DIR"

    # Generate Packages file
    apt-ftparchive packages pool > "dists/${DIST_NAME}/main/binary-${ARCH}/Packages"
    gzip -9c "dists/${DIST_NAME}/main/binary-${ARCH}/Packages" > "dists/${DIST_NAME}/main/binary-${ARCH}/Packages.gz"

    # Generate Release file
    cat > /tmp/apt-ftparchive.conf <<EOF
APT::FTPArchive::Release::Origin "Purple Computer";
APT::FTPArchive::Release::Label "PurpleOS Offline Repository";
APT::FTPArchive::Release::Suite "${DIST_NAME}";
APT::FTPArchive::Release::Codename "${DIST_NAME}";
APT::FTPArchive::Release::Architectures "${ARCH}";
APT::FTPArchive::Release::Components "main";
APT::FTPArchive::Release::Description "${DIST_FULL} Offline Repository";
EOF

    apt-ftparchive -c /tmp/apt-ftparchive.conf release "dists/${DIST_NAME}" > "dists/${DIST_NAME}/Release"

    log_info "Repository created: ${MIRROR_DIR}"
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
    log_info "✓ Repository ready at: ${MIRROR_DIR}"
    log_info "  Packages: $(ls -1 ${MIRROR_DIR}/pool/*.deb 2>/dev/null | wc -l)"
    log_info "  Size: $(du -sh ${MIRROR_DIR} | cut -f1)"
    log_info ""
    log_info "Next: Run 02-build-fai-nfsroot.sh"
}

main
