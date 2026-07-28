#!/usr/bin/env bash
# Purple Computer Build Configuration

# Paths
INSTALLER_BASE="/opt/purple-installer"
BUILD_DIR="$INSTALLER_BASE/build"
OUTPUT_DIR="$INSTALLER_BASE/output"
TEST_DIR="$INSTALLER_BASE/test-results"

DIST_NAME="noble"
DIST_FULL="Ubuntu 24.04.1 LTS"
ARCH="amd64"

# Ubuntu Server ISO (initramfs injection architecture)
UBUNTU_ISO_URL="https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-24.04.1-live-server-amd64.iso"

# Essential base packages for golden image (the installed system)
GOLDEN_PACKAGES="linux-image-generic grub-efi-amd64 systemd sudo"

# Where 'just build --ref <commit>' keeps an old commit's build state (its own
# golden image and output dir), so it never clobbers the current build. Flash
# from it with 'just flash --ref <commit>'.
archive_dir_for_ref() {
    local hash
    hash="$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --short "$1")" || return 1
    echo "$INSTALLER_BASE/archive/$hash"
}

# variant_path <stem> <standard|backup|debug>
variant_path() {
    case "$2" in
        backup) echo "$1.with-backup.iso" ;;
        debug)  echo "$1.debug.iso" ;;
        *)      echo "$1.iso" ;;
    esac
}

variant_label() {
    case "$1" in
        backup) echo "standard + backup image, for shipped USBs" ;;
        debug)  echo "debug boot menu" ;;
        *)      echo "standard" ;;
    esac
}

# The ISO variants a build produces, given current PURPLE_WITH_BACKUP_ISO.
planned_iso_variants() {
    echo standard
    [ "${PURPLE_WITH_BACKUP_ISO:-0}" = "1" ] && echo backup
    echo debug
    return 0
}

# Path stem (no variant suffix) a build would write today, given FAST_BUILD.
# Mirrors the naming in 01-remaster-iso.sh.
planned_build_stem() {
    local tag=""
    [ "${FAST_BUILD:-0}" = "1" ] && tag="-fast"
    echo "$OUTPUT_DIR/purple-installer-$(date +%Y%m%d)${tag}"
}

# Human-readable list of the ISO files a build will produce.
planned_iso_names() {
    local stem variant
    stem="$(planned_build_stem)"
    for variant in $(planned_iso_variants); do
        echo "$(basename "$(variant_path "$stem" "$variant")")  ($(variant_label "$variant"))"
    done
}

# Stem of an existing build of git commit <hash> that already has every variant
# the current settings would produce, or nothing. Lets a build skip itself.
existing_build_for_hash() {
    local hash="$1" is_fast vf stem variant found=""
    # Date-stamped names, so the last glob match is the newest build.
    for vf in "$OUTPUT_DIR"/purple-installer-*.iso.version; do
        [ -f "$vf" ] || continue
        [[ "$(tr -d '[:space:]' < "$vf")" == build-"$hash"-* ]] || continue
        stem="${vf%.iso.version}"
        stem="${stem%.with-backup}"
        stem="${stem%.debug}"
        [[ "$stem" == *-fast ]] && is_fast=1 || is_fast=0
        [ "$is_fast" = "${FAST_BUILD:-0}" ] || continue
        for variant in $(planned_iso_variants); do
            [ -f "$(variant_path "$stem" "$variant")" ] || continue 2
        done
        found="$stem"
    done
    [ -n "$found" ] || return 1
    echo "$found"
}
