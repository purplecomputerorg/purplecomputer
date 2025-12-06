# Building Purple Computer Installer

Complete guide to building the Purple Computer FAI-based installer.

## Prerequisites

### Build Machine Requirements

- Debian 12 (Bookworm) or Ubuntu 22.04/24.04
- At least 20GB free disk space
- Root access
- Internet connection (only during build, not during installation)

### Time Requirements

- Repository download: 30-60 minutes (depending on connection speed)
- FAI nfsroot build: 10-15 minutes
- ISO creation: 5-10 minutes
- Total: ~1-2 hours

## Quick Start

```bash
# 1. Install build dependencies
cd /home/tavi/purplecomputer/build-scripts
sudo ./00-install-build-deps.sh

# 2. Create local package repository
sudo ./01-create-local-repo.sh

# 3. Build FAI installation environment
sudo ./02-build-fai-nfsroot.sh

# 4. Create bootable ISO
sudo ./03-build-iso.sh

# 5. Your ISO is ready!
ls -lh /opt/purple-installer/output/
```

## Detailed Steps

### Step 1: Install Build Dependencies

This installs FAI, debootstrap, squashfs tools, and ISO creation utilities.

```bash
sudo ./00-install-build-deps.sh
```

**What it does:**
- Installs `fai-server`, `fai-setup-storage`
- Installs `squashfs-tools`, `xorriso`, `isolinux`
- Installs GRUB bootloaders for BIOS and UEFI
- Creates directory structure in `/srv/fai` and `/opt/purple-installer`

### Step 2: Create Local Repository

Downloads all required packages and creates a complete APT repository.

```bash
sudo ./01-create-local-repo.sh
```

**What it does:**
- Reads package lists from `fai-config/package_config/*`
- Downloads all packages with dependencies
- Organizes packages into proper pool structure
- Creates repository metadata (Packages.gz, Release, etc.)
- Result: ~2-5GB repository in `/opt/purple-installer/local-repo/mirror`

**Repository structure:**
```
/opt/purple-installer/local-repo/mirror/
├── dists/
│   └── bookworm/
│       ├── main/
│       │   └── binary-amd64/
│       │       ├── Packages
│       │       ├── Packages.gz
│       │       └── Release
│       ├── contrib/
│       └── non-free/
├── pool/
│   ├── main/
│   ├── contrib/
│   └── non-free/
└── Release
```

### Step 3: Build FAI Nfsroot

Creates the live installation environment.

```bash
sudo ./02-build-fai-nfsroot.sh
```

**What it does:**
- Configures FAI to use local repository
- Runs `fai-make-nfsroot` to create installation environment
- Installs kernel, LVM tools, partitioning utilities
- Customizes for offline operation
- Result: ~1-2GB nfsroot in `/srv/fai/nfsroot`

**Nfsroot contents:**
- Linux kernel and initramfs
- FAI installation tools
- LVM, partition utilities (parted, gdisk)
- Network tools for hardware detection
- All tools needed to install the target system

### Step 4: Build Bootable ISO

Creates the final installer ISO with embedded repository.

```bash
sudo ./03-build-iso.sh
```

**What it does:**
- Creates squashfs from nfsroot
- Copies kernel and initramfs
- Embeds entire local repository
- Configures ISOLINUX (BIOS boot)
- Configures GRUB (UEFI boot)
- Creates hybrid ISO (bootable on USB and CD)
- Generates checksums
- Result: ~3-7GB ISO in `/opt/purple-installer/output`

**ISO contents:**
```
ISO:
├── isolinux/          # BIOS boot configuration
├── EFI/boot/          # UEFI boot configuration
├── live/
│   ├── vmlinuz        # Linux kernel
│   ├── initrd.img     # Initial ramdisk
│   └── filesystem.squashfs  # FAI nfsroot
└── purple-repo/       # Complete local repository
    ├── dists/
    └── pool/
```

## Writing to USB

### Linux

```bash
# Find USB device
lsblk

# Write ISO (replace sdX with your device)
sudo dd if=purple-computer-installer-*.iso of=/dev/sdX bs=4M status=progress && sync

# Verify
sudo dd if=/dev/sdX bs=4M count=1000 | md5sum
```

### macOS

```bash
# Find USB device
diskutil list

# Unmount (replace diskN)
diskutil unmountDisk /dev/diskN

# Write ISO
sudo dd if=purple-computer-installer-*.iso of=/dev/rdiskN bs=4m && sync

# Eject
diskutil eject /dev/diskN
```

### Windows

Use one of these tools:
- **Rufus** (recommended): Select DD Image mode
- **balenaEtcher**: Automatic detection
- **Win32DiskImager**: Classic tool

## Installation Process

