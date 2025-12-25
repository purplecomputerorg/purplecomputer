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
- [Power Management](#power-management)
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

### How It Works (Two-Gate Safety Model)

Installation requires passing **two independent safety gates**:

| Gate | When | What | Purpose |
|------|------|------|---------|
| **Gate 1** | Initramfs (early boot) | Check `purple.install=1` in cmdline | Design-time arming |
| **Gate 2** | Userspace (systemd) | Show confirmation, require ENTER | Runtime user consent |

**Boot Flow:**

1. **Boot:** USB stick loads Ubuntu's signed boot chain (shim → GRUB → kernel)
2. **Initramfs:** Kernel loads initramfs with our injected hook script
3. **Gate 1 (Hook Runs):** Our script in `/scripts/init-top/` checks for `purple.install=1`
   - If NOT armed → exit, normal Ubuntu boot
   - If ARMED → find payload, write runtime artifacts to `/run/`, continue to casper
4. **Casper:** Ubuntu's casper mounts squashfs, systemd starts
5. **Gate 2 (Confirmation):** Runtime systemd service shows confirmation screen
   - User presses ENTER → run installer
   - User presses ESC or timeout → reboot (no install)
6. **Write:** Decompress and write pre-built Ubuntu image to internal disk
7. **Bootloader:** Setup UEFI boot entries with multi-layer fallback
8. **Reboot:** System boots into installed Ubuntu + Purple TUI

**Key insight:** The squashfs is never modified. Gate 2's systemd service is written to `/run/` by the initramfs hook—systemd automatically loads units from `/run/systemd/system/`.

**No package manager runs during installation.** The installer writes a complete, pre-built Ubuntu system image directly to disk.

### Initramfs Injection Architecture

The installer intercepts boot BEFORE Ubuntu's live system starts:

```
USB Boot Flow (Two-Gate Model)
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
GRUB menu:
  • "Install Purple Computer" (default) → purple.install=1
  • "Debug Mode (no install)" → no arming flag
    │
    ▼
vmlinuz + initrd (Ubuntu kernel + modified initramfs)
    │
    ▼
═══════════════════════════════════════════════════════════
                    GATE 1: DESIGN-TIME ARMING
═══════════════════════════════════════════════════════════
initramfs runs init-top scripts
    │
    ├── [Purple hook] Check cmdline for purple.install=1
    │       │
    │       ├── NOT ARMED → Gate 1 CLOSED → normal Ubuntu boot
    │       │
    │       └── ARMED → scan for payload
    │               │
    │               ├── Found → write /run/purple/armed marker
    │               │           write /run/systemd/system/purple-confirm.service
    │               │           Gate 1 PASSED → continue to casper
    │               │
    │               └── Not found → Gate 1 CLOSED → normal Ubuntu boot
    │
    ▼
casper mounts squashfs → systemd starts
    │
    ▼
═══════════════════════════════════════════════════════════
                    GATE 2: RUNTIME USER CONFIRMATION
═══════════════════════════════════════════════════════════
purple-confirm.service runs (only if /run/purple/armed exists)
    │
    ├── Shows large warning: "This will set up Purple Computer"
    │
    ├── Waits for user input:
    │       │
    │       ├── ENTER → Gate 2 PASSED → run installer
    │       │
    │       ├── ESC → Gate 2 CLOSED → reboot (no install)
    │       │
    │       └── Timeout → Gate 2 CLOSED → reboot (no install)
    │
    ▼
(Only reaches here if both gates passed)
install.sh writes golden image to disk
    │
    ▼
Reboot into installed Purple Computer
```

**Key insight:** Our hook runs in initramfs but does NOT run the installer. It writes runtime artifacts to `/run/` and lets casper continue. The confirmation screen (Gate 2) runs in userspace via systemd.

**Safety:** Installation requires BOTH gates to pass:
1. `purple.install=1` in kernel cmdline (Gate 1 - design-time arming)
2. User presses ENTER on confirmation screen (Gate 2 - runtime consent)

Selecting "Debug Mode" from the GRUB menu fails Gate 1, booting into normal Ubuntu Server live environment.

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

Purple Computer displays a **100×28 character viewport** (plus header and footer) requiring a **104×37 character terminal grid**. The font size is calculated to fill **80% of the screen**, with a cap to prevent huge viewports on large displays.

**Minimum supported resolution:** 1024×768

#### How It Works

At X11 startup, `calc_font_size.py` calculates the optimal font size:

1. **Get resolution** from xrandr (fallback: 1366×768)
2. **Probe cell size** by launching Alacritty at 18pt (fallback: 11×22 pixels)
3. **Calculate font** to fill 80% of screen
4. **Clamp** to 12-24pt range

That's it. No EDID/physical size detection (too unreliable), no caching (fast enough), no validation loops (calculation just works).

#### Behavior by Screen Size

| Screen | Resolution | Font | Viewport Fill |
|--------|------------|------|---------------|
| 11" laptop | 1366×768 | 14pt | 80% |
| 13" laptop | 1920×1080 | 19pt | 80% |
| 15" laptop | 1920×1080 | 19pt | 80% |
| 17" laptop | 2560×1440 | 24pt | ~60% (capped) |
| 4K monitor | 3840×2160 | 24pt | ~40% (capped) |

The 24pt cap prevents oversized viewports on large screens while keeping the UI proportional on typical donated laptops (11-15").

#### Debugging

Run inside the VM to see what's happening:
```bash
python3 /opt/purple/calc_font_size.py --info
```

Output:
```
Screen: 1920x1080
Cell: 11x22 (at 18pt)
Grid: 104x37
Fill: 80%
Font: 19.1pt
```

Startup log: `cat /tmp/xinitrc.log`

#### Manual Override

Edit xinitrc to force a specific font size:
```bash
FONT_SIZE=20  # Override calculated size
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

#### Input Devices

Purple Computer is **keyboard-only**. Mouse and trackpad input is disabled at multiple layers:

| Layer | How | Config |
|-------|-----|--------|
| **X.Org** | `MatchIsPointer "on"` → `Ignore "true"` | `40-disable-pointer.conf` |
| **Textual** | `app.run(mouse=False)` | `purple_tui.py` |
| **Visual** | `unclutter -idle 2` hides cursor | `.xinitrc` |

The X.Org config (`/usr/share/X11/xorg.conf.d/40-disable-pointer.conf`) completely ignores all pointer and touchpad devices:

```
Section "InputClass"
    Identifier "Disable all pointer devices"
    MatchIsPointer "on"
    Option "Ignore" "true"
EndSection

Section "InputClass"
    Identifier "Disable touchpads"
    MatchIsTouchpad "on"
    Option "Ignore" "true"
EndSection
```

This ensures kids can't accidentally click around or get confused by trackpad gestures.

#### F-Key Setup

Purple Computer uses the top-row keys (F1-F12) for switching between modes. On first boot, keyboard setup runs automatically - just press each F-key when prompted.

**How it works:**

The keyboard normalizer identifies physical keys by their internal codes (scancodes), which stay the same regardless of what the laptop decides each key should do. This means:
- Physical F1 key → always works as F1 in Purple Computer
- No need to hold extra keys or remember special combinations
- Works on any laptop

**Re-running setup:**

If you need to reconfigure (e.g., different keyboard), run from parent shell:

```bash
sudo python3 /opt/purple/keyboard_normalizer.py --calibrate
```

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

**Recommended: Use the flash script (Linux)**

The `flash-to-usb.sh` script provides safe USB writing with verification:

```bash
# One-time setup: whitelist your USB drive
./build-scripts/flash-to-usb.sh --list    # Find your drive's serial number
echo 'YOUR_SERIAL' >> .flash-drives.conf  # Add to whitelist

# Flash the latest ISO
./build-scripts/flash-to-usb.sh
```

**Features:**
- Only writes to whitelisted drives (prevents accidental data loss)
- Rejects drives over 256GB (safety limit for flash drives)
- Verifies write by reading back and comparing SHA256 checksums
- Auto-detects most recent ISO in `/opt/purple-installer/output/`

**Manual method (Linux/macOS):**
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

**Two-gate installation (10-20 minutes):**

1. USB boots (Ubuntu kernel loads initramfs)
2. **Gate 1:** Hook script checks for `purple.install=1` in kernel cmdline
3. Hook finds payload on boot device, writes runtime artifacts to `/run/`
4. Casper mounts squashfs, systemd starts
5. **Gate 2:** Confirmation screen appears - "This will set up Purple Computer"
6. **User presses ENTER** to confirm (ESC or timeout cancels)
7. Installer detects internal disk (first non-USB, non-removable disk)
8. Wipes disk and writes golden image via `zstdcat | dd`
9. Sets up UEFI boot with 3-layer fallback strategy
10. User removes USB and presses ENTER to reboot

**User confirmation required.** Gate 2 ensures explicit consent before any disk writes.

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

## Power Management

Purple Computer includes automatic power management to save energy and protect the screen on unattended laptops.

### Idle Detection

The system tracks keyboard activity and progresses through idle states:

| Idle Time | State | What Happens |
|-----------|-------|--------------|
| 0-3 min | Active | Normal operation |
| 3 min | Sleep UI | Show sleeping face, "press any key to wake" |
| 10 min | Dim | (reserved for future use) |
| 15 min | Screen Off | DPMS turns off display |
| 25 min | Shutdown Warning | "Turning off in X minutes" |
| 30 min | Shutdown | System powers off |

**Lid close** triggers a 5-second countdown to shutdown (shown on screen).

### Implementation

Activity is tracked via `on_event()` in the Textual app, which catches all keyboard events before they can be consumed by child widgets. This ensures activity is always recorded regardless of which mode is active.

**Key files:**
- `purple_tui/power_manager.py` - Idle tracking, screen control, shutdown
- `purple_tui/modes/sleep_screen.py` - Sleep UI and wake handling
- `purple_tui/purple_tui.py` - Activity recording in `on_event()`

### Testing Sleep Mode

Use demo mode for accelerated timings:

```bash
PURPLE_SLEEP_DEMO=1 python -m purple_tui.purple_tui
```

Demo timings:
- Sleep UI: 2 seconds
- Screen off: 10 seconds
- Shutdown warning: 15 seconds
- Shutdown: 20 seconds (prints message instead of actual shutdown)

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

- Ensure USB was written correctly (use `flash-to-usb.sh` which verifies the write)
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

**F-keys (F1-F12) not working**

Keyboard setup should have run on first boot. To re-run it:

```bash
# From parent shell (hold Escape 1 second)
sudo python3 /opt/purple/keyboard_normalizer.py --calibrate
```

Or delete the config and reboot:
```bash
sudo rm /etc/purple/keyboard-map.json
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
├── flash-to-usb.sh              # Safe USB writing with verification
└── install.sh                   # Installation script (runs in initramfs)

.flash-drives.conf               # USB drive whitelist (gitignored, user-specific)
.flash-drives.conf.example       # Template for whitelist
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
  ├─ "Install Purple Computer" → purple.install=1 (default)
  └─ "Debug Mode (no install)" → no arming flag
  ↓
Load Ubuntu Kernel + Initramfs
  ├─ MODULES=most initramfs
  ├─ Comprehensive driver support
  └─ Modified initramfs with Purple hook
  ↓
═══════════════════════════════════════════════
            GATE 1: DESIGN-TIME ARMING
═══════════════════════════════════════════════
Initramfs init-top scripts run
  ├─ udev starts (devices available)
  └─ Purple hook: /scripts/init-top/01_purple_installer
      ├─ Check cmdline for purple.install=1
      ├─ If NOT ARMED: exit, Gate 1 closed
      ├─ If ARMED: scan for /purple/payload
      │     ├─ If found: write /run/purple/armed
      │     │            write /run/systemd/system/purple-confirm.service
      │     │            Gate 1 passed → continue to casper
      │     └─ If not found: exit, Gate 1 closed
  ↓
Casper mounts squashfs → systemd starts
  ↓
═══════════════════════════════════════════════
         GATE 2: RUNTIME USER CONFIRMATION
═══════════════════════════════════════════════
purple-confirm.service runs (if /run/purple/armed exists)
  ├─ Shows confirmation screen
  ├─ ENTER → Gate 2 passed → run install.sh
  ├─ ESC → Gate 2 closed → reboot
  └─ Timeout → Gate 2 closed → reboot
  ↓
(Only if both gates passed)
install.sh writes golden image to disk
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
