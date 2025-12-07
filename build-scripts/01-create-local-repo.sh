#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

REPO_BASE="/opt/purple-installer/local-repo"
MIRROR_DIR="${REPO_BASE}/mirror"
CACHE_DIR="${REPO_BASE}/cache"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check for required tools
check_dependencies() {
    local missing=0

    for cmd in apt-get dpkg apt-cache; do
        if ! command -v $cmd &> /dev/null; then
            log_error "Required command not found: $cmd"
            missing=1
        fi
    done

    if [ $missing -eq 1 ]; then
        log_error "Please install required dependencies"
        exit 1
    fi
}

# Create directory structure
create_directories() {
    log_info "Creating repository directory structure..."

    mkdir -p "${MIRROR_DIR}/dists/${DIST_NAME}"
    mkdir -p "${CACHE_DIR}"

    for section in $SECTIONS; do
        mkdir -p "${MIRROR_DIR}/dists/${DIST_NAME}/${section}/binary-${ARCH}"
        mkdir -p "${MIRROR_DIR}/pool/${section}"
    done

    log_info "Directory structure created at: ${REPO_BASE}"
}

# Read all package lists from FAI config
collect_package_list() {
    log_info "Collecting package list from FAI configuration..."

    local pkg_config_dir="/home/tavi/purplecomputer/fai-config/package_config"
    local pkg_list="${CACHE_DIR}/all-packages.list"

    > "$pkg_list"  # Clear file

    for config_file in "$pkg_config_dir"/*; do
        if [ -f "$config_file" ]; then
            log_info "Processing: $(basename $config_file)"
            # Extract package names (skip comments and PACKAGES directives)
            grep -v '^#' "$config_file" | \
            grep -v '^PACKAGES' | \
            grep -v '^$' | \
            awk '{print $1}' >> "$pkg_list"
        fi
    done

    # Remove duplicates and sort
    sort -u "$pkg_list" -o "$pkg_list"

    local count=$(wc -l < "$pkg_list")
    log_info "Total unique packages to download: $count"
}

# Download packages and dependencies
download_packages() {
    log_info "Downloading packages and dependencies..."

    local pkg_list="${CACHE_DIR}/all-packages.list"
    local download_dir="${CACHE_DIR}/downloads"

    mkdir -p "$download_dir"
    cd "$download_dir"

    # Update package lists
    log_info "Updating APT cache..."
    apt-get update

    # Download packages with dependencies
    log_info "Downloading packages (this may take a while)..."

    # Use apt-get download with --download-only and resolver
    xargs -a "$pkg_list" apt-get install --reinstall --download-only -y -o Dir::Cache::Archives="$download_dir"

    # Alternative: use apt-rdepends for complete dependency resolution
    # apt-get install apt-rdepends
    # cat "$pkg_list" | xargs apt-rdepends --follow=Depends,PreDepends,Recommends | \
    #     grep -v '^ ' | sort -u | \
    #     xargs apt-get install --reinstall --download-only -y -o Dir::Cache::Archives="$download_dir"

    log_info "Download complete. Downloaded $(ls -1 *.deb 2>/dev/null | wc -l) packages."
}

# Organize packages into pool structure
organize_packages() {
    log_info "Organizing packages into pool structure..."

    local download_dir="${CACHE_DIR}/downloads"

    cd "$download_dir"

    for deb in *.deb; do
        if [ ! -f "$deb" ]; then
            continue
        fi

        # Determine section from package metadata
        local section=$(dpkg-deb -f "$deb" Section | cut -d/ -f1)

        # Default to main if no section specified
        if [ -z "$section" ] || [ "$section" = "unknown" ]; then
            section="main"
        fi

        # Get first letter of package name for pool structure
        local pkg_name=$(dpkg-deb -f "$deb" Package)
        local first_letter=${pkg_name:0:1}

        # Special handling for lib* packages
        if [[ $pkg_name == lib* ]]; then
            first_letter="lib${pkg_name:3:1}"
        fi

        # Create pool directory
        local pool_dir="${MIRROR_DIR}/pool/${section}/${first_letter}/${pkg_name}"
        mkdir -p "$pool_dir"

        # Copy package to pool
        cp "$deb" "$pool_dir/"
    done

    log_info "Packages organized in pool structure."
}

# Create repository metadata
create_metadata() {
    log_info "Creating repository metadata..."

    cd "$MIRROR_DIR"

    for section in $SECTIONS; do
        local packages_file="dists/${DIST_NAME}/${section}/binary-${ARCH}/Packages"

        log_info "Generating Packages file for ${section}..."

        # Use dpkg-scanpackages to create Packages file
        dpkg-scanpackages --arch "$ARCH" "pool/${section}" /dev/null > "$packages_file"

        # Compress Packages file
        gzip -9c "$packages_file" > "${packages_file}.gz"
        bzip2 -9c "$packages_file" > "${packages_file}.bz2"
        xz -9c "$packages_file" > "${packages_file}.xz"
    done

    log_info "Packages files generated."
}

# Create Release file
create_release() {
    log_info "Creating Release file..."

    local release_file="${MIRROR_DIR}/dists/${DIST_NAME}/Release"

    cat > "$release_file" <<EOF
Origin: Purple Computer
Label: Purple Computer Local Repository
Suite: ${DIST_NAME}
Codename: ${DIST_NAME}
Date: $(date -R)
Architectures: ${ARCH}
Components: ${SECTIONS}
Description: ${DIST_FULL} Offline Repository
EOF

    # Generate checksums
    cd "${MIRROR_DIR}/dists/${DIST_NAME}"

    # MD5Sum
    echo "MD5Sum:" >> "$release_file"
    find . -type f -name 'Packages*' | while read file; do
        # Strip leading ./
        file_path="${file#./}"
        file_size=$(stat -c%s "$file")
        file_hash=$(md5sum "$file" | awk '{print $1}')
        echo " $file_hash $file_size $file_path"
    done >> "$release_file"

    # SHA256
    echo "SHA256:" >> "$release_file"
    find . -type f -name 'Packages*' | while read file; do
        # Strip leading ./
        file_path="${file#./}"
        file_size=$(stat -c%s "$file")
        file_hash=$(sha256sum "$file" | awk '{print $1}')
        echo " $file_hash $file_size $file_path"
    done >> "$release_file"

    log_info "Release file created."
}

# Main execution
main() {
    log_info "Starting local repository creation for Purple Computer..."
    log_info "Distribution: ${DIST_FULL}"
    log_info "Architecture: ${ARCH}"

    check_dependencies
    create_directories
    collect_package_list
    download_packages
    organize_packages
    create_metadata
    create_release

    log_info ""
    log_info "Local repository created successfully!"
    log_info "Repository location: ${MIRROR_DIR}"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Review the repository at ${MIRROR_DIR}"
    log_info "  2. Run 02-build-fai-nfsroot.sh to create FAI installation environment"
    log_info "  3. Run 03-build-iso.sh to create bootable ISO"
}

# Run main function
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root (for apt operations)"
    exit 1
fi

main