1. **Boot from USB/CD**
   - BIOS: Set USB/CD as first boot device
   - UEFI: Select USB/CD from boot menu

2. **Automatic Installation**
   - Boot menu appears (5 second timeout)
   - Default: Automated Installation
   - Partitions disk with LVM layout
   - Installs packages from embedded repository
   - Configures system, creates user
   - Installs bootloader

3. **First Boot**
   - System reboots automatically
   - LightDM auto-login as 'purple' user
   - Minimal X11 + Openbox environment
   - Welcome message displayed
   - Default password: 'purple' (CHANGE THIS!)

## Customization

### Change Distribution

Edit these files:
- `build-scripts/01-create-local-repo.sh`: Change `DIST` variable
- `build-scripts/02-build-fai-nfsroot.sh`: Change `FAI_DEBOOTSTRAP`
- `fai-config/class/10-base-classes`: Change distribution class

### Add/Remove Packages

Edit package lists in `fai-config/package_config/`:
- `FAIBASE`: Essential system packages
- `PURPLECOMPUTER`: Purple Computer-specific packages
- `MINIMAL_X`: X11 and GUI packages

After changes, rebuild repository:
```bash
sudo ./01-create-local-repo.sh
```

### Modify Disk Layout

Edit `fai-config/disk_config/LAPTOP` to change:
- Partition sizes
- LVM volume layout
- Filesystem types
- Mount options

### Customize Configuration

Edit scripts in `fai-config/scripts/PURPLECOMPUTER/`:
- `10-configure-system`: System settings
- `20-create-user`: User creation and shell config
- `30-configure-x11`: X11 and desktop environment
- `40-custom-config`: Dotfiles and applications
- `50-finalize`: Final setup and bootloader

## Troubleshooting

### Build Failures

**Repository download fails:**
- Check internet connection
- Try running `apt-get update` manually
- Check `/opt/purple-installer/local-repo/cache/` for partial downloads

**Nfsroot build fails:**
- Check `/var/log/fai/fai-make-nfsroot.log`
- Ensure local repository is complete
- Try: `sudo fai-make-nfsroot -v` for verbose output

**ISO creation fails:**
- Check disk space (need ~10GB free)
- Verify squashfs was created
- Check for error messages in xorriso output

### Installation Issues

**Boot menu doesn't appear:**
- Try "Installation (Verbose)" option
- Check BIOS/UEFI boot settings
- Verify ISO checksum matches

**Installation hangs:**
- Select "Installation (Verbose)" from boot menu
- Press Alt+F2 to see detailed logs
- Check for hardware compatibility issues

**Cannot find packages:**
- Repository may not be mounted correctly
- Check `/media/purple-repo` exists during install
- Verify repository metadata is complete

## Testing

### Test in Virtual Machine

```bash
# Using QEMU (BIOS boot)
qemu-system-x86_64 -cdrom purple-computer-installer-*.iso -boot d -m 2048

# Using QEMU (UEFI boot)
qemu-system-x86_64 -cdrom purple-computer-installer-*.iso -boot d -m 2048 \
    -bios /usr/share/ovmf/OVMF.fd

# Using VirtualBox
VBoxManage createvm --name "PurpleTest" --register
VBoxManage modifyvm "PurpleTest" --memory 2048 --vram 16
VBoxManage storagectl "PurpleTest" --name "IDE" --add ide
VBoxManage storageattach "PurpleTest" --storagectl "IDE" --port 0 --device 0 \
    --type dvddrive --medium purple-computer-installer-*.iso
VBoxManage startvm "PurpleTest"
```

## Directory Reference

```
/home/tavi/purplecomputer/
├── fai-config/              # FAI configuration
│   ├── class/              # Class definitions
│   ├── disk_config/        # Partition layouts
│   ├── package_config/     # Package lists
│   ├── scripts/            # Installation scripts
│   ├── hooks/              # FAI hooks
│   └── files/              # Config files to copy
└── build-scripts/          # Build automation
    ├── 00-install-build-deps.sh
    ├── 01-create-local-repo.sh
    ├── 02-build-fai-nfsroot.sh
    └── 03-build-iso.sh

/srv/fai/
├── config/                 # FAI config (copied from fai-config/)
└── nfsroot/                # Installation environment

/opt/purple-installer/
├── local-repo/             # Package repository
│   ├── mirror/            # APT repository structure
│   └── cache/             # Build cache
├── iso-build/             # Temporary ISO build directory
└── output/                # Final ISO files
```

## Support

For issues or questions:
- Check logs in `/var/log/fai/`
- Review this documentation
- Check FAI documentation: https://fai-project.org/

## License

Purple Computer is open source software.
FAI is licensed under GPL v2.
