# Purple Computer Manual

Complete reference for building, installing, and maintaining Purple Computer.

**Table of Contents:**
- [Overview](#overview)
- [Installer Architecture](#installer-architecture)
  - [Screen Size & Font Calculation](#screen-size--font-calculation)
  - [Graphics Stack](#graphics-stack-installed-system)
- [Build Process](#build-process)
- [Installation](#installation)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)

---

## Overview

Purple Computer turns old laptops into calm, creative tools for kids. The installer boots from USB, writes a pre-built Ubuntu disk image to the internal drive, and reboots into a minimal TUI environment.

**Key Facts:**
- **Installed OS:** Ubuntu 24.04 LTS (Noble Numbat) with custom TUI application
- **Installer Method:** Direct disk imaging (no apt, no package installation during setup)
- **Boot Medium:** USB stick (hybrid ISO, BIOS and UEFI compatible)
- **Installation Time:** 10-20 minutes (mostly disk write time)
- **Secure Boot:** Supported out of the box

**Important:** There are **two separate systems** involved:
1. **USB Installer** - A temporary Ubuntu live environment that copies the system to disk, then is never used again
2. **Installed System** - A normal Ubuntu 24.04 system that kids use every day

These are built differently and serve different purposes. See [guides/architecture-overview.md](guides/architecture-overview.md) for a detailed explanation.

---

## Installer Architecture

### Design Philosophy

The PurpleOS installer is built for **simplicity, reliability, and broad hardware compatibility**. It uses Ubuntu's stock kernel and signed boot chain to work across diverse laptop hardware including Surface, Dell, HP, and ThinkPad devices.

### How It Works

1. **Boot:** USB stick loads Ubuntu's signed boot chain (shim → GRUB → kernel)
2. **Initramfs:** Kernel loads initramfs with our injected hook script
3. **Hook Runs:** Our script in `/scripts/init-top/` runs before casper
4. **Detect:** Hook finds payload on boot device and runs installer
5. **Write:** Decompress and write pre-built Ubuntu image to internal disk
6. **Bootloader:** Setup UEFI boot entries with multi-layer fallback
7. **Reboot:** System boots into installed Ubuntu + Purple TUI

**No package manager runs during installation.** The installer writes a complete, pre-built Ubuntu system image directly to disk. The squashfs is never mounted—we intercept boot before casper runs.

### Initramfs Injection Architecture

The installer intercepts boot BEFORE Ubuntu's live system starts:

```
USB Boot Flow
═══════════════════════════════════════════════════════════

UEFI Firmware
    │
    ▼
shimx64.efi (Microsoft-signed)
    │
    ▼
grubx64.efi (Canonical-signed)
    │
    ▼
vmlinuz + initrd (Ubuntu kernel + modified initramfs)
    │
    ▼
initramfs runs init-top scripts
    │
    ├── [Purple hook] Check for /purple/install.sh on boot device
    │       │
    │       ├── If found: Run installer, reboot
    │       │
    │       └── If not found: Continue to casper (normal Ubuntu boot)
    │
    ▼
(Only reaches here if payload missing)
Casper mounts squashfs → Normal Ubuntu live boot
```

**Key insight:** Our installer runs in initramfs, before casper ever mounts the squashfs. The squashfs and Ubuntu's live system are never touched.

### Why Ubuntu's Boot Stack?

Previous versions used a custom Linux kernel with all drivers built-in. While elegant, this approach failed on diverse hardware due to:

- **Platform-Specific Quirks:** Modern laptops require ACPI quirks and platform drivers beyond basic storage support
- **Secure Boot:** Custom kernels aren't signed by Microsoft's UEFI CA
- **Maintenance Burden:** Debugging kernel configs per laptop model is not sustainable

Ubuntu's stock kernel handles these automatically:

- **Surface:** ACPI quirks, Type Cover drivers
- **Dell/HP:** WMI drivers, Thunderbolt quirks
- **ThinkPad:** ThinkPad ACPI, TrackPoint drivers
- **Generic:** EFI framebuffer, NVMe APST quirks

### Screen Size & Font Calculation

Purple Computer displays a fixed 100×28 character viewport that targets approximately **10×6 inches** of physical screen space. This provides a consistent experience for kids across different laptop sizes.

#### How It Works

The font size is calculated at X11 startup by `calc_font_size.py`:

1. **Check cache** (`/var/cache/purple/font_probe.cache`) — instant if valid
2. **Probe Alacritty** — launch once at 18pt to measure actual cell dimensions
3. **Get screen info** — resolution (pixels) and physical size (mm) from xrandr
4. **Calculate target**:
   - If physical size known: target 10" wide viewport (254mm)
   - If physical size unknown: fill 85% of screen width
   - Always cap at 85% to ensure purple border is visible
5. **Apply safety margin** (5%) and clamp to 10-48pt range

#### Behavior by Screen Size

| Screen | Resolution | Physical Width | Viewport Behavior |
|--------|------------|----------------|-------------------|
| 10" laptop | 1280×800 | ~220mm | Fills ~85% (max cap) |
| 13" laptop | 1920×1080 | ~290mm | Fills ~87% → capped to 85% |
| 15" laptop | 1920×1080 | ~340mm | Fills ~75% (targets 10") |
| Surface 13.8" | 2304×1536 | ~267mm | Fills ~85% (max cap) |

#### Fallback Behavior

Every step has a fallback to ensure Purple always starts:

- **Cache corrupt/missing**: Re-probe Alacritty (adds ~1-2s to first boot)
- **Probe fails**: Use 16pt (guaranteed to fit 1280×800)
- **xrandr fails**: Use fallback resolution 1366×768

#### Cache

Probe results are cached per-resolution at `/var/cache/purple/font_probe.cache`. Format:
```
2304x1536:18:11:22
# resolution:probe_pt:cell_w:cell_h
```

The cache is automatically invalidated if screen resolution changes.

#### Manual Override

To force a specific font size, edit `/home/purple/.xinitrc`:
```bash
# Replace the FONT_SIZE= line with:
FONT_SIZE=22.0
```

---

### Graphics Stack (Installed System)

The installed Purple Computer uses X11 with a deliberately minimal graphics configuration designed for maximum hardware compatibility.

#### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Purple TUI                           │
│                   (Alacritty terminal)                  │
├─────────────────────────────────────────────────────────┤
│              Matchbox Window Manager                    │
├─────────────────────────────────────────────────────────┤
│                    X.Org Server                         │
│              (modesetting driver only)                  │
├─────────────────────────────────────────────────────────┤
│        Mesa + Glamor (OpenGL acceleration)              │
├─────────────────────────────────────────────────────────┤
│              Linux DRM/KMS (kernel)                     │
│         (i915, amdgpu, nouveau, etc.)                   │
└─────────────────────────────────────────────────────────┘
```

#### Why Modesetting Only?

We deliberately **do not install** `xserver-xorg-video-all` (which includes legacy drivers like vesa, fbdev, intel DDX). Instead, we rely solely on the **modesetting driver** built into `xserver-xorg-core`.

**Reasons:**

1. **Avoids I/O port errors:** Legacy drivers (vesa, fbdev) attempt to access VGA I/O ports (`0000-03ff`), which fails under rootless X with `xf86EnableIO: Operation not permitted`

2. **Works everywhere KMS works:** The modesetting driver supports all hardware with a working kernel DRM/KMS driver—which includes Intel (2008+), AMD (2012+), NVIDIA via nouveau, and VM graphics (QXL, virtio-gpu)

3. **Simpler, more maintainable:** Legacy DDX drivers are effectively unmaintained; modesetting is what modern Xorg development targets

4. **No privilege escalation needed:** Modesetting uses only DRM/KMS ioctls, never raw I/O—works cleanly with logind/rootless X

#### Hardware Compatibility

| GPU | Kernel Driver | Support |
|-----|---------------|---------|
| Intel HD/UHD (2008+) | i915 | ✅ Full |
| AMD Radeon (2012+) | amdgpu | ✅ Full |
| AMD Radeon (older) | radeon | ✅ Full |
| NVIDIA (via nouveau) | nouveau | ✅ Basic |
| NVIDIA proprietary | nvidia | ⚠️ Requires separate config |
| QEMU/KVM VMs | virtio-gpu, qxl | ✅ Full |
| VirtualBox | vboxvideo | ✅ Full |

**Note:** NVIDIA proprietary drivers install their own X driver and config, which takes precedence. The modesetting approach doesn't interfere with this.

---

## Build Process

### Prerequisites

**Build machine:**
- Docker installed and running
- 20GB free disk space
- Internet connection (for downloads)
- Any OS (Linux, macOS, NixOS)

**Time estimate:**
- Golden image: 10-15 minutes
- Ubuntu ISO download: 5-10 minutes (first build only)
- ISO remaster: 5-10 minutes
- **Total: 20-35 minutes (first build), 15-25 minutes (subsequent)**

### Quick Start

```bash
cd build-scripts
./build-in-docker.sh
```

This builds everything in Docker and outputs the ISO to `/opt/purple-installer/output/`.

**Resume from a specific step:**
```bash
./build-in-docker.sh 1  # Skip golden image, start from ISO remaster
```

### Build Pipeline (2 Steps)

The build uses an **initramfs injection** approach: we download the official Ubuntu Server ISO and inject a hook script into the initramfs. The squashfs is left completely untouched.

#### Step 0: Build Golden Image

**Script:** `00-build-golden-image.sh`

Creates a complete Ubuntu Noble Numbat system as a disk image using `debootstrap`.

**Output:** `purple-os.img.zst` (~1.5 GB compressed)

**Contents:**
- Ubuntu 24.04 minimal base
- Standard Ubuntu kernel (linux-image-generic)
- GRUB bootloader
- X11 + Alacritty + Purple TUI
- Python dependencies

This is the system that gets written to the target laptop's internal disk.

#### Step 1: Remaster Ubuntu ISO

**Script:** `01-remaster-iso.sh`

Downloads official Ubuntu Server 24.04 ISO and injects our hook into the initramfs.

**Process:**
1. Download Ubuntu Server ISO (cached for subsequent builds)
2. Mount and extract ISO contents
3. Extract initramfs (using `unmkinitramfs`)
4. Add hook script to `/scripts/init-top/`
5. Repack initramfs (maintaining concatenated cpio structure)
6. Add payload files to ISO root (`/purple/`)
7. Rebuild ISO with xorriso

**Output:** `purple-installer-YYYYMMDD.iso` (~4-5 GB)

**Key insight:** We only modify the initramfs. The squashfs, kernel, and boot stack remain completely untouched.

**ISO structure (after remaster):**
```
purple-installer.iso
├── casper/
│   ├── vmlinuz             # Ubuntu kernel (untouched)
│   ├── initrd              # MODIFIED: has our hook script
│   └── *.squashfs          # Untouched (never mounted)
├── purple/                 # NEW: our payload
│   ├── install.sh          # Installer script
│   └── purple-os.img.zst   # Golden image
├── boot/grub/
│   └── grub.cfg            # Ubuntu's GRUB config (untouched)
├── [BOOT]/                 # UEFI boot partition (untouched)
└── isolinux/               # BIOS boot (untouched)
```

The ISO is **hybrid**—bootable from USB stick or optical media, BIOS or UEFI, with Secure Boot support.

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

**Note:** Secure Boot can remain enabled on most systems.

### Installation Process

**Automatic installation (10-20 minutes):**

1. USB boots (Ubuntu kernel loads initramfs)
2. Hook script in initramfs runs before casper
3. Hook finds payload on boot device and runs `install.sh`
4. Installer detects internal disk (first non-USB, non-removable disk)
5. Wipes disk and writes golden image via `zstdcat | dd`
6. Sets up UEFI boot with 3-layer fallback strategy
7. Reboots automatically

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

The golden image is built in step 0. To customize the installed OS:

**Edit:** `build-scripts/00-build-golden-image.sh`

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
./build-in-docker.sh 0  # Full rebuild
```

### Change Partition Layout

The golden image creates a simple two-partition layout (EFI + root). To customize:

**Edit:** `build-scripts/00-build-golden-image.sh`

**Example—add swap partition:**
```bash
# In partition creation section
parted -s "$GOLDEN_IMAGE" mkpart primary linux-swap 513MiB 4GiB
parted -s "$GOLDEN_IMAGE" mkpart primary ext4 4GiB 100%
```

---

## Troubleshooting

### Build Issues

**"debootstrap: error retrieving packages"**

Network connectivity issue during build. Ensure Docker has internet access.

**"No space left on device"**

Free up space or use larger disk:
```bash
df -h /opt/purple-installer  # Check usage
du -sh /opt/purple-installer/build/*  # Find large files
```

### Boot Issues

**"Boot device not found" / No USB boot option**

- Ensure USB was written correctly (use `dd` or balenaEtcher)
- Try different USB port (USB 2.0 ports often more reliable)
- Check BIOS boot order includes USB

**Installer hangs at boot (black screen)**

Ubuntu's kernel should handle most hardware, but try:
- Wait longer (some hardware takes 30+ seconds to initialize)
- Try debug mode from boot menu
- Check BIOS settings for legacy boot options

**"No target disk found"**

The installer couldn't find an internal disk. Causes:
- Disk is USB-connected (shows as removable)
- NVMe not detected (rare with Ubuntu kernel)

**Solution:** Check tty2 (Alt+F2) for emergency shell, then:
```bash
lsblk  # List all disks
cat /sys/block/*/removable  # Check removable flags
```

### Installation Issues

**Installation hangs during disk write**

- Bad disk sectors or failing hard drive
- USB stick interference

**Check:**
```bash
# Boot Ubuntu live USB separately
# Run disk check
sudo badblocks -v /dev/sda

# Check SMART status
sudo smartctl -a /dev/sda
```

### Post-Install Issues

**System boots to grub rescue prompt**

UEFI boot entries not created correctly.

**Solution:**
```bash
# Boot from Ubuntu live USB
# Mount target system
sudo mount /dev/sdX2 /mnt
sudo mount /dev/sdX1 /mnt/boot/efi

# Check if bootloader exists
ls /mnt/boot/efi/EFI/BOOT/

# If missing, copy from installer or reinstall
```

**Screen resolution wrong**

X11 may not detect native resolution. See [Graphics Stack](#graphics-stack-installed-system).

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
│   ├── purple-os.img.zst              # Golden image (compressed)
│   ├── ubuntu-24.04.1-live-server-amd64.iso  # Cached Ubuntu ISO
│   └── remaster/                      # Remaster working directory
│       ├── iso-contents/              # Extracted ISO
│       └── initrd-work/               # Extracted initramfs
└── output/
    └── purple-installer-YYYYMMDD.iso  # Final ISO
```

**Source files:**
```
build-scripts/
├── 00-build-golden-image.sh     # Ubuntu base system (debootstrap)
├── 01-remaster-iso.sh           # Remaster Ubuntu Server ISO (initramfs injection)
├── build-all.sh                 # Orchestrator (2 steps)
├── build-in-docker.sh           # Docker wrapper
├── clean.sh                     # Clean all build artifacts
├── validate-build.sh            # Pre-build validation
└── install.sh                   # Installation script (runs in initramfs)
```

**Installed system:**
```
/boot/
├── vmlinuz-*           # Ubuntu kernel
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
- Microsoft Surface Laptop (2017+)
- MacBook Air/Pro (2013+, Intel models)

**Supported storage:**
- SATA (AHCI controller)
- NVMe (modern SSDs)
- USB (for installer boot)

**Secure Boot:**
- Works on most systems with shim + GRUB signed boot chain
- No MOK enrollment required

### Size Reference

| Component | Size |
|-----------|------|
| Golden image (compressed) | ~1.5 GB |
| Live filesystem (squashfs) | ~2.5 GB |
| Final ISO | ~3-4 GB |
| Installed system | ~5-6 GB |

### Boot Flow Diagram

```
USB Boot (BIOS/UEFI)
  ↓
Bootloader (ISOLINUX/GRUB+Shim)
  ↓
Load Ubuntu Kernel + Initramfs
  ├─ MODULES=most initramfs
  ├─ Comprehensive driver support
  └─ Modified initramfs with Purple hook
  ↓
Initramfs init-top scripts run
  ├─ udev starts (devices available)
  └─ Purple hook: /scripts/init-top/01_purple_installer
      ├─ Check each block device for /purple/install.sh
      ├─ If found: Run installer, reboot
      └─ If not found: Exit, continue to casper
  ↓
(Only if payload not found)
Casper mounts squashfs → Normal Ubuntu boot
  ↓
First Boot (Installed System)
  └─ Ubuntu 24.04 + Purple TUI
```

### Documentation

- **README.md** - Quick start and overview
- **MANUAL.md** - This file (complete reference)
- **guides/architecture-overview.md** - High-level explanation of the two-system design and design rationale
- **guides/ubuntu-live-installer.md** - Technical deep-dive on ISO remaster architecture

---

💜
