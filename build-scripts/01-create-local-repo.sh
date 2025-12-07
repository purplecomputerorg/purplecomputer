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

# Collect package list from FAI configs
collect_packages() {
    log_info "Collecting package list from FAI configuration..."

    local pkg_list="${CACHE_DIR}/packages.list"
    > "$pkg_list"

    for config in /home/tavi/purplecomputer/fai-config/package_config/*; do
        grep -v '^#\|^PACKAGES\|^$' "$config" | awk '{print $1}' >> "$pkg_list"
    done

    sort -u "$pkg_list" -o "$pkg_list"
    log_info "Packages to download: $(wc -l < "$pkg_list")"
}

# Download packages with dependencies
download_packages() {
    log_info "Downloading packages and dependencies..."

    mkdir -p "${CACHE_DIR}/downloads"
    cd "${CACHE_DIR}/downloads"

    apt-get update
    xargs -a "${CACHE_DIR}/packages.list" apt-get install --reinstall --download-only -y \
        -o Dir::Cache::Archives="${CACHE_DIR}/downloads"

    log_info "Downloaded $(ls -1 *.deb 2>/dev/null | wc -l) packages"
}

# Organize packages into pool and generate metadata
create_repository() {
    log_info "Creating repository structure..."

    mkdir -p "${MIRROR_DIR}/pool"
    mkdir -p "${MIRROR_DIR}/dists/${DIST_NAME}/main/binary-${ARCH}"

    # Copy all debs to pool (flat structure - simpler)
    cp "${CACHE_DIR}/downloads"/*.deb "${MIRROR_DIR}/pool/" 2>/dev/null || true

    cd "$MIRROR_DIR"

    # Generate Packages file using official tool
    apt-ftparchive packages pool > "dists/${DIST_NAME}/main/binary-${ARCH}/Packages"
    gzip -9c "dists/${DIST_NAME}/main/binary-${ARCH}/Packages" > "dists/${DIST_NAME}/main/binary-${ARCH}/Packages.gz"

    # Generate Release file
    apt-ftparchive release "dists/${DIST_NAME}" > "dists/${DIST_NAME}/Release"

    log_info "Repository created: ${MIRROR_DIR}"
}

# Main
main() {
    log_info "Creating minimal offline repository for Purple Computer"
    log_info "Distribution: ${DIST_FULL} (${DIST_NAME})"

    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi

    mkdir -p "$CACHE_DIR"

    collect_packages
    download_packages
    create_repository

    log_info ""
    log_info "✓ Repository ready at: ${MIRROR_DIR}"
    log_info "  Size: $(du -sh ${MIRROR_DIR} | cut -f1)"
    log_info ""
    log_info "Next: Run 02-build-fai-nfsroot.sh"
}

main
