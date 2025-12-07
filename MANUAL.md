# Purple Computer Manual

Complete reference for building, customizing, and maintaining Purple Computer installer.

**Table of Contents:**
- [Overview](#overview)
- [Build Process](#build-process)
- [FAI Configuration](#fai-configuration)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [Reference](#reference)

---

## Overview

Purple Computer uses **FAI (Fully Automatic Installation)** to create a robust, offline installer. The system:

- Downloads all packages and creates a proper APT repository (~2-5GB)
- Builds a FAI installation environment (nfsroot)
- Creates a bootable ISO with embedded repository (~3-7GB)
- Installs a minimal Debian/Ubuntu system with LVM and X11
- Configures Purple Computer application with auto-login

**Why FAI?**
- Industry-standard (used by data centers, OEMs)
- Powerful class-based configuration
- Supports LVM, RAID, complex disk layouts
- Extensive hooks for customization
- Well-documented and actively maintained

---

## Build Process

### Prerequisites

**Build machine:**
- Debian 12 (Bookworm) or Ubuntu 22.04/24.04
- 20GB free disk space
- Root access
- Internet connection (for package download)

**Time estimate:**
- Dependency install: 5 minutes
- Repository creation: 30-60 minutes (downloads ~2-5GB)
- Nfsroot build: 10-15 minutes
- ISO creation: 5-10 minutes

### Step 1: Install Dependencies

```bash
cd build-scripts
sudo ./00-install-build-deps.sh
```

**What it installs:**
- FAI tools: `fai-server`, `fai-setup-storage`, `fai-client`
- Bootloaders: `grub-pc-bin`, `grub-efi-amd64-bin`
- ISO tools: `xorriso`, `squashfs-tools`, `isolinux`, `syslinux`
- Repository tools: `dpkg-dev`, `apt-utils`
- Utilities: `debootstrap`, `rsync`, `mtools`

**What it creates:**
- `/srv/fai/` - FAI base directory
- `/opt/purple-installer/` - Build workspace

### Step 2: Create Local Repository

```bash
sudo ./01-create-local-repo.sh
```

**What it does:**
1. Reads package lists from `fai-config/package_config/*`
2. Resolves dependencies using APT
3. Downloads all `.deb` files to cache
4. Organizes packages into pool structure (`pool/main/`, `pool/contrib/`, etc.)
5. Generates repository metadata:
   - `Packages` (plain text package index)
   - `Packages.gz`, `Packages.bz2`, `Packages.xz` (compressed)
   - `Release` file with MD5Sum and SHA256 checksums

**Result:**
```
/opt/purple-installer/local-repo/mirror/
├── dists/bookworm/
│   ├── Release
│   ├── main/binary-amd64/Packages.gz
│   ├── contrib/binary-amd64/Packages.gz
│   └── non-free/binary-amd64/Packages.gz
└── pool/
    ├── main/a/alacritty/alacritty_*.deb
    ├── main/v/vim/vim_*.deb
    └── ...
```

This is a **real APT repository** - not just copied files. APT can use it natively with:
```
deb [trusted=yes] file:///path/to/mirror bookworm main contrib non-free
```

**Customization:**
- Edit `DIST` variable for Ubuntu (change `bookworm` to `jammy` or `noble`)
- Edit `SECTIONS` for Ubuntu (`main restricted universe multiverse`)
- See [guides/offline_apt_guide.md](guides/offline_apt_guide.md) for details

### Step 3: Build FAI Nfsroot

```bash
sudo ./02-build-fai-nfsroot.sh
```

**What it does:**
1. Configures FAI to use local repository
2. Creates `/etc/fai/fai.conf` with offline settings
3. Runs `fai-make-nfsroot` to create installation environment
4. Customizes nfsroot for offline operation

**Nfsroot contents:**
- Minimal Debian/Ubuntu base system
- Linux kernel and initramfs
- FAI installation tools
- LVM and partitioning utilities (parted, gdisk, lvm2)
- Grub bootloaders (both BIOS and UEFI)
- Network tools for hardware detection

**Result:** `/srv/fai/nfsroot/` (~1-2GB)

The nfsroot is a complete Linux system that runs from RAM during installation. It contains everything needed to partition disks, install packages, and configure the target system.

### Step 4: Build Bootable ISO

```bash
sudo ./03-build-iso.sh
```

**What it does:**
1. Creates squashfs from nfsroot (`filesystem.squashfs`)
2. Copies kernel and initrd from nfsroot
3. Embeds entire local repository (~2-5GB)
4. Configures ISOLINUX for BIOS boot
5. Configures GRUB for UEFI boot
6. Creates hybrid ISO (bootable from CD and USB)
7. Generates MD5 and SHA256 checksums

**Result:** `/opt/purple-installer/output/purple-computer-installer-YYYYMMDD.iso`

**ISO structure:**
```
ISO:
├── isolinux/          # BIOS boot
│   ├── isolinux.bin
│   └── isolinux.cfg
├── EFI/boot/          # UEFI boot
│   ├── bootx64.efi
│   └── grub.cfg
├── live/
│   ├── vmlinuz
│   ├── initrd.img
│   └── filesystem.squashfs
└── purple-repo/       # Complete APT repository
```

The ISO is **hybrid** - you can:
- Burn to CD/DVD
- Write to USB with `dd`: `sudo dd if=installer.iso of=/dev/sdX bs=4M`
- Boot in BIOS or UEFI mode

---

## FAI Configuration

FAI uses a **class-based** system. Each class can define:
- Disk layout (`disk_config/`)
- Package list (`package_config/`)
- Configuration scripts (`scripts/`)
- Hooks at various installation stages (`hooks/`)

### Directory Structure

```
fai-config/
├── class/10-base-classes      # Assigns classes based on hardware
├── disk_config/
│   ├── LAPTOP                 # LVM layout for laptops
│   ├── UEFI                   # UEFI-specific partitions
│   └── BIOS                   # BIOS/legacy partitions
├── package_config/
│   ├── FAIBASE                # Essential system packages
│   ├── PURPLECOMPUTER         # Purple Computer packages
│   └── MINIMAL_X              # X11 and GUI packages
├── scripts/
│   ├── PURPLECOMPUTER/
│   │   ├── 10-configure-system
│   │   ├── 20-create-user
│   │   ├── 40-custom-config
│   │   └── 50-finalize
│   └── MINIMAL_X/
│       └── 30-configure-x11
├── hooks/
│   └── instsoft.PURPLECOMPUTER
└── nfsroot.conf               # Nfsroot build config
```

### Class Assignment

**File:** `fai-config/class/10-base-classes`

This script runs early in installation and outputs class names (one per line):

```bash
echo "FAIBASE"        # Always applied
echo "DEBIAN"         # or UBUNTU
echo "AMD64"          # Architecture
echo "BOOKWORM"       # Distribution release
echo "PURPLECOMPUTER" # Purple Computer config
echo "LAPTOP"         # Laptop-specific settings
echo "MINIMAL_X"      # Install X11

# Auto-detect firmware type
if [ -d /sys/firmware/efi ]; then
    echo "UEFI"
else
    echo "BIOS"
fi
```

Classes are stored in `$LOGDIR/FAI_CLASSES` and used throughout installation.

### Disk Configuration

**LVM Layout (LAPTOP class):**

```
/dev/sda1: /boot     512MB ext4
/dev/sda2: LVM PV    Rest of disk

Volume Group: vg_system
  - root:  20GB  /
  - swap:   4GB  swap
  - home:  10GB  /home
  - var:   10GB  /var
  - tmp:    2GB  /tmp
  - (unallocated space for expansion)
```

**UEFI systems** add an ESP partition:
```
/dev/sda1: /boot/efi 512MB vfat (ESP)
/dev/sda2: /boot     512MB ext4
/dev/sda3: LVM PV    Rest
```

**Format:**
```
disk_config disk1 disklabel:gpt bootable:1 fstabkey:uuid

primary /boot     512M    ext4    rw,relatime,errors=remount-ro
primary -         0-      -       -

disk_config lvm vg:vg_system

vg_system-root    /       20G     ext4    rw,relatime,errors=remount-ro
vg_system-swap    swap    4G      swap    sw
vg_system-home    /home   10G     ext4    rw,relatime,nodev,nosuid
```

See `fai-config/disk_config/LAPTOP` for complete layout.

### Package Lists

**FAIBASE** - Essential system:
- `linux-image-amd64`, `grub-pc`, `grub-efi-amd64`
- `lvm2`, `sudo`, `vim-tiny`, `wget`, `curl`
- `firmware-linux-free`, `pciutils`, `usbutils`

**PURPLECOMPUTER** - Core packages:
- System: `systemd`, `dbus`, `udev`
- Filesystems: `e2fsprogs`, `btrfs-progs`, `ntfs-3g`
- Editors: `vim`, `nano`
- Tools: `htop`, `tmux`, `tree`, `rsync`
- Laptop: `laptop-mode-tools`, `tlp`, `acpi`
- Wireless: `wpasupplicant`, `wireless-tools`, `iw`
- Bluetooth: `bluez`, `bluez-tools`
- Development: `build-essential`, `git`, `python3`

**MINIMAL_X** - Graphical environment:
- X11: `xserver-xorg-core`, `xserver-xorg-input-all`
- Display manager: `lightdm`, `lightdm-gtk-greeter`
- Window manager: `openbox`, `obconf`
- Terminals: `alacritty`, `xterm`, `rxvt-unicode`
- Fonts: `fonts-dejavu-core`, `fonts-liberation`, `fonts-noto-*`
- Audio: `alsa-utils`, `pulseaudio`, `pavucontrol`
- Apps: `firefox-esr`, `feh`, `pcmanfm`, `zathura`

### Installation Scripts

Scripts run in numerical order within each class directory.

**PURPLECOMPUTER/10-configure-system** - System settings
- Hostname: `purplecomputer`
- Locale: `en_US.UTF-8`
- Timezone: `UTC`
- Keyboard: `us`
- Enable services: `systemd-journald`, `acpid`, `tlp`
- Configure sudo (no password for sudo group)

**PURPLECOMPUTER/20-create-user** - User account
- Create user `purple` with groups: `sudo`, `audio`, `video`, `plugdev`, `netdev`, `bluetooth`
- Default password: `purple`
- Create home directories: `Documents`, `Downloads`, `Pictures`, etc.
- Configure `.bashrc` with colors and aliases
- Configure `.profile` for PATH

**MINIMAL_X/30-configure-x11** - X11 environment
- Enable `lightdm` display manager
- Configure auto-login for user `purple`
- Create Openbox config (menu, keybindings, autostart)
- Configure `.xinitrc`, `.Xresources`
- Set up terminal colors (Gruvbox-inspired)

**PURPLECOMPUTER/40-custom-config** - Dotfiles
- Alacritty config (colors, fonts, keybindings)
- Vim config (line numbers, syntax, keybindings)
- Git config (user, aliases)
- Tmux config (prefix Ctrl+A, keybindings)
- First-boot welcome message

**PURPLECOMPUTER/50-finalize** - Final tasks
- Update initramfs
- Install GRUB (UEFI or BIOS)
- Clean package cache
- Create `/etc/purple-install-info`
- Create `/etc/motd` (message of the day)
- Create `purple-setup` helper script
- Set file permissions

### Hooks

**instsoft.PURPLECOMPUTER** - APT configuration

Runs during `instsoft` stage (after package installation begins).

Creates `/etc/apt/sources.list` pointing to offline repository:
```
deb [trusted=yes] file:///media/purple-repo bookworm main contrib non-free
```

Configures APT:
- Disable recommended/suggested packages
- Non-interactive dpkg mode
- Prefer local repository (Pin-Priority: 1000)

### FAI Variables

Available in scripts:

- `$target` - Mount point of target system (e.g., `/target`)
- `$ROOTCMD` - Prefix for commands in chroot (e.g., `chroot $target`)
- `$classes` - Space-separated list of classes
- `$LOGDIR` - FAI log directory

**Examples:**
```bash
# Create file in target
echo "purplecomputer" > $target/etc/hostname

# Run command in chroot
$ROOTCMD systemctl enable lightdm

# Check for class
if ifclass MINIMAL_X; then
    echo "Installing X11..."
fi
```

---

## Customization

### Add/Remove Packages

**Edit package lists:**
```bash
vim fai-config/package_config/PURPLECOMPUTER
# Add/remove package names (one per line)
```

**Rebuild repository:**
```bash
sudo ./01-create-local-repo.sh
sudo ./02-build-fai-nfsroot.sh  # If FAI tools need new packages
sudo ./03-build-iso.sh
```

### Change Disk Layout

**Edit disk config:**
```bash
vim fai-config/disk_config/LAPTOP
```

**Example - increase root to 40GB:**
```
vg_system-root    /       40G     ext4    rw,relatime,errors=remount-ro
```

Changes apply on next installation. No rebuild needed.

### Change Distribution

**For Ubuntu:**

1. Edit `build-scripts/01-create-local-repo.sh`:
   ```bash
   DIST="jammy"  # or noble for 24.04
   SECTIONS="main restricted universe multiverse"
   ```

2. Edit `build-scripts/02-build-fai-nfsroot.sh`:
   ```bash
   FAI_DEBOOTSTRAP="jammy file://${MIRROR_DIR}"
   ```

3. Edit `fai-config/class/10-base-classes`:
   ```bash
   echo "UBUNTU"
   echo "JAMMY"  # instead of BOOKWORM
   ```

4. Rebuild everything:
   ```bash
   sudo ./01-create-local-repo.sh
   sudo ./02-build-fai-nfsroot.sh
   sudo ./03-build-iso.sh
   ```

### Modify User Configuration

**Edit user creation script:**
```bash
vim fai-config/scripts/PURPLECOMPUTER/20-create-user
```

**Example - change username:**
```bash
USERNAME="myuser"
FULLNAME="My User"
```

**Example - change default password:**
```bash
echo "$USERNAME:mypassword" | $ROOTCMD chpasswd
```

### Add Post-Install Script

**Create new script:**
```bash
vim fai-config/scripts/PURPLECOMPUTER/60-install-purple-tui
chmod +x fai-config/scripts/PURPLECOMPUTER/60-install-purple-tui
```

**Example script:**
```bash
#!/bin/bash
set -e
error=0 ; trap 'error=$(($?>$error?$?:$error))' ERR

echo "Installing Purple TUI..."

# Copy Purple TUI to target
cp -r /path/to/purple_tui $target/opt/purple_tui

# Create systemd service
cat > $target/etc/systemd/system/purple.service <<'EOF'
[Unit]
Description=Purple Computer
After=graphical.target

[Service]
Type=simple
User=purple
ExecStart=/opt/purple_tui/run.sh

[Install]
WantedBy=graphical.target
EOF

# Enable service
$ROOTCMD systemctl enable purple

exit $error
```

Scripts run in numerical order (10, 20, 30, ...).

---

## Troubleshooting

### Build Issues

**Repository download fails:**
```bash
# Check internet connection
ping deb.debian.org

# Check APT cache
sudo apt-get update

# Check disk space
df -h /opt/purple-installer

# Partial downloads in cache
ls -lh /opt/purple-installer/local-repo/cache/downloads/
```

**Nfsroot build fails:**
```bash
# Check logs
sudo cat /var/log/fai/fai-make-nfsroot.log

# Verify local repository
ls /opt/purple-installer/local-repo/mirror/dists/bookworm/

# Try verbose mode
sudo fai-make-nfsroot -v
```

**ISO creation fails:**
```bash
# Check disk space (need ~10GB free)
df -h /opt/purple-installer

# Verify squashfs was created
ls -lh /opt/purple-installer/iso-build/live/filesystem.squashfs

# Check xorriso is installed
which xorriso
```

### Installation Issues

**Boot menu doesn't appear:**
- Verify ISO checksum matches `.md5` file
- Try different USB port
- Check BIOS/UEFI boot settings
- Try writing with different tool (Rufus, balenaEtcher, dd)

**Installation hangs:**
- Select "Installation (Verbose)" from boot menu
- Press `Alt+F2` to switch to shell
- Press `Alt+F3` to view FAI logs
- Check `/tmp/fai/` for log files

**Cannot find packages:**
- Repository not mounted correctly
- Check if `/media/purple-repo` exists during install
- Verify repository on ISO: mount ISO and check `purple-repo/` directory

**Partition fails:**
- Disk may have existing partitions
- Boot to rescue mode and manually partition
- Check disk is not in use (unmount all partitions)

**Bootloader installation fails:**
- UEFI/BIOS mismatch
- Check firmware mode in BIOS settings
- Verify ESP partition exists (UEFI) or boot flag set (BIOS)

### Post-Install Issues

**No display after boot:**
```bash
# Switch to console
Press Ctrl+Alt+F2

# Check X11 logs
journalctl -u lightdm
cat /var/log/Xorg.0.log

# Try manual X start
startx
```

**Network not working:**
```bash
# Check interface
ip link

# WiFi needs firmware
lspci | grep -i network
# May need firmware-iwlwifi or similar

# Manual network config
sudo nmtui
```

**Wrong resolution:**
```bash
# List available modes
xrandr

# Set resolution
xrandr --output HDMI-1 --mode 1920x1080
```

### Debugging FAI

**Enable verbose output:**
Boot menu → "Installation (Verbose)"

**Shell access during install:**
Press `Alt+F2` during installation

**Check class assignment:**
```bash
cat /tmp/fai/FAI_CLASSES
```

**View FAI variables:**
```bash
# During installation (Alt+F2)
echo $target
echo $classes
ls $LOGDIR
```

**Test disk config:**
```bash
# On build machine
fai-disk-config -t LAPTOP
```

**Manual FAI run:**
```bash
# Boot to rescue shell
# Partition manually, mount to /target
fai -v -N install
```

---

## Reference

### File Locations

**Build machine:**
- `/srv/fai/config/` - FAI configuration (copied from `fai-config/`)
- `/srv/fai/nfsroot/` - Installation environment (~1-2GB)
- `/opt/purple-installer/local-repo/mirror/` - APT repository (~2-5GB)
- `/opt/purple-installer/output/` - Final ISO files

**Installed system:**
- `/var/log/fai/` - Installation logs
- `/etc/purple-install-info` - Installation metadata
- `/etc/apt/sources.list` - APT configuration (points to `/media/purple-repo`)
- `/home/purple/` - User home directory

### Important Scripts

**Build:**
- `build-scripts/00-install-build-deps.sh` - Install FAI and tools
- `build-scripts/01-create-local-repo.sh` - Create APT repository
- `build-scripts/02-build-fai-nfsroot.sh` - Build installation environment
- `build-scripts/03-build-iso.sh` - Create bootable ISO

**FAI:**
- `fai-config/class/10-base-classes` - Class assignment
- `fai-config/scripts/PURPLECOMPUTER/*` - Configuration scripts
- `fai-config/hooks/instsoft.PURPLECOMPUTER` - APT setup

**Installed system:**
- `/usr/local/bin/purple-setup` - Post-install helper

### Package Counts

Approximate package counts by class:

- FAIBASE: ~20 packages
- PURPLECOMPUTER: ~60 packages
- MINIMAL_X: ~80 packages
- **Total: ~160 packages** (plus dependencies = ~500-800 packages)

### Size Estimates

- Local repository: 2-5GB
- FAI nfsroot: 1-2GB
- ISO file: 3-7GB
- Installed system: 3-5GB (without repository)

### Boot Process

1. BIOS/UEFI loads bootloader (ISOLINUX or GRUB)
2. Bootloader loads kernel and initramfs from `live/`
3. Initramfs mounts squashfs (`filesystem.squashfs`)
4. Live environment boots (FAI nfsroot)
5. FAI starts automatically (`FAI_ACTION=install`)
6. Class assignment (`class/10-base-classes`)
7. Disk partitioning (`disk_config/`)
8. Package installation (`package_config/`)
9. Configuration (`scripts/`, `hooks/`)
10. Bootloader install (`50-finalize`)
11. Reboot to installed system

### Default Credentials

**Username:** `purple`
**Password:** `purple`

**IMPORTANT:** Change password immediately after installation:
```bash
passwd
```

Or use helper:
```bash
sudo purple-setup
# Select option 1
```

### Useful Commands

**LVM management:**
```bash
# View volumes
sudo lvs
sudo vgs
sudo pvs

# Extend volume
sudo lvextend -L +10G /dev/vg_system/home
sudo resize2fs /dev/vg_system/home

# Create snapshot
sudo lvcreate -L 5G -s -n root_snapshot /dev/vg_system/root
```

**Repository management:**
```bash
# Verify repository
apt-cache policy

# List available packages
apt-cache search .

# Add online repositories
sudo vim /etc/apt/sources.list
# Uncomment online repo lines
sudo apt update
```

**System info:**
```bash
# Installation info
cat /etc/purple-install-info

# Applied classes
# (during install only)
cat /tmp/fai/FAI_CLASSES

# Disk layout
lsblk
df -h

# Boot logs
journalctl -b
```

### FAI Documentation

- FAI Project: https://fai-project.org/
- FAI Guide: https://fai-project.org/fai-guide/
- Disk config: https://fai-project.org/doc/man/fai-disk-config.html
- Setup storage: https://fai-project.org/doc/man/setup-storage.html

### Support

For issues with Purple Computer installer:
1. Check logs in `/var/log/fai/`
2. Review this manual
3. Check FAI documentation
4. Boot in verbose mode for detailed output

For issues with Purple Computer application:
- See main repository documentation
- Check `purple_tui/` source code

---

💜
