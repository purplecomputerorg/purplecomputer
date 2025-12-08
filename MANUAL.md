# Purple Computer Manual

Complete reference for building, installing, and maintaining Purple Computer.

**Table of Contents:**
- [Overview](#overview)
- [Installer Architecture](#installer-architecture)
- [Build Process](#build-process)
- [Installation](#installation)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)

---

## Overview

Purple Computer turns old laptops into calm, creative tools for kids. The installer boots from USB, writes a pre-built Ubuntu Noble Numbat disk image to the internal drive, and reboots into a minimal TUI environment.

**Key Facts:**
- **Installed OS:** Ubuntu 24.04 LTS (Noble Numbat) with custom TUI application
- **Installer Method:** Direct disk imaging (no apt, no package installation during setup)
- **Boot Medium:** USB stick (hybrid ISO, BIOS and UEFI compatible)
- **Installation Time:** 10-20 minutes (mostly disk write time)

---

## Installer Architecture

### Design Philosophy

The PurpleOS installer is built for **simplicity and reliability**. It eliminates common failure modes (module ABI mismatches, apt dependency hell, network requirements) by using a pre-built system image and minimal custom kernel.

### How It Works

1. **Boot:** USB stick loads custom Linux kernel with built-in drivers
2. **Detect:** Initramfs finds internal disk (SATA, NVMe, or legacy IDE)
3. **Write:** Decompress and write Ubuntu Noble image to disk (~4GB)
4. **Bootloader:** Install GRUB for BIOS or UEFI systems
5. **Reboot:** System boots into installed Ubuntu + Purple TUI

**No package manager runs during installation.** The installer writes a complete, pre-built Ubuntu system image directly to disk.

### Custom Kernel (Installer Only)

The installer uses a **custom Linux kernel (6.8.12)** with all essential storage and filesystem drivers compiled in:

- USB controllers (xhci, ehci, usb-storage, uas)
- SATA controllers (ahci, ata_piix for older ThinkPads)
- NVMe (modern SSDs)
- Filesystems (ext4, vfat)

**This kernel is only used during installation.** The installed OS runs Ubuntu's standard kernel.

#### Why a Custom Kernel?

The previous approach attempted to load Ubuntu kernel modules at runtime. This repeatedly failed due to:

- ABI mismatches between kernel and modules
- Compressed `.ko.zst` modules that wouldn't load
- Missing dependencies or incorrect load order
- CD-ROM mounting logic not used on real hardware
- Initramfs scripts designed for Ubuntu's live ISO environment (casper/live)

By compiling all drivers into the kernel (`CONFIG_*=y`), the installer boots deterministically on diverse laptop hardware without runtime module loading.

#### Are We Still Installing Ubuntu?

**Yes.** Nothing about the installed OS changes.

The installer boots a small, purpose-built environment, writes a **pre-built Ubuntu Noble Numbat image** to the internal disk, installs GRUB, and reboots. The final running system is 100% Ubuntu (plus our custom TUI application).

The installer kernel is just a tool—it is not the kernel the end user runs.

### Why Not Subiquity or FAI?

Subiquity and FAI (Fully Automatic Installation) are powerful but designed for different use cases:

- They expect a **full apt repository** with metadata and dependency resolution
- They require package-based installation, not raw image deployment
- They assume network availability or mirror configuration
- They are tightly coupled to Ubuntu's stock initramfs and module layout
- They introduce significant complexity and fragile points of failure

For an **offline, deterministic, one-click installation** intended for non-technical users and aging hardware, these systems are overkill.

Our approach eliminates apt entirely from the installation flow.

### Comparison to Cloud Images

Cloud providers (AWS, GCP, Azure) supply:

- Standardized virtual hardware
- A known kernel and module set
- Guaranteed driver availability

**Cloud providers give you the kernel.** We must supply our own installer kernel that supports unpredictable real hardware without relying on Ubuntu's module system.

Once Ubuntu is installed, the system boots the stock Ubuntu kernel—exactly like cloud images.

---

## Build Process

### Prerequisites

**Build machine:**
- Docker installed and running
- 20GB free disk space
- Internet connection (for downloads)
- Any OS (Linux, macOS, NixOS)

**Time estimate:**
- Kernel build: 10-30 minutes (first time only, cached after)
- Golden image: 10-15 minutes
- Initramfs: 1-2 minutes
- Installer rootfs: 5-10 minutes
- ISO creation: 5-10 minutes
- **Total: 30-60 minutes (first build), 10-20 minutes (subsequent)**

### Quick Start

```bash
cd build-scripts
./build-in-docker.sh
```

This builds everything in Docker and outputs the ISO to `/opt/purple-installer/output/`.

**Resume from a specific step:**
```bash
./build-in-docker.sh 2  # Skip kernel and golden image, start from initramfs
```

### Build Pipeline (5 Steps)

#### Step 0: Build Custom Kernel

**Script:** `00-build-custom-kernel.sh`

Downloads Linux 6.8.12 source from kernel.org, applies PurpleOS driver configuration, and compiles kernel with built-in drivers.

**Output:** `vmlinuz-purple` (8-12 MB)

**What's built in:**
- USB: xhci-hcd, ehci-hcd, usb-storage, uas
- SATA: ahci, ata_piix (for older Intel chipsets)
- NVMe: nvme-core, nvme
- Filesystems: ext4, vfat
- Block: loop device, partition tables (GPT/MBR)
- EFI: UEFI boot support

See `build-scripts/kernel-config-fragment.config` for full annotated configuration.

#### Step 1: Build Golden Image

**Script:** `01-build-golden-image.sh`

Creates a complete Ubuntu Noble Numbat system as a 4GB disk image using `debootstrap`.

**Output:** `purple-os.img.zst` (~1.5 GB compressed)

**Contents:**
- Ubuntu 24.04 minimal base
- Standard Ubuntu kernel (linux-image-generic)
- GRUB bootloader
- System utilities (sudo, vim, less)

This is the system that gets written to the target laptop's internal disk.

#### Step 2: Build Initramfs

**Script:** `02-build-initramfs.sh`

Creates a minimal initramfs with BusyBox and boot logic.

**Output:** `initrd.img` (1-2 MB)

**Contents:**
- Statically-compiled BusyBox
- `/init` script (device detection, mounts installer rootfs)
- No kernel modules (all drivers built into kernel)

**Boot flow:**
1. Mount proc, sys, dev
2. Wait 3 seconds for USB/SATA/NVMe enumeration
3. Find partition labeled `PURPLE_INSTALLER`
4. Mount USB partition
5. Loop-mount `installer.ext4`
6. Switch root and execute `install.sh`

#### Step 3: Build Installer Rootfs

**Script:** `03-build-installer-rootfs.sh`

Creates the installer environment that runs `install.sh`.

**Output:** `installer.ext4` (2-3 GB)

**Contents:**
- Minimal Ubuntu environment (debootstrap)
- Installation tools (zstd, gdisk, grub, dosfstools)
- Compressed golden image (`purple-os.img.zst`)
- Installation script (`install.sh`)

#### Step 4: Build ISO

**Script:** `04-build-iso.sh`

Combines kernel, initramfs, and installer rootfs into a hybrid bootable ISO.

**Output:** `purple-installer-YYYYMMDD.iso` (3-5 GB)

**ISO structure:**
```
purple-installer.iso
├── boot/
│   ├── vmlinuz             # Custom kernel
│   ├── initrd.img          # Minimal initramfs
│   └── installer.ext4      # Installer environment
├── isolinux/               # BIOS boot
│   ├── isolinux.bin
│   └── isolinux.cfg
└── EFI/boot/               # UEFI boot
    ├── bootx64.efi
    └── grub.cfg
```

The ISO is **hybrid**—bootable from USB stick or optical media, BIOS or UEFI.

---

## Installation

### Writing to USB

**Linux/macOS:**
```bash
sudo dd if=/opt/purple-installer/output/purple-installer-*.iso \
    of=/dev/sdX bs=4M status=progress conv=fsync
```

Replace `/dev/sdX` with your USB device (check with `lsblk`).

**Windows:**
Use [balenaEtcher](https://www.balena.io/etcher/) or [Rufus](https://rufus.ie/).

### Booting

1. Insert USB stick into target laptop
2. Enter BIOS/UEFI boot menu (usually F12, F2, Del, or Esc during startup)
3. Select USB device
4. System boots into installer automatically

### Installation Process

**Automatic installation (10-20 minutes):**

1. Kernel boots (custom kernel with built-in drivers)
2. Initramfs finds internal disk (first non-USB disk)
3. Wipes partition table and creates GPT partitions:
   - `/dev/sdX1`: EFI system partition (512 MB, vfat)
   - `/dev/sdX2`: Root partition (rest of disk, ext4)
4. Decompresses and writes golden image to root partition
5. Installs GRUB bootloader (UEFI or BIOS)
6. Reboots

**No user interaction required.** The entire process is automated.

### First Boot

**Default credentials:**
- Username: `purple`
- Password: `purple`

**IMPORTANT:** Change password immediately:
```bash
passwd
```

---

## Customization

### Modify Golden Image

The golden image is built in step 1. To customize the installed OS:

**Edit:** `build-scripts/01-build-golden-image.sh`

**Examples:**

Add packages during debootstrap:
```bash
debootstrap \
    --include=linux-image-generic,grub-efi-amd64,systemd,sudo,vim-tiny,neofetch \
    noble "$MOUNT_DIR" http://archive.ubuntu.com/ubuntu
```

Create additional users:
```bash
chroot "$MOUNT_DIR" useradd -m -s /bin/bash myuser
echo "myuser:password" | chroot "$MOUNT_DIR" chpasswd
```

Install custom software:
```bash
cp -r /path/to/purple_tui "$MOUNT_DIR/opt/"
chroot "$MOUNT_DIR" systemctl enable purple-tui
```

**Rebuild:**
```bash
./build-in-docker.sh 1  # Rebuild from step 1 (skip kernel build)
```

### Modify Kernel Drivers

If the installer doesn't boot on specific hardware, you may need to add drivers.

**Edit:** `build-scripts/kernel-config-fragment.config`

**Example—add Intel wireless driver:**
```makefile
# Intel WiFi (iwlwifi)
CONFIG_IWLWIFI=y
CONFIG_IWLMVM=y
```

**Rebuild:**
```bash
./build-in-docker.sh 0  # Rebuild kernel
./build-in-docker.sh 4  # Rebuild ISO
```

### Change Partition Layout

The installer creates a simple two-partition layout (EFI + root). To customize:

**Edit:** `build-scripts/install.sh`

**Example—add swap partition:**
```bash
# After line 40 (partition creation)
sgdisk -n 3:0:+4G -t 3:8200 -c 3:"SWAP" /dev/$TARGET

# After line 44 (root write)
mkswap /dev/${TARGET}3
```

---

## Troubleshooting

### Build Issues

**"ERROR: busybox not found"**

Install busybox-static in Docker container:
```dockerfile
# Add to build-scripts/Dockerfile
RUN apt-get install -y busybox-static
```

**"Kernel build fails: missing bc"**

Install kernel build dependencies:
```dockerfile
# Add to build-scripts/Dockerfile
RUN apt-get install -y build-essential bc bison flex libelf-dev libssl-dev
```

**"No space left on device"**

Free up space or use larger disk:
```bash
df -h /opt/purple-installer  # Check usage
du -sh /opt/purple-installer/build/*  # Find large files
```

### Boot Issues

**"ERROR: Cannot find PurpleOS installer partition"**

The initramfs can't detect the USB stick. Causes:

- USB stick wasn't written correctly
- Partition label is missing
- USB controller not supported by kernel

**Solutions:**
```bash
# Verify partition label
sudo blkid  # Should show LABEL="PURPLE_INSTALLER"

# Re-write USB stick
sudo dd if=purple-installer.iso of=/dev/sdX bs=4M status=progress

# Try different USB port (USB 2.0 ports often more reliable)
```

**Kernel doesn't boot (black screen)**

Possible causes:

- Missing graphics driver in kernel
- Incompatible BIOS/UEFI settings

**Solutions:**
```bash
# Add nomodeset to kernel command line
# Edit build-scripts/04-build-iso.sh, line 84:
APPEND initrd=/boot/initrd.img quiet nomodeset

# Check BIOS settings
- Disable Secure Boot
- Enable Legacy Boot (for BIOS)
- Enable CSM (Compatibility Support Module)
```

**No /dev/sdX devices detected**

USB/SATA drivers aren't loaded. This shouldn't happen with the custom kernel, but if it does:

```bash
# Verify kernel config
grep "=y" /opt/purple-installer/build/kernel-config-purple | grep -E "USB|SATA|NVME"

# Should see:
# CONFIG_USB=y
# CONFIG_USB_XHCI_HCD=y
# CONFIG_SATA_AHCI=y
# CONFIG_NVME_CORE=y
```

**Kernel Panic**

A kernel panic indicates a critical error during boot. The kernel will display a panic message and halt.

**Common causes:**
- Missing or misconfigured essential drivers (root filesystem, storage)
- Hardware incompatibility
- Corrupted kernel image
- Missing initramfs or init script errors
- Memory issues (bad RAM)

**Debugging steps:**

1. **Capture the panic message:**
   - Take a photo of the screen showing the panic
   - Look for the last function call before panic (often in brackets like `[function_name+0x123]`)
   - Note any "not syncing" or "Attempted to kill init" messages

2. **Add kernel debug parameters:**

   Edit `build-scripts/04-build-iso.sh` to add debug options to the kernel command line:

   ```bash
   # For ISOLINUX (BIOS boot), around line 84:
   APPEND initrd=/boot/initrd.img debug ignore_loglevel earlyprintk=vga,keep

   # For GRUB (UEFI boot), around line 106:
   linux /boot/vmlinuz debug ignore_loglevel earlyprintk=vga,keep
   ```

   These options provide verbose output during boot, showing where the panic occurs.

3. **Test with minimal kernel parameters:**

   Remove all optional parameters to isolate the issue:

   ```bash
   # Minimal boot line (ISOLINUX)
   APPEND initrd=/boot/initrd.img

   # Minimal boot line (GRUB)
   linux /boot/vmlinuz
   initrd /boot/initrd.img
   ```

4. **Check for missing drivers:**

   If panic mentions "VFS: Unable to mount root fs" or "not syncing: No working init found":

   ```bash
   # Verify initramfs is present and correct
   file /opt/purple-installer/build/initrd.img
   # Should show: gzip compressed data

   # Extract and check init script exists
   mkdir -p /tmp/initrd-check
   cd /tmp/initrd-check
   zcat /opt/purple-installer/build/initrd.img | cpio -i
   ls -la init  # Should exist and be executable

   # Verify BusyBox is present
   ls -la bin/busybox
   ```

5. **Enable serial console for detailed logs:**

   If you have access to serial port or can use QEMU/VirtualBox for testing:

   ```bash
   # Add to kernel command line
   console=ttyS0,115200 console=tty0

   # In QEMU, capture output:
   qemu-system-x86_64 -serial file:boot.log -cdrom purple-installer.iso
   ```

6. **Test kernel configuration:**

   Verify critical drivers are enabled:

   ```bash
   grep "CONFIG_BLK_DEV=y" /opt/purple-installer/build/kernel-config-purple
   grep "CONFIG_EXT4_FS=y" /opt/purple-installer/build/kernel-config-purple
   grep "CONFIG_PROC_FS=y" /opt/purple-installer/build/kernel-config-purple
   grep "CONFIG_SYSFS=y" /opt/purple-installer/build/kernel-config-purple
   grep "CONFIG_DEVTMPFS=y" /opt/purple-installer/build/kernel-config-purple
   ```

   All should return `=y`. If not, the kernel config fragment wasn't applied correctly.

7. **Common panic messages and solutions:**

   | Panic Message | Likely Cause | Solution |
   |---------------|--------------|----------|
   | "VFS: Unable to mount root fs" | Missing filesystem driver or initramfs not found | Verify CONFIG_EXT4_FS=y and initrd.img exists |
   | "Attempted to kill init" | /init script failed or doesn't exist | Check initramfs contains /init and is executable |
   | "No working init found" | Init path wrong or BusyBox missing | Verify BusyBox at /bin/busybox in initramfs |
   | "end Kernel panic - not syncing" | Generic kernel failure | Enable debug params above, check for earlier error messages |
   | "Kernel panic - not syncing: Fatal exception" | Hardware incompatibility or driver bug | Try `nomodeset`, disable specific drivers, test on different hardware |

8. **Rebuild with conservative options:**

   If panic persists, try disabling advanced features:

   ```bash
   # Edit build-scripts/kernel-config-fragment.config
   # Comment out these lines:
   # CONFIG_NVME_MULTIPATH=y
   # CONFIG_DM_CRYPT=y
   # CONFIG_ACPI=y  # Only as last resort

   # Rebuild kernel
   ./build-in-docker.sh 0
   ./build-in-docker.sh 4
   ```

9. **Test on known-good hardware:**

   If available, test the same USB stick on a different laptop to isolate whether the issue is:
   - Hardware-specific (original laptop incompatibility)
   - Build issue (affects all hardware)

10. **Last resort—use Ubuntu's kernel for testing:**

    To quickly test if the issue is kernel-specific:

    ```bash
    # Extract Ubuntu's kernel from golden image for comparison
    # (Not recommended for production—only for debugging)

    # Mount golden image
    LOOP=$(losetup -f --show /opt/purple-installer/build/purple-os.img)
    mkdir -p /tmp/golden
    mount ${LOOP}p2 /tmp/golden

    # Copy Ubuntu kernel
    cp /tmp/golden/boot/vmlinuz-* /tmp/test-vmlinuz

    # Test this kernel with same initramfs
    # If this boots, the issue is in the custom kernel config
    ```

**When to ask for help:**

If you've tried the above and still get kernel panics:

1. Capture the full panic output (photo or serial log)
2. Note the hardware (laptop model, CPU, disk type)
3. Share the kernel config: `/opt/purple-installer/build/kernel-config-purple`
4. Share the panic message and any earlier errors visible on screen

### Installation Issues

**"No target disk found"**

The installer couldn't find an internal disk (all disks appear as USB).

**Solution:**
Manually specify target in `install.sh`:
```bash
# Edit build-scripts/install.sh, line 24:
TARGET="sda"  # Or nvme0n1, vda, etc.
```

**Installation hangs during disk write**

- Bad disk sectors
- Failing hard drive
- USB stick interference

**Check:**
```bash
# Boot Ubuntu live USB separately
# Run disk check
sudo badblocks -v /dev/sda

# Check SMART status
sudo smartctl -a /dev/sda
```

**GRUB installation fails**

UEFI/BIOS mismatch or partition issues.

**Check:**
- Booted in UEFI mode but trying to install BIOS GRUB (or vice versa)
- ESP partition not formatted as vfat
- Boot flag not set on correct partition

### Post-Install Issues

**System boots to grub rescue prompt**

GRUB installation failed or disk UUID changed.

**Solution:**
```bash
# Boot from Ubuntu live USB
# Mount target system
sudo mount /dev/sdX2 /mnt
sudo mount /dev/sdX1 /mnt/boot/efi

# Reinstall GRUB
sudo grub-install --target=x86_64-efi --efi-directory=/mnt/boot/efi \
    --boot-directory=/mnt/boot /dev/sdX

# Update GRUB config
sudo chroot /mnt update-grub
```

**No network connectivity**

Laptop may need proprietary firmware for WiFi.

**Check:**
```bash
# Identify WiFi card
lspci | grep -i network

# Common fixes
sudo apt update
sudo apt install firmware-iwlwifi      # Intel
sudo apt install firmware-realtek      # Realtek
sudo apt install firmware-atheros      # Atheros

# Reboot
sudo reboot
```

**Screen resolution wrong**

X11 may not detect native resolution.

**Fix:**
```bash
# List available modes
xrandr

# Set resolution
xrandr --output HDMI-1 --mode 1920x1080

# Make permanent (add to ~/.xprofile)
echo "xrandr --output HDMI-1 --mode 1920x1080" >> ~/.xprofile
```

---

## Reference

### File Locations

**Build system:**
```
/opt/purple-installer/
├── build/
│   ├── vmlinuz-purple           # Custom kernel
│   ├── kernel-config-purple     # Kernel .config
│   ├── initrd.img               # Initramfs
│   ├── purple-os.img            # Golden image (uncompressed)
│   ├── purple-os.img.zst        # Golden image (compressed)
│   └── installer.ext4           # Installer environment
└── output/
    └── purple-installer-YYYYMMDD.iso  # Final ISO
```

**Source files:**
```
build-scripts/
├── 00-build-custom-kernel.sh       # Kernel build
├── 01-build-golden-image.sh        # Ubuntu base system
├── 02-build-initramfs.sh           # Minimal initramfs
├── 03-build-installer-rootfs.sh    # Installer environment
├── 04-build-iso.sh                 # Hybrid ISO
├── build-all.sh                    # Orchestrator
├── build-in-docker.sh              # Docker wrapper
├── kernel-config-fragment.config   # Kernel driver config
├── install.sh                      # Installation script
└── config.sh                       # Build configuration
```

**Installed system:**
```
/boot/
├── vmlinuz-*           # Ubuntu kernel (not custom kernel)
├── initrd.img-*        # Ubuntu initramfs
└── grub/               # GRUB config

/home/purple/           # User home directory
/etc/hostname           # purplecomputer
```

### Hardware Compatibility

**Tested configurations:**
- ThinkPad T/X/L series (2010-2020)
- Dell Latitude (2012+)
- HP EliteBook (2013+)
- MacBook Air/Pro (2013+, Intel models)

**Supported storage:**
- SATA (AHCI controller)
- SATA (legacy IDE/PATA via ata_piix)
- NVMe (modern SSDs)
- USB (for installer boot)

**Known incompatible:**
- Very old laptops (<2010) may need IDE drivers
- Some MacBooks (2016+ with T2 chip)
- Exotic RAID controllers

### Size Reference

| Component | Size |
|-----------|------|
| Custom kernel | 8-12 MB |
| Initramfs | 1-2 MB |
| Golden image (compressed) | 1.5 GB |
| Installer rootfs | 2-3 GB |
| Final ISO | 3-5 GB |
| Installed system | 3-5 GB |

### Boot Flow Diagram

```
USB Boot (BIOS/UEFI)
  ↓
Bootloader (ISOLINUX/GRUB)
  ↓
Load Custom Kernel (vmlinuz-purple)
  ├─ All drivers built-in (no module loading)
  ├─ USB controllers (xhci, ehci)
  ├─ SATA controllers (ahci, ata_piix)
  ├─ NVMe (nvme-core, nvme)
  └─ Filesystems (ext4, vfat)
  ↓
Unpack Initramfs (initrd.img)
  ↓
Execute /init Script
  ├─ Mount proc, sys, dev
  ├─ Wait for device enumeration
  ├─ Find partition labeled PURPLE_INSTALLER
  ├─ Mount USB partition
  ├─ Loop-mount installer.ext4
  └─ switch_root /newroot /install.sh
  ↓
Installation (install.sh)
  ├─ Detect target disk (first non-USB)
  ├─ Wipe partition table (sgdisk -Z)
  ├─ Create GPT partitions (EFI + root)
  ├─ Decompress purple-os.img.zst → /dev/sdX2
  ├─ Install GRUB (--target=x86_64-efi or i386-pc)
  └─ Reboot
  ↓
First Boot (Installed System)
  └─ Ubuntu 24.04 + Purple TUI
```

### Documentation

- **README.md** - Quick start and overview
- **MANUAL.md** - This file (complete reference)
- **guides/module-free-architecture.md** - Technical deep-dive on installer design

---

💜
