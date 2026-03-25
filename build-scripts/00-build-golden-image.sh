#!/usr/bin/env bash
# Build PurpleOS Golden Image
# This creates a complete, bootable PurpleOS system as a disk image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
GOLDEN_IMAGE="${BUILD_DIR}/purple-os.img"
GOLDEN_COMPRESSED="${BUILD_DIR}/purple-os.img.zst"
IMAGE_SIZE_MB=8192
MOUNT_DIR="${BUILD_DIR}/mnt-golden"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

# Track the loop device so cleanup can find it
LOOP_DEV=""

cleanup_build() {
    # Tear down mounts, kpartx mappings, and loop devices from this or previous builds.
    # Safe to call multiple times (every step is idempotent).
    log_info "Cleaning up stale mounts and loop devices..."

    # Unmount anything under the mount dir
    if [ -d "$MOUNT_DIR" ]; then
        for mp in "$MOUNT_DIR/dev/pts" "$MOUNT_DIR/dev" "$MOUNT_DIR/sys" "$MOUNT_DIR/proc" "$MOUNT_DIR/boot/efi" "$MOUNT_DIR"; do
            mountpoint -q "$mp" 2>/dev/null && umount -l "$mp" 2>/dev/null || true
        done
    fi

    # Remove kpartx mappings and detach loop devices associated with our image
    for loop in $(losetup -j "$GOLDEN_IMAGE" 2>/dev/null | cut -d: -f1); do
        kpartx -dv "$loop" 2>/dev/null || true
        losetup -d "$loop" 2>/dev/null || true
    done

    # Also clean up the tracked loop device (in case the image file was already deleted)
    if [ -n "$LOOP_DEV" ] && losetup "$LOOP_DEV" &>/dev/null; then
        kpartx -dv "$LOOP_DEV" 2>/dev/null || true
        losetup -d "$LOOP_DEV" 2>/dev/null || true
    fi
}

# Clean up on exit (success or failure) so failed builds never leave stale state
trap cleanup_build EXIT

