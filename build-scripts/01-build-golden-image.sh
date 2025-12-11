#!/usr/bin/env bash
# Build PurpleOS Golden Image
# This creates a complete, bootable PurpleOS system as a disk image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
GOLDEN_IMAGE="${BUILD_DIR}/purple-os.img"
GOLDEN_COMPRESSED="${BUILD_DIR}/purple-os.img.zst"
IMAGE_SIZE_MB=8192

# Colors
GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

main() {
    log_info "Building PurpleOS Golden Image..."

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    mkdir -p "$BUILD_DIR"

    # Create empty disk image
    log_info "Creating ${IMAGE_SIZE_MB}MB disk image..."
    dd if=/dev/zero of="$GOLDEN_IMAGE" bs=1M count="$IMAGE_SIZE_MB" status=progress

    # Create partition table
    log_info "Partitioning disk image..."
    parted -s "$GOLDEN_IMAGE" mklabel gpt
    parted -s "$GOLDEN_IMAGE" mkpart ESP fat32 1MiB 513MiB
    parted -s "$GOLDEN_IMAGE" set 1 esp on
    parted -s "$GOLDEN_IMAGE" mkpart primary ext4 513MiB 100%

    # Setup loop device with kpartx (more reliable in Docker)
    log_info "Setting up loop device..."
    LOOP_DEV=$(losetup -f --show "$GOLDEN_IMAGE")
    kpartx -av "$LOOP_DEV"

    # kpartx creates devices like /dev/mapper/loop0p1
    LOOP_NAME=$(basename "$LOOP_DEV")

    # Format partitions with labels (used in fstab)
    log_info "Formatting partitions..."
    mkfs.vfat -F32 -n PURPLE_EFI "/dev/mapper/${LOOP_NAME}p1"
    mkfs.ext4 -L PURPLE_ROOT "/dev/mapper/${LOOP_NAME}p2"

    # Mount root partition
    MOUNT_DIR="${BUILD_DIR}/mnt-golden"
    mkdir -p "$MOUNT_DIR"
    mount "/dev/mapper/${LOOP_NAME}p2" "$MOUNT_DIR"
    mkdir -p "$MOUNT_DIR/boot/efi"
    mount "/dev/mapper/${LOOP_NAME}p1" "$MOUNT_DIR/boot/efi"

    # Install base system using debootstrap
    log_info "Installing base system with debootstrap..."
    debootstrap \
        --arch=amd64 \
        --variant=minbase \
        --include=linux-image-generic,initramfs-tools,systemd,systemd-sysv,sudo,vim-tiny,less,python3 \
        noble \
        "$MOUNT_DIR" \
        http://archive.ubuntu.com/ubuntu

    # Configure system
    log_info "Configuring PurpleOS..."

    # Set hostname
    echo "purplecomputer" > "$MOUNT_DIR/etc/hostname"
    echo "127.0.0.1 localhost purplecomputer" > "$MOUNT_DIR/etc/hosts"

    # Create fstab - critical for mounting root as read-write
    cat > "$MOUNT_DIR/etc/fstab" <<'FSTAB'
# PurpleOS filesystem table
LABEL=PURPLE_ROOT  /         ext4  defaults,errors=remount-ro  0 1
LABEL=PURPLE_EFI   /boot/efi vfat  umask=0077                  0 1
tmpfs              /tmp      tmpfs defaults,nosuid,nodev       0 0
FSTAB

    # Create purple user
    chroot "$MOUNT_DIR" useradd -m -s /bin/bash purple
    chroot "$MOUNT_DIR" usermod -aG sudo purple
    echo "purple:purple" | chroot "$MOUNT_DIR" chpasswd

    # Install Purple Computer application
    log_info "Installing Purple Computer application..."

    # Setup apt sources for universe repository (needed for pip)
    cat > "$MOUNT_DIR/etc/apt/sources.list" <<'SOURCES'
deb http://archive.ubuntu.com/ubuntu noble main universe
deb http://archive.ubuntu.com/ubuntu noble-updates main universe
deb http://archive.ubuntu.com/ubuntu noble-security main universe
SOURCES

    # Install pip, SDL libraries for pygame, audio support, and X11/GUI stack (requires universe repository)
    chroot "$MOUNT_DIR" apt-get update
    chroot "$MOUNT_DIR" apt-get install -y \
        python3-pip \
        libsdl2-2.0-0 libsdl2-mixer-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 \
        alsa-utils pulseaudio \
        xorg xinit x11-xserver-utils \
        xserver-xorg-core \
        xserver-xorg-input-all \
        xserver-xorg-video-all \
        matchbox-window-manager \
        alacritty \
        libxkbcommon-x11-0 \
        unclutter \
        fontconfig \
        spice-vdagent

    # Install JetBrainsMono Nerd Font (needed for emoji/icon glyphs in Purple TUI)
    # Download from host (curl available in Docker container, not in chroot)
    log_info "Installing JetBrainsMono Nerd Font..."
    FONT_DIR="$MOUNT_DIR/usr/share/fonts/truetype/jetbrains-mono-nerd"
    mkdir -p "$FONT_DIR"
    curl -fsSL https://github.com/ryanoasis/nerd-fonts/releases/download/v3.1.1/JetBrainsMono.zip -o /tmp/JetBrainsMono.zip
    unzip -o /tmp/JetBrainsMono.zip -d "$FONT_DIR"
    rm /tmp/JetBrainsMono.zip
    chroot "$MOUNT_DIR" fc-cache -fv

    # Copy application files (project root is mounted at /purple-src)
    mkdir -p "$MOUNT_DIR/opt/purple"
    cp -r /purple-src/purple_tui "$MOUNT_DIR/opt/purple/"
    cp -r /purple-src/packs "$MOUNT_DIR/opt/purple/"
    cp /purple-src/keyboard_normalizer.py "$MOUNT_DIR/opt/purple/"
    cp /purple-src/requirements.txt "$MOUNT_DIR/opt/purple/"
    cp /purple-src/scripts/calc_font_size.py "$MOUNT_DIR/opt/purple/"

    # Install Python dependencies (python-xlib for font size calculation fallback)
    chroot "$MOUNT_DIR" pip3 install --break-system-packages textual rich wcwidth pygame python-xlib

    # Clean apt cache to save space
    chroot "$MOUNT_DIR" apt-get clean

    # Create launcher script
    cat > "$MOUNT_DIR/usr/local/bin/purple" <<'LAUNCHER'
#!/bin/bash
export TERM=${TERM:-linux}
export SDL_AUDIODRIVER=${SDL_AUDIODRIVER:-alsa}
cd /opt/purple

# Detect VM and suppress ALSA underrun warnings (only affects VMs, not real hardware)
if systemd-detect-virt -q 2>/dev/null; then
    exec python3 -m purple_tui.purple_tui "$@" 2>&1 | grep -v "snd_pcm_recover"
else
    exec python3 -m purple_tui.purple_tui "$@"
fi
LAUNCHER
    chmod +x "$MOUNT_DIR/usr/local/bin/purple"

    # Configure auto-login for purple user on tty1
    mkdir -p "$MOUNT_DIR/etc/systemd/system/getty@tty1.service.d"
    cat > "$MOUNT_DIR/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin purple --noclear %I $TERM
AUTOLOGIN

    # Copy xinitrc from project config (shared with dev environment)
    cp /purple-src/config/xinit/xinitrc "$MOUNT_DIR/home/purple/.xinitrc"
    chmod +x "$MOUNT_DIR/home/purple/.xinitrc"
    chown 1000:1000 "$MOUNT_DIR/home/purple/.xinitrc"

    # Copy Alacritty config from project config (shared with dev environment)
    mkdir -p "$MOUNT_DIR/etc/purple"
    cp /purple-src/config/alacritty/alacritty.toml "$MOUNT_DIR/etc/purple/alacritty.toml"

    # Configure auto-start X11 on login (via .bashrc)
    cat >> "$MOUNT_DIR/home/purple/.bashrc" <<'AUTOSTART'

# Auto-start X11 with Purple Computer on login (only on tty1, not SSH)
if [ -z "$SSH_CONNECTION" ] && [ "$(tty)" = "/dev/tty1" ]; then
    # Clean stale X lock files from previous crashes
    rm -f /tmp/.X0-lock /tmp/.X11-unix/X0 2>/dev/null
    exec startx
fi
AUTOSTART
    chown 1000:1000 "$MOUNT_DIR/home/purple/.bashrc"

    # Configure auto-login on tty2 as well (for debugging - no X11, just bash)
    mkdir -p "$MOUNT_DIR/etc/systemd/system/getty@tty2.service.d"
    cat > "$MOUNT_DIR/etc/systemd/system/getty@tty2.service.d/autologin.conf" <<'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin purple --noclear %I $TERM
AUTOLOGIN

    # We skip grub-install and update-grub entirely - they create complex configs that
    # don't work well with our standalone GRUB. Instead we use grub-mkstandalone for
    # the bootloader and create our own minimal grub.cfg.

    # Create minimal grub.cfg for the installed system
    # This is what gets loaded when our standalone BOOTX64.EFI calls configfile
    log_info "Creating minimal GRUB configuration..."
    mkdir -p "$MOUNT_DIR/boot/grub"
    cat > "$MOUNT_DIR/boot/grub/grub.cfg" <<'EOF'
# PurpleOS minimal GRUB configuration
set timeout=0
set default=0

menuentry "PurpleOS" {
    search --no-floppy --label PURPLE_ROOT --set=root
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro quiet console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}

menuentry "PurpleOS (recovery mode)" {
    search --no-floppy --label PURPLE_ROOT --set=root
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro single console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
EOF

    # Create symlinks to actual kernel/initrd (Ubuntu installs versioned files)
    # This makes our grub.cfg work regardless of kernel version
    KERNEL_VERSION=$(ls "$MOUNT_DIR/boot/" | grep "vmlinuz-" | head -1 | sed 's/vmlinuz-//')
    if [ -n "$KERNEL_VERSION" ]; then
        ln -sf "vmlinuz-$KERNEL_VERSION" "$MOUNT_DIR/boot/vmlinuz"
        ln -sf "initrd.img-$KERNEL_VERSION" "$MOUNT_DIR/boot/initrd.img"
        log_info "  Kernel version: $KERNEL_VERSION"
    fi

    # Create fallback bootloader using grub-mkstandalone for maximum hardware compatibility
    # Ubuntu's grubx64.efi may not have all modules (e.g., serial) built in
    # grub-mkstandalone ensures we have all modules needed for debugging and boot
    log_info "Creating UEFI fallback bootloader with grub-mkstandalone..."
    mkdir -p "$MOUNT_DIR/boot/efi/EFI/BOOT"

    # Create the grub.cfg that will be embedded in the standalone EFI binary
    cat > /tmp/grub-standalone.cfg <<'EOF'
# GRUB standalone bootloader for PurpleOS
terminal_output console
terminal_input console
set pager=0

search --no-floppy --label PURPLE_ROOT --set=root

if [ -n "$root" ]; then
    set prefix=($root)/boot/grub
    configfile ($root)/boot/grub/grub.cfg
fi
EOF

    # Generate standalone GRUB EFI with all required modules
    grub-mkstandalone \
        --format=x86_64-efi \
        --output="$MOUNT_DIR/boot/efi/EFI/BOOT/BOOTX64.EFI" \
        --modules="part_gpt part_msdos fat ext2 normal linux configfile search search_label efi_gop efi_uga all_video video video_bochs video_cirrus video_fb gfxterm gfxterm_background terminal terminfo font echo test" \
        --locales="" \
        "boot/grub/grub.cfg=/tmp/grub-standalone.cfg"

    rm -f /tmp/grub-standalone.cfg

    # Cleanup
    log_info "Cleaning up..."
    sync
    umount "$MOUNT_DIR/boot/efi"
    umount "$MOUNT_DIR"
    kpartx -dv "$LOOP_DEV"
    losetup -d "$LOOP_DEV"

    # Compress golden image
    log_info "Compressing golden image..."
    zstd -19 -T0 -f "$GOLDEN_IMAGE" -o "$GOLDEN_COMPRESSED"

    log_info "✓ Golden image ready: $GOLDEN_COMPRESSED"
    log_info "  Original size: $(du -h $GOLDEN_IMAGE | cut -f1)"
    log_info "  Compressed: $(du -h $GOLDEN_COMPRESSED | cut -f1)"

    # Delete uncompressed image to save space
    rm -f "$GOLDEN_IMAGE"
}

main "$@"