main() {
    log_info "Building PurpleOS Golden Image..."

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    # Clean up any leftover state from a previous failed build
    cleanup_build

    mkdir -p "$BUILD_DIR"

    # Create empty disk image
    log_info "Creating ${IMAGE_SIZE_MB}MB disk image..."
    dd if=/dev/zero of="$GOLDEN_IMAGE" bs=1M count="$IMAGE_SIZE_MB" status=progress
    sync

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

    # Mount virtual filesystems for chroot operations (required by apt-get, systemd, etc.)
    log_info "Mounting virtual filesystems for chroot..."
    mount --bind /proc "$MOUNT_DIR/proc"
    mount --bind /sys "$MOUNT_DIR/sys"
    mount --bind /dev "$MOUNT_DIR/dev"
    mount --bind /dev/pts "$MOUNT_DIR/dev/pts"

    # Install linux-modules-extra immediately, using debootstrap's sources.list
    # which points at the same base 'noble' repo. This guarantees the version matches
    # the kernel debootstrap installed. Must happen BEFORE we overwrite sources.list
    # with noble-updates (which has newer, non-matching versions).
    KVER=$(ls "$MOUNT_DIR/lib/modules/" | head -1)
    log_info "Kernel from debootstrap: $KVER"
    chroot "$MOUNT_DIR" apt-get update
    chroot "$MOUNT_DIR" apt-get install -y "linux-modules-extra-$KVER"

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

    # Create purple user (input group for keyboard access via evdev)
    # No password: this is an offline appliance for kids, not a multi-user system
    chroot "$MOUNT_DIR" useradd -m -s /bin/bash purple
    chroot "$MOUNT_DIR" usermod -aG sudo,input purple
    chroot "$MOUNT_DIR" passwd -l purple

    # Install Purple Computer application
    log_info "Installing Purple Computer application..."

    # Setup apt sources for universe repository (needed for pip)
    # Using us.archive for better mirror sync reliability
    cat > "$MOUNT_DIR/etc/apt/sources.list" <<'SOURCES'
deb http://us.archive.ubuntu.com/ubuntu noble main universe
deb http://us.archive.ubuntu.com/ubuntu noble-updates main universe
deb http://security.ubuntu.com/ubuntu noble-security main universe
SOURCES

    # Don't install Recommended packages. This is an appliance, not a desktop.
    # Saves ~100-200MB by skipping optional extras (e.g. bluetooth modules,
    # extra font packages, documentation). Test boot after changing this.
    echo 'APT::Install-Recommends "0";' > "$MOUNT_DIR/etc/apt/apt.conf.d/99norecommends"

    chroot "$MOUNT_DIR" apt-get update

    # Install pip, SDL libraries for pygame, audio support, and X11/GUI stack (requires universe repository)
    # NOTE: We deliberately omit xserver-xorg-video-all to use the modesetting driver
    # built into xserver-xorg-core. This avoids xf86EnableIO errors from legacy drivers
    # (vesa, fbdev) trying to access VGA I/O ports under rootless X.
    # Mesa is required for glamor acceleration with modesetting.
    #
    # X11: minimal packages instead of the `xorg` metapackage (which pulls in
    # x11-apps, xfonts-base, xfonts-utils, x11-session-utils, xorg-docs, etc.)
    # linux-firmware is a Recommend of linux-image-generic (not a hard dep).
    # With --no-install-recommends it's skipped, but we need GPU firmware
    # (i915, amdgpu, nvidia) for display. Install it explicitly here;
    # the firmware pruning step later strips everything we don't need.
    chroot "$MOUNT_DIR" apt-get install -y linux-firmware

    chroot "$MOUNT_DIR" apt-get install -y \
        python3-pip \
        libsdl2-2.0-0 libsdl2-mixer-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 \
        alsa-utils pulseaudio \
        xinit x11-xserver-utils \
        xserver-xorg-core \
        xserver-xorg-input-libinput \
        xkb-data xauth \
        libgl1-mesa-dri \
        matchbox-window-manager \
        alacritty \
        ncurses-term \
        libxkbcommon-x11-0 \
        fontconfig \
        fonts-noto-color-emoji \
        xkbset \
        unclutter \
        casper \
        zstd

    # If apt upgraded the kernel (noble-updates has newer versions), install
    # modules-extra for the new version too, then rebuild initrd.
    KVER_NOW=$(ls -v "$MOUNT_DIR/lib/modules/" | tail -1)
    if [ "$KVER_NOW" != "$KVER" ]; then
        log_info "Kernel upgraded: $KVER -> $KVER_NOW"
        chroot "$MOUNT_DIR" apt-get install -y "linux-modules-extra-$KVER_NOW"

        # Remove old kernel to save ~100-200MB (appliance only needs one kernel)
        log_info "Removing old kernel $KVER..."
        chroot "$MOUNT_DIR" apt-get remove --purge -y \
            "linux-image-$KVER" "linux-modules-$KVER" "linux-modules-extra-$KVER" 2>/dev/null || true

        KVER="$KVER_NOW"
    fi

    # Rebuild initrd to include casper scripts (installed above)
    chroot "$MOUNT_DIR" update-initramfs -u -k "$KVER"

    # Verify sound modules are present (fail the build if not)
    log_info "Kernel version: $KVER"
    if [ ! -d "$MOUNT_DIR/lib/modules/$KVER/kernel/sound/pci" ]; then
        echo "ERROR: Sound modules not found! linux-modules-extra may have failed to install."
        ls -R "$MOUNT_DIR/lib/modules/$KVER/kernel/sound/" 2>/dev/null
        exit 1
    fi
    log_info "Sound modules verified"

    # Install JetBrainsMono Nerd Font (for UI icons like battery, volume, etc.)
    # Noto Color Emoji (installed via apt above) provides Unicode emoji
    # Download from host (curl available in Docker container, not in chroot)
    log_info "Installing JetBrainsMono Nerd Font..."
    FONT_DIR="$MOUNT_DIR/usr/share/fonts/truetype/jetbrains-mono-nerd"
    mkdir -p "$FONT_DIR"
    curl -fsSL https://github.com/ryanoasis/nerd-fonts/releases/download/v3.1.1/JetBrainsMono.zip -o /tmp/JetBrainsMono.zip
    # Install only the 4 weights Alacritty uses (Regular, Bold, Italic, Bold Italic).
    # The full zip has 40+ files (Thin, Light, Medium, SemiBold, ExtraBold, etc.)
    unzip -o /tmp/JetBrainsMono.zip \
        "JetBrainsMonoNerdFont-Regular.ttf" \
        "JetBrainsMonoNerdFont-Bold.ttf" \
        "JetBrainsMonoNerdFont-Italic.ttf" \
        "JetBrainsMonoNerdFont-BoldItalic.ttf" \
        -d "$FONT_DIR"
    rm /tmp/JetBrainsMono.zip

    # Install fontconfig rule to prioritize Noto Color Emoji
    # Without this, some emoji render as monochrome outlines instead of color
    log_info "Installing emoji fontconfig rule..."
    cp /purple-src/config/fontconfig/99-emoji.conf "$MOUNT_DIR/etc/fonts/conf.d/"

    chroot "$MOUNT_DIR" fc-cache -fv

    # Copy application files (project root is mounted at /purple-src)
    mkdir -p "$MOUNT_DIR/opt/purple"
    cp -r /purple-src/purple_tui "$MOUNT_DIR/opt/purple/"
    cp -r /purple-src/packs "$MOUNT_DIR/opt/purple/"
    cp /purple-src/requirements.txt "$MOUNT_DIR/opt/purple/"
    cp /purple-src/scripts/calc_font_size.py "$MOUNT_DIR/opt/purple/"
    cp /purple-src/scripts/debug-shell.sh "$MOUNT_DIR/opt/purple/"

    # Copy on-device scripts (everything in scripts/on-device/)
    # These are available on the image for debugging from the parent menu terminal
    if [ -d /purple-src/scripts/on-device ]; then
        mkdir -p "$MOUNT_DIR/opt/purple/scripts"
        cp /purple-src/scripts/on-device/*.py "$MOUNT_DIR/opt/purple/scripts/" 2>/dev/null || true
        cp /purple-src/scripts/on-device/*.sh "$MOUNT_DIR/opt/purple/scripts/" 2>/dev/null || true
    fi

    # Copy USB update config (udev rule + systemd service)
    cp /purple-src/config/udev/99-purple-update.rules "$MOUNT_DIR/etc/udev/rules.d/"
    cp /purple-src/config/systemd/purple-usb-update@.service "$MOUNT_DIR/etc/systemd/system/"

    # Copy USB update public key (if it exists, for signature verification)
    if [ -f /purple-src/update-key.pub ]; then
        cp /purple-src/update-key.pub "$MOUNT_DIR/opt/purple/"
        log_info "  USB update public key installed"
    else
        log_info "  Warning: update-key.pub not found. USB updates will not work."
        log_info "  Run 'just keygen' to generate a key pair."
    fi

    # Install build deps for compiling Python C extensions.
    # evdev needs gcc + linux/input.h. Previously pulled in as Recommends,
    # now needed explicitly with --no-install-recommends. Removed after pip install.
    chroot "$MOUNT_DIR" apt-get install -y gcc linux-libc-dev python3-dev

    # Install Python dependencies from requirements.txt
    chroot "$MOUNT_DIR" pip3 install --no-cache-dir --break-system-packages -r /opt/purple/requirements.txt

    # Remove build deps (only needed for compilation).
    # --no-auto-remove prevents apt from cascading into unrelated packages.
    log_info "Packages apt will remove with build deps:"
    chroot "$MOUNT_DIR" apt-get remove --purge -y -s gcc linux-libc-dev python3-dev 2>/dev/null | grep "^Remv" || true

    chroot "$MOUNT_DIR" apt-get remove --purge -y --no-auto-remove gcc linux-libc-dev python3-dev 2>/dev/null || true

    # Download Piper TTS voice model (LibriTTS high quality - American English, speaker p6006)
    log_info "Downloading Piper TTS voice model..."
    VOICE_MODEL="en_US-libritts-high"
    VOICE_DIR="$MOUNT_DIR/opt/purple/piper-voices"
    mkdir -p "$VOICE_DIR"
    curl -fsSL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/${VOICE_MODEL}.onnx" -o "$VOICE_DIR/${VOICE_MODEL}.onnx"
    curl -fsSL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts/high/${VOICE_MODEL}.onnx.json" -o "$VOICE_DIR/${VOICE_MODEL}.onnx.json"

    # Create launcher script
    # NOTE: Do NOT redirect stderr - Textual writes its UI to stderr!
    cat > "$MOUNT_DIR/usr/local/bin/purple" <<'LAUNCHER'
#!/bin/bash
cd /opt/purple

exec python3 -m purple_tui.purple_tui "$@"
LAUNCHER
    chmod +x "$MOUNT_DIR/usr/local/bin/purple"

    # Mask getty@tty1: the purple-x11 service owns tty1 directly (no login shell needed)
    chroot "$MOUNT_DIR" systemctl mask getty@tty1.service

    # Early boot splash: paint tty1 purple with "Starting up..." message.
    # With console=tty2, tty1 is blank until agetty starts. This fills the gap.
    cat > "$MOUNT_DIR/usr/local/bin/purple-splash" <<'SPLASH'
#!/bin/sh
# In debug mode, skip the splash so kernel/systemd messages stay visible
[ -f /opt/purple/debug ] && exit 0
# Silence kernel console messages (camera drivers, etc.) so they don't
# overwrite our splash. Works regardless of which modules are loaded.
dmesg -n 1 2>/dev/null
# Redefine VT color 0 (black) to Purple Computer purple (#2d1b4e),
# then clear screen (fills with purple) and show white text.
printf '\033]P02d1b4e\033[H\033[2J\033[97m\033[5;7H Welcome to Purple Computer!\033[7;7H Starting up...\033[0m' > /dev/tty1 2>/dev/null
SPLASH
    chmod +x "$MOUNT_DIR/usr/local/bin/purple-splash"

    cat > "$MOUNT_DIR/etc/systemd/system/purple-splash.service" <<'SPLASHUNIT'
[Unit]
Description=Purple Computer Boot Splash
DefaultDependencies=no
After=systemd-vconsole-setup.service
Before=getty@tty1.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/purple-splash
# On shutdown, repaint tty1 purple so no X.Org or systemd messages are visible
ExecStop=/usr/local/bin/purple-splash
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
SPLASHUNIT
    chroot "$MOUNT_DIR" systemctl enable purple-splash.service

    # Configure systemd-logind for power management
    # The Purple TUI handles power button and lid close with kid-friendly UX:
    #   Power tap = sleep screen, power hold 3s = shutdown, lid close = shutdown after 2 min
    # logind is set to ignore so the TUI has full control.
    # If the TUI isn't running, idle shutdown (30 min) and hardware power-off (10s hold) still work.
    mkdir -p "$MOUNT_DIR/etc/systemd/logind.conf.d"
    cat > "$MOUNT_DIR/etc/systemd/logind.conf.d/purple-power.conf" <<'LOGIND'
# Purple Computer power management
# TUI handles all power UX. logind ignores buttons so TUI has full control.
# Hardware 10-second power hold always works as emergency off (ACPI).
[Login]
# Power button: TUI handles tap (sleep) and hold (shutdown)
HandlePowerKey=ignore
HandlePowerKeyLongPress=ignore
# Lid: TUI handles with 2-minute delayed shutdown
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
# No suspend/hibernate: on/off only for reliability across old laptops
HandleSuspendKey=ignore
HandleHibernateKey=ignore
# Allow purple user to shut down without password
PolicyKitBypassUsers=purple
LOGIND

    # Passwordless sudo: offline appliance, no security boundary needed
    cat > "$MOUNT_DIR/etc/sudoers.d/purple-nopasswd" <<'SUDOERS'
purple ALL=(ALL) NOPASSWD: ALL
SUDOERS
    chmod 440 "$MOUNT_DIR/etc/sudoers.d/purple-nopasswd"

    # Disable SysRq magic keys (Alt+PrintScreen combos can force reboot, kill processes, etc.)
    # Kids mashing keys could accidentally trigger these. Value 0 = completely disabled.
    # Parents/admins can still use the power button for shutdown.
    mkdir -p "$MOUNT_DIR/etc/sysctl.d"
    cat > "$MOUNT_DIR/etc/sysctl.d/99-purple-sysrq.conf" <<'SYSCTL'
# Purple Computer: disable SysRq magic keys for kid-proofing
# Alt+SysRq+B = instant reboot, Alt+SysRq+O = instant poweroff, etc.
# These are dangerous when kids mash random key combinations.
kernel.sysrq = 0

# Suppress kernel messages on console (camera drivers, etc. leak to tty1 during boot).
# Format: console_loglevel default_message_loglevel minimum_console_loglevel default_console_loglevel
# Level 1 = only KERN_ALERT and KERN_EMERG reach the console.
kernel.printk = 1 1 1 1
SYSCTL

    # Disable Ctrl+Alt+Del reboot (systemd target)
    # By default this triggers a system reboot, which kids could hit accidentally
    chroot "$MOUNT_DIR" systemctl mask ctrl-alt-del.target

    # Suppress Ubuntu MOTD on login (PAM's pam_motd.so prints it even with --noissue)
    touch "$MOUNT_DIR/home/purple/.hushlogin"
    chown 1000:1000 "$MOUNT_DIR/home/purple/.hushlogin"

    # Pre-create .Xauthority so startx doesn't warn about it missing
    touch "$MOUNT_DIR/home/purple/.Xauthority"
    chown 1000:1000 "$MOUNT_DIR/home/purple/.Xauthority"

    # Copy xinitrc from project config (shared with dev environment)
    cp /purple-src/config/xinit/xinitrc "$MOUNT_DIR/home/purple/.xinitrc"
    chmod +x "$MOUNT_DIR/home/purple/.xinitrc"
    chown 1000:1000 "$MOUNT_DIR/home/purple/.xinitrc"

    # Copy X.Org configs
    mkdir -p "$MOUNT_DIR/usr/share/X11/xorg.conf.d"
    # Forces modesetting driver, avoids I/O port issues
    cp /purple-src/config/xorg/10-modesetting.conf "$MOUNT_DIR/usr/share/X11/xorg.conf.d/"
    # Disable mouse/trackpad - kids use keyboard only
    cp /purple-src/config/xorg/40-disable-pointer.conf "$MOUNT_DIR/usr/share/X11/xorg.conf.d/"

    # Purple X11 service: systemd-managed, waits for GPU readiness before starting X
    cp /purple-src/config/systemd/purple-x11.service "$MOUNT_DIR/etc/systemd/system/"
    cp /purple-src/scripts/purple-wait-display.sh "$MOUNT_DIR/usr/local/bin/purple-wait-display"
    cp /purple-src/scripts/purple-x11-failed.sh "$MOUNT_DIR/usr/local/bin/purple-x11-failed"
    chmod +x "$MOUNT_DIR/usr/local/bin/purple-wait-display"
    chmod +x "$MOUNT_DIR/usr/local/bin/purple-x11-failed"
    chroot "$MOUNT_DIR" systemctl enable purple-x11.service

    # Copy Alacritty config from project config (shared with dev environment)
    mkdir -p "$MOUNT_DIR/etc/purple"
    cp /purple-src/config/alacritty/alacritty.toml "$MOUNT_DIR/etc/purple/alacritty.toml"

    # Store canonical copies of dotfiles in /etc/purple/ (casper can't shadow these).
    # The casper live boot hook copies them back to /home/purple/ after casper's
    # adduser overwrites the home directory with skeleton files.
    cp /purple-src/config/xinit/xinitrc "$MOUNT_DIR/etc/purple/xinitrc"

    # Configure auto-login on tty2 as well (for debugging - no X11, just bash)
    mkdir -p "$MOUNT_DIR/etc/systemd/system/getty@tty2.service.d"
    cat > "$MOUNT_DIR/etc/systemd/system/getty@tty2.service.d/autologin.conf" <<'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin purple --skip-login --noclear --noissue --nohostname %I $TERM
AUTOLOGIN

    # Use Ubuntu's signed boot chain (shim → GRUB → kernel) for Secure Boot compatibility.
    # We download the signed binaries and set them up manually, rather than running
    # grub-install which doesn't work in a container/chroot build environment.

    # Create minimal grub.cfg for the installed system
    # This is what gets loaded when the EFI search config calls configfile
    log_info "Creating minimal GRUB configuration..."
    mkdir -p "$MOUNT_DIR/boot/grub"
    cat > "$MOUNT_DIR/boot/grub/grub.cfg" <<'EOF'
# PurpleOS minimal GRUB configuration
set timeout=0
set default=0

menuentry "PurpleOS" {
    search --no-floppy --label PURPLE_ROOT --set=root
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro quiet loglevel=0 systemd.show_status=false vt.global_cursor_default=0 console=tty2 console=ttyS0,115200n8 vt.default_red=0x2d,0xaa,0x00,0xaa,0x00,0xaa,0x00,0xaa,0x55,0xff,0x55,0xff,0x55,0xff,0x55,0xff vt.default_grn=0x1b,0x00,0xaa,0x55,0x00,0x00,0xaa,0xaa,0x55,0x55,0xff,0xff,0x55,0x55,0xff,0xff vt.default_blu=0x4e,0x00,0x00,0x00,0xaa,0xaa,0xaa,0xaa,0x55,0x55,0x55,0x55,0xff,0xff,0xff,0xff
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
    KERNEL_VERSION=$(ls -v "$MOUNT_DIR/boot/" | grep "vmlinuz-" | tail -1 | sed 's/vmlinuz-//')
    if [ -n "$KERNEL_VERSION" ]; then
        ln -sf "vmlinuz-$KERNEL_VERSION" "$MOUNT_DIR/boot/vmlinuz"
        ln -sf "initrd.img-$KERNEL_VERSION" "$MOUNT_DIR/boot/initrd.img"
        log_info "  Kernel version: $KERNEL_VERSION"
    fi

    # Set up Secure Boot compatible UEFI boot chain
    # shim (Microsoft-signed) → GRUB (Canonical-signed) → kernel (Canonical-signed)
    # See CLAUDE.md "UEFI Boot and Hardware Compatibility" for the multi-path strategy
    log_info "Setting up Secure Boot boot chain..."
    mkdir -p "$MOUNT_DIR/boot/efi/EFI/BOOT"

    # Download signed binaries without full install (avoids grub-install postinst
    # which fails in container/chroot and would fight our manual EFI layout)
    if ! chroot "$MOUNT_DIR" bash -c 'cd /tmp && apt-get download shim-signed grub-efi-amd64-signed'; then
        echo "ERROR: Failed to download signed boot packages"
        exit 1
    fi

    # Extract signed binaries from downloaded debs
    EXTRACT_DIR="$MOUNT_DIR/tmp/boot-extract"
    mkdir -p "$EXTRACT_DIR"
    for deb in "$MOUNT_DIR/tmp/"shim-signed_*.deb "$MOUNT_DIR/tmp/"grub-efi-amd64-signed_*.deb; do
        [ -f "$deb" ] && dpkg -x "$deb" "$EXTRACT_DIR"
    done

    # Find signed shim (follow symlinks, skip .previous versions)
    SHIM_SRC=$(find "$EXTRACT_DIR" -name "shimx64.efi.signed*" ! -name "*.previous" 2>/dev/null | head -1)
    GRUB_SRC=$(find "$EXTRACT_DIR" -name "grubx64.efi.signed" 2>/dev/null | head -1)

    if [ -z "$SHIM_SRC" ] || [ -z "$GRUB_SRC" ]; then
        echo "ERROR: Could not find signed boot binaries"
        echo "  Shim: $SHIM_SRC"
        echo "  GRUB: $GRUB_SRC"
        ls -laR "$EXTRACT_DIR/usr/lib/" 2>/dev/null
        exit 1
    fi

    # BOOTX64.EFI = shim (UEFI spec fallback path, all firmware checks this)
    cp -L "$SHIM_SRC" "$MOUNT_DIR/boot/efi/EFI/BOOT/BOOTX64.EFI"
    # grubx64.efi = signed GRUB (shim loads this from same directory)
    cp -L "$GRUB_SRC" "$MOUNT_DIR/boot/efi/EFI/BOOT/grubx64.efi"
    log_info "  Shim: $(basename "$SHIM_SRC")"
    log_info "  GRUB: $(basename "$GRUB_SRC")"

    # Create EFI search config at /EFI/ubuntu/ (where Ubuntu's signed GRUB expects it).
    # The signed GRUB binary has prefix=/EFI/ubuntu compiled in, so it loads
    # /EFI/ubuntu/grub.cfg regardless of which directory shim loaded it from.
    # This config searches for the root partition and loads the full /boot/grub/grub.cfg.
    mkdir -p "$MOUNT_DIR/boot/efi/EFI/ubuntu"
    cat > "$MOUNT_DIR/boot/efi/EFI/ubuntu/grub.cfg" <<'EOF'
# PurpleOS EFI search config
# Finds root partition using multiple fallback methods, then loads full config.
# IMPORTANT: call configfile exactly once to avoid "recursion depth exceeded".

# Method 1: Label search (most reliable on fresh installs)
search --no-floppy --label PURPLE_ROOT --set=root

# Method 2: File search (works if label is missing/changed)
if [ -z "$root" ]; then
    search --no-floppy --file /boot/grub/grub.cfg --set=root
fi

# Method 3: SATA/SAS device probe
if [ -z "$root" ]; then
    for dev in hd0,gpt2 hd1,gpt2 hd2,gpt2; do
        if [ -f ($dev)/boot/grub/grub.cfg ]; then
            set root=$dev
            break
        fi
    done
fi

# Method 4: NVMe device probe
if [ -z "$root" ]; then
    for dev in nvme0n1,gpt2 nvme1n1,gpt2; do
        if [ -f ($dev)/boot/grub/grub.cfg ]; then
            set root=$dev
            break
        fi
    done
fi

# Load full config from root partition (exactly once)
if [ -n "$root" ]; then
    set prefix=($root)/boot/grub
    configfile ($root)/boot/grub/grub.cfg
fi

echo ""
echo "Purple Computer could not start."
echo ""
echo "The boot files were not found."
echo "This usually means installation"
echo "did not complete successfully."
echo ""
echo "Please reinstall or contact support."
echo ""
echo "(Technical: root partition not found)"
echo ""
sleep 10
EOF

    # Clean up downloaded debs and extracted files
    rm -rf "$EXTRACT_DIR" "$MOUNT_DIR/tmp/"shim-signed_*.deb "$MOUNT_DIR/tmp/"grub-efi-amd64-signed_*.deb

    # =========================================================================
    # SIZE REDUCTION: strip everything not needed for an offline kids' appliance
    # These changes apply to both the squashfs AND the golden image (2x savings).
    # This block runs LAST, after all apt operations (including boot chain setup).
    # =========================================================================

    # Remove pip (no longer needed after installing requirements)
    # Use --no-auto-remove to prevent apt from cascading into kernel packages.
    log_info "Removing pip and build tools..."
    chroot "$MOUNT_DIR" pip3 cache purge 2>/dev/null || true

    # Log what apt plans to remove (for debugging disappearing packages)
    log_info "Packages apt will remove with python3-pip:"
    chroot "$MOUNT_DIR" apt-get remove --purge -y -s python3-pip 2>/dev/null | grep "^Remv" || true

    chroot "$MOUNT_DIR" apt-get remove --purge -y --no-auto-remove python3-pip 2>/dev/null || true

    chroot "$MOUNT_DIR" apt-get clean

    # Remove apt package lists (~30-50MB, not needed on appliance)
    rm -rf "$MOUNT_DIR/var/lib/apt/lists/"*

    # Strip documentation, man pages, and lintian data (~50-80MB)
    rm -rf "$MOUNT_DIR/usr/share/doc"
    rm -rf "$MOUNT_DIR/usr/share/man"
    rm -rf "$MOUNT_DIR/usr/share/info"
    rm -rf "$MOUNT_DIR/usr/share/lintian"

    # Prune firmware: keep only what laptops need for display and sound.
    # Removes ~400MB of WiFi, Bluetooth, enterprise networking, and legacy firmware.
    # The kernel logs "firmware not found" for missing hardware and continues normally.
    log_info "Pruning firmware (keeping GPU and sound only)..."
    FIRMWARE_DIR="$MOUNT_DIR/lib/firmware"
    FIRMWARE_KEEP="$BUILD_DIR/firmware-keep"
    mkdir -p "$FIRMWARE_KEEP"

    # GPU display firmware (needed for modesetting to initialize the display)
    for dir in i915 amdgpu nvidia; do
        [ -d "$FIRMWARE_DIR/$dir" ] && mv "$FIRMWARE_DIR/$dir" "$FIRMWARE_KEEP/"
    done
    # Intel misc firmware (includes SOF audio firmware for newer laptop speakers)
    [ -d "$FIRMWARE_DIR/intel" ] && mv "$FIRMWARE_DIR/intel" "$FIRMWARE_KEEP/"
    # Keep loose files in firmware root (some drivers expect files here)
    find "$FIRMWARE_DIR" -maxdepth 1 -type f -exec mv {} "$FIRMWARE_KEEP/" \;

    # Remove everything else and restore kept firmware
    rm -rf "$FIRMWARE_DIR"/*
    mv "$FIRMWARE_KEEP"/* "$FIRMWARE_DIR/"
    rmdir "$FIRMWARE_KEEP"

    log_info "Firmware pruned. Remaining: $(du -sh "$FIRMWARE_DIR" | cut -f1)"

    # Remove networking kernel modules only. This is an offline appliance:
    # no WiFi, no Bluetooth, no ethernet.
    # We intentionally keep all other modules (GPU, sound, media, platform, etc.)
    # because they have hidden dependency chains that break on specific hardware
    # if removed (e.g., i915 depends on drivers/media/cec via drm_display_helper).
    log_info "Removing network kernel modules..."
    for kdir in "$MOUNT_DIR/lib/modules"/*/kernel; do
        rm -rf "$kdir/drivers/net"           # All network drivers (WiFi, ethernet, USB net)
        rm -rf "$kdir/drivers/bluetooth"     # Bluetooth drivers
        rm -rf "$kdir/net/bluetooth"         # Bluetooth protocol stack
        rm -rf "$kdir/net/wireless"          # Wireless stack (cfg80211, mac80211)
        rm -rf "$kdir/drivers/nfc"           # NFC/RFID
        rm -rf "$kdir/drivers/isdn"          # Legacy telecom
    done

    # Rebuild module dependency database after pruning
    chroot "$MOUNT_DIR" depmod -a "$KVER"

    # Verify critical modules can load with all their dependencies.
    # modprobe --dry-run resolves the full dependency chain and fails if
    # any required module was removed by the pruning above.
    log_info "Verifying critical kernel modules..."
    MODULES_FAILED=0
    for mod in i915 amdgpu snd_hda_intel; do
        if chroot "$MOUNT_DIR" modprobe -S "$KVER" --dry-run "$mod" 2>/dev/null; then
            log_info "  $mod: OK"
        else
            echo "ERROR: modprobe --dry-run $mod failed! A dependency was likely removed."
            echo "  Run: modprobe -v $mod  to see which module is missing."
            MODULES_FAILED=1
        fi
    done
    if [ "$MODULES_FAILED" -eq 1 ]; then
        exit 1
    fi

    # Unmount virtual filesystems BEFORE creating squashfs
    # Otherwise mksquashfs tries to include /proc, /sys, /dev (huge and slow)
    log_info "Unmounting virtual filesystems..."
    sync
    umount "$MOUNT_DIR/dev/pts" 2>/dev/null || true
    umount "$MOUNT_DIR/dev" 2>/dev/null || true
    umount "$MOUNT_DIR/sys" 2>/dev/null || true
    umount "$MOUNT_DIR/proc" 2>/dev/null || true

    # Ensure empty mountpoint directories exist (kernel needs them at boot).
    # mksquashfs -e excludes entire directory trees, so we exclude contents
    # via -wildcards instead, preserving the empty directories.
    mkdir -p "$MOUNT_DIR/dev" "$MOUNT_DIR/proc" "$MOUNT_DIR/sys"

    # Create squashfs for live boot (same root filesystem, different packaging)
    log_info "Creating live boot squashfs..."
    SQUASHFS_OUT="${BUILD_DIR}/filesystem.squashfs"
    rm -f "$SQUASHFS_OUT"
    mksquashfs "$MOUNT_DIR" "$SQUASHFS_OUT" \
        -comp zstd \
        -Xcompression-level 19 \
        -noappend \
        -wildcards \
        -e 'boot/efi' 'proc/*' 'sys/*' 'dev/*'

    # Record uncompressed size (required by casper)
    du -sx --block-size=1 "$MOUNT_DIR" | cut -f1 > "${BUILD_DIR}/filesystem.size"

    log_info "  Squashfs: $(du -h "$SQUASHFS_OUT" | cut -f1)"
    log_info "  Uncompressed: $(cat "${BUILD_DIR}/filesystem.size") bytes"

    # Unmount and detach (the EXIT trap also calls cleanup_build as a safety net)
    log_info "Cleaning up mounts..."
    cleanup_build

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
