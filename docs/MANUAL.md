# Purple Computer Manual

Complete reference for building, installing, and maintaining Purple Computer.

**Table of Contents:**
- [Overview](#overview)
- [Installer Architecture](#installer-architecture)
  - [Screen Size & Font Calculation](#screen-size--font-calculation)
  - [Graphics Stack](#graphics-stack-installed-system)
- [Play Room](#play-room)
- [Build Process](#build-process)
  - [Versioning](#versioning)
  - [Releasing](#releasing)
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
1. **USB Installer:** A temporary Ubuntu live environment that copies the system to disk, then is never used again
2. **Installed System:** A normal Ubuntu 24.04 system that kids use every day

These are built differently and serve different purposes. See [guides/architecture-overview.md](../guides/architecture-overview.md) for a detailed explanation.

---

## Installer Architecture

### Design Philosophy

The PurpleOS installer is built for **simplicity, reliability, and broad hardware compatibility**. It uses Ubuntu's stock kernel and signed boot chain to work across diverse laptop hardware including Surface, Dell, HP, and ThinkPad devices.

### How It Works (Live Boot + Optional Install)

The USB boots straight into Purple (live boot). Installation is optional and is started from the parent menu inside the running TUI, after a PIN and a data-loss confirmation. There is no GRUB install entry and no kernel-cmdline arming in production.

**Boot Flow:**

1. **Boot:** USB stick loads Ubuntu's signed boot chain (shim → GRUB → kernel). The GRUB menu is hidden and auto-boots "Purple Computer."
2. **Casper:** Ubuntu's casper mounts our squashfs and overlayfs. The casper-bottom hook (`80_purple_installer`) restores dotfiles, sets debug mode, and paints the splash. It does NOT gate install.
3. **Live system:** systemd auto-logins as `purple`, `purple-x11.service` starts X11 → Alacritty → Purple TUI. The internal disk is never touched.
4. **Install (optional):** A parent holds Escape for 1s to open the PIN-gated parent menu and picks "Install on this Computer." `InstallProgressScreen` shows a data-loss warning, then runs `/cdrom/purple/install.sh` (via sudo) while the live system keeps running.
5. **Write:** `install.sh` detects the internal disk (excluding USB/removable devices), wipes it, and writes the pre-built Ubuntu image (`purple-os.img.zst`) directly to disk.
6. **Bootloader:** Sets up UEFI boot entries with multi-layer fallback.
7. **Reboot:** "Press ENTER to restart" hands off to the `purple-reboot` binary; the system boots into installed Ubuntu + Purple TUI.

**Key insight:** The squashfs is never modified. The same debootstrap root filesystem is packaged twice: as the squashfs for live boot and as `purple-os.img.zst` for install.

**No package manager runs during installation.** The installer writes a complete, pre-built Ubuntu system image directly to disk.

> Historical note: earlier versions armed install from a GRUB entry (`purple.install=1`) and confirmed via a `purple-confirm.service` two-gate model. That has been replaced by the in-TUI parent-menu flow. `purple.install=1` now survives only as a developer/test switch that suppresses X11 so the install path can be exercised on a tty (see `test-boot.sh --mode install`).

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

Purple Computer displays a **134×29 character viewport** (plus header and footer) requiring a **146×37 character terminal grid**. The font size is the largest that fits the screen, clamped to 12-48pt.

**Minimum supported resolution:** 1024×768

#### How It Works

At X11 startup, `calc_font_size.py` calculates the optimal font size:

1. **Get resolution** from xrandr (fallback: 1366×768)
2. **Use a fixed cell-to-point ratio** for JetBrainsMono at 96 DPI (11×22 px at 18pt)
3. **Calculate the largest font** that fits the required grid on screen
4. **Clamp** to 12-48pt range

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
Grid: 146x37
Cell ratio: 0.611w x 1.222h px/pt
Fill: 100% (max font that fits grid)
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

#### Parent Menu

Hold Escape for ~1 second to open the Parent Menu. Alternatively, hold the backslash key (`\`) for 3 seconds, which works on all keyboards including Macs where Escape may be unreliable.

Navigation uses explicit key handling (no focus system):

| Key | Action |
|-----|--------|
| **↑/↓** | Move selection |
| **Enter** | Activate selected item |
| **Escape** | Close menu |

---

## Play Room

The Play room is a calculator that understands math, emojis, and colors. It's designed to be **maximally permissive**: always try to do something meaningful.

### Quick Reference

| Input | Output |
|-------|--------|
| `2 + 2` | 4 with dot visualization |
| `3 * 4 + 2` | 14 (operator precedence preserved) |
| `cat` | 🐱 |
| `3 cats` | 🐱🐱🐱 |
| `cat * 5` | 5 cats + 🐱🐱🐱🐱🐱 (with label) |
| `cat + dog` | 🐱 🐶 (space between different types) |
| `cats` | 🐱🐱 (bare plural = 2) |
| `red + blue` | Purple swatch (color mixing) |
| `3 + 4 + 2 bananas` | 9 bananas (numbers attach to emoji) |
| `apple + red + green` | Two lines: inputs then mixed result |

### Key Behaviors

- **Operator precedence preserved:** `3 * 4 + 2 = 14`, not 18
- **Numbers attach to emojis:** `3 + 4 + 2 bananas = 9 bananas`
- **Labels for computed expressions:** Shows "14 dogs" above the emojis when math was involved
- **Spaces between different emoji types:** `cat + dog` → `🐱 🐶`
- **Colors mix like paint:** Even with non-colors between them
- **Typo tolerance:** Long math expressions (3+ operators, 60%+ valid symbols) tolerate accidental keystrokes like `=` (replaced with `+`)
- **Unknown text passes through:** `my name is tavi apple` → `my name is tavi 🍎`

### Speech

Add `!` anywhere in your input to hear it spoken aloud:

| Input | Behavior |
|-------|----------|
| `cat!` | Shows 🐱 and speaks "cat" |
| `2+2!` | Shows 4 and speaks "2 plus 2 equals 4" |
| `!red + blue` | Shows purple swatch and speaks "red plus blue equals purple" |

The `!` is stripped from display. Works anywhere in the text (beginning, middle, end).

**Other speech triggers:**
- `say` or `talk` prefix: `say cat` speaks "cat"
- **Enter on empty input**: repeats the last result ("say it again")

### Autocomplete

- Triggers at 2+ characters
- Common 2-letter words excluded (by, my, go, to, etc.) to prevent unwanted completions
- Space accepts the suggestion

For the full design philosophy, see [guides/play-room-design.md](../guides/play-room-design.md).

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

The build remasters the official Ubuntu Server ISO: we swap in our Purple Computer squashfs and inject a casper-bottom hook into the initramfs. The kernel and signed boot stack are left untouched.

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

Downloads the official Ubuntu Server 24.04 ISO, swaps in our squashfs, and injects our casper-bottom hook.

**Process:**
1. Download Ubuntu Server ISO (cached for subsequent builds)
2. Mount and extract ISO contents
3. Replace Ubuntu's squashfs with our Purple Computer squashfs
4. Extract initramfs (using `unmkinitramfs`)
5. Add hook script to `/scripts/casper-bottom/` (`80_purple_installer`) and list it in `ORDER`
6. Repack initramfs (maintaining concatenated cpio structure)
7. Add payload files to ISO root (`/purple/`: golden image + install.sh)
8. Rebuild ISO with xorriso

**Output:** `purple-installer-YYYYMMDD.iso` (~4-5 GB)

**Key insight:** The kernel and signed boot stack remain untouched. We replace the squashfs with our own and add one casper-bottom hook to the initramfs.

**ISO structure (after remaster):**
```
purple-installer.iso
├── casper/
│   ├── vmlinuz             # Ubuntu kernel (untouched)
│   ├── initrd              # MODIFIED: has our casper-bottom hook
│   └── filesystem.squashfs # REPLACED: Purple root filesystem (mounted as root)
├── purple/                 # NEW: our payload
│   ├── install.sh          # Installer script (run by the parent menu)
│   └── purple-os.img.zst   # Golden image
├── boot/grub/
│   └── grub.cfg            # MODIFIED: hidden auto-boot, single Purple Computer entry
├── [BOOT]/                 # UEFI boot partition (untouched)
└── isolinux/               # BIOS boot (untouched)
```

The ISO is **hybrid**—bootable from USB stick or optical media, BIOS or UEFI, with Secure Boot support.

### Versioning

Every ISO is stamped with a version in `/etc/purple-version`, visible in the Parent Menu (hold Escape).

**Version formats:**

| Type | Example | Parent Menu shows | When |
|------|---------|-------------------|------|
| Semver | `v1.0` | Version 1.0 | Major releases (`./release-iso.sh v1.0`) |
| Date-time | `v2026.03.30-1430` | Build: Mar 30, 2026 | Regular releases (`./release-iso.sh`) |
| Dev build | `build-abc1234-20260330` | Dev build: abc1234 | No `PURPLE_VERSION` set at build time |

**To stamp a specific version at build time:**

```bash
PURPLE_VERSION=v1.0 ./build-in-docker.sh
```

If `PURPLE_VERSION` is not set, the build uses the git short hash and date as a fallback.

### Releasing

**Script:** `release-iso.sh`

Uploads ISOs to Cloudflare R2 and updates redirect rules so `/download.iso` points to the new version.

```bash
./release-iso.sh          # date-time version (v2026.03.30-1430)
./release-iso.sh v1.0     # semver for major releases
```

**What it does:**
1. Generates SHA-256 checksums
2. Uploads standard + debug ISOs to `releases/{version}/`
3. Updates Cloudflare redirect rules (`/download.iso` → versioned path)
4. Writes `latest.json` with version, checksums, and sizes

**Required `.env` values** (see `.env.template`): `R2_BUCKET`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CF_API_TOKEN`, `CF_ZONE_ID`, `R2_CUSTOM_DOMAIN`.

**Cloudflare setup (one-time):** `setup-cloudflare-rules.sh` configures cache rules (aggressive caching for `/releases/*`, bypass for `/download*`) and redirect rules. It runs automatically as part of `release-iso.sh`, or can be run standalone to set up cache rules without releasing.

### The Download Page and PDFs

The customer download page lives in the landing repo (`~/landing/src/pages/downloads.tsx`) and is served by Vercel at `downloads.purplecomputer.org`; it deploys with the landing site. The files themselves (ISOs, checksums, `latest.json`, card PDFs) are served straight from R2 on a separate custom domain (`R2_CUSTOM_DOMAIN`, value in the private env file).

```bash
just upload-pdfs           # Upload the card PDFs, purge cache
```

`upload-pdfs` extracts installation (pages 1-2) and guide (pages 3-4) PDFs from `cards/purple.pdf`, uploads them to R2, then purges the Cloudflare cache for both.

### Caching Strategy

ISOs use versioned paths (`releases/{version}/standard.iso`), so each release has a unique URL that can be cached aggressively (1 day edge TTL). The `/download.iso` shortcut is a Cloudflare 302 redirect to the current version, with cache bypassed so it always resolves to the latest release.

PDFs don't have versioned filenames, so `upload-pdfs` purges the Cloudflare cache after each upload. If the purge fails (e.g., missing CF credentials), a warning is printed but the upload still succeeds. Visitors may see stale content briefly until the cache expires naturally.

The upload script shares common helpers from `r2-helpers.sh` (env loading, R2 upload, PDF extraction, cache purge).

---

## Installation

### Writing to USB

**Recommended: Use the flash script (Linux)**

The `flash-to-usb.sh` script provides safe USB writing with verification:

```bash
# Flash: asks which of the newest build's ISO variants to use, then which
# drive (plugged-in USB sticks of 64GB or smaller)
./build-scripts/flash-to-usb.sh

# Optional: whitelist your drive to skip the drive picker, allow drives over
# 64GB, and enable non-interactive flashing (--yes, flash-all)
./build-scripts/flash-to-usb.sh --list    # Find your drive's serial/vendor/model
echo 'YOUR_SERIAL' >> .flash-drives.conf  # Add to whitelist

# Or whitelist a whole vendor+model (handy when you have several of the same kind):
echo 'model:Verbatim/STORE N GO max=20G' >> .flash-drives.conf
```

**Features:**
- Only offers small USB drives (64GB and under) unless whitelisted, so a real
  data disk is never one typo away from being erased; automation paths
  (`--yes`, `--device`, `flash-all`) are whitelist-only
- Whitelisted drives are capped at 256GB (whitelist rules can set tighter
  `max=` limits per vendor/model)
- Verifies write by reading back and comparing SHA256 checksums
- Shows the newest build in `/opt/purple-installer/output/` and asks which
  variant to flash (standard, with-backup, or debug); never silently falls
  back to an older build

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

**Installation (started from the parent menu, 10-20 minutes):**

1. USB live-boots straight into Purple (no install yet)
2. A parent holds Escape for 1s and enters the PIN to open the parent menu
3. Parent picks "Install on this Computer"; `InstallProgressScreen` shows a data-loss confirmation
4. On confirm, `install.sh` runs from `/cdrom/purple/` while the live system keeps running
5. Installer detects the internal disk (first non-USB, non-removable disk)
6. Wipes disk and writes golden image via `zstdcat | dd`
7. Sets up UEFI boot with 3-layer fallback strategy
8. User removes USB and presses ENTER to reboot

**User confirmation required.** The PIN gate plus the confirmation screen ensure explicit consent before any disk writes.

### First Boot

The system logs in automatically as the `purple` user. No password is needed. Purple Computer is an offline appliance, so there is no login screen or password prompt.

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

Purple Computer includes automatic power management to save energy. Two power states: awake and sleep face (no DPMS screen-off). Timers adapt to charger status and lid position.

### Power Button

The power button is kid-proofed to prevent accidental shutdowns:

| Gesture | What Happens |
|---------|-------------|
| Tap (< 3s) | Shows shutdown confirmation with countdown. Tap again to confirm, or wait to cancel. |
| Hold (3s) | Shows "Bye!" and shuts down. Like a phone. |
| Hold (10s) | Hardware forced off (ACPI, always available). |

logind is configured to ignore the power button (`HandlePowerKey=ignore`). The TUI reads the power button via a separate evdev device (`PowerButtonReader`) and handles all the UX.

### Lid Close

Closing the lid shows the sleep screen immediately and starts a 10-minute shutdown countdown. Opening the lid cancels the countdown but keeps the sleep screen visible, showing parents how long the lid was closed and when the computer will turn off. Any key press wakes back to normal.

Shuts down after 10 minutes of lid-closed time regardless of charger state.

### Idle Detection (Lid Open)

Timings depend on charger state:

| Condition | Sleep Face | Auto Shutdown |
|-----------|-----------|---------------|
| On charger | 5 min idle | 60 min idle |
| On battery | 2 min idle | 10 min idle |

The sleep screen shows a power status message so parents understand what's happening: charger state, elapsed time, and when auto-shutdown will occur. On live boot (USB), it also notes that the USB is needed to restart.

### Implementation

**Key files:**
- `purple_tui/power_manager.py`: Idle tracking, charger detection, shutdown timings
- `purple_tui/rooms/sleep_screen.py`: Sleep UI (`SleepScreen`), shutdown confirm (`ShutdownConfirmScreen`), bye (`ByeScreen`)
- `purple_tui/input.py`: `PowerButtonReader` and `LidSwitchReader` (evdev)
- `purple_tui/purple_tui.py`: Activity recording, lid/power button integration

### Testing Sleep Mode

Use demo mode for accelerated timings:

```bash
PURPLE_SLEEP_DEMO=1 python -m purple_tui.purple_tui
```

Demo timings: sleep face in 2-3 seconds, shutdown in 8-10 seconds (prints message instead of actual shutdown).

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

**Solution:** Switch to tty2 for an emergency shell (see below), then:
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

### Switching to a Debug Shell (VT Switch)

Purple Computer runs on tty1. To get a root shell on tty2 for debugging:

**From the keyboard (emergency escape hatch):** Two options:
- **Ctrl+Alt+F2**: Immediate switch (standard Linux VT switching, reimplemented via evdev since the kernel's built-in version is disabled by Alacritty's K_OFF mode)
- **Ctrl+\\** (Ctrl+Backslash) held for 3 seconds: Same effect, alternative combo

Both release the evdev grab so tty2 receives keyboard input. Both work even when the TUI is completely frozen. Note: these only work once the app's evdev handler has started (a few seconds after the purple screen appears).

**From SSH:** `sudo chvt 2` (note: this does not release the evdev grab, so keyboard input will still go to the app. Use the keyboard methods instead.)

**Returning to Purple Computer:** Either press Ctrl+Alt+F1 (works because tty2 is in normal `K_UNICODE` mode), or hold Ctrl+Backslash for 3 seconds again. Both methods reacquire the evdev grab automatically when the app detects it is back on tty1.

**Checking VT keyboard mode:** `sudo kbd_mode -C /dev/tty1` (will show "unknown" due to `K_OFF`).

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

**Can't open parent menu**

Hold Escape for 1 second. If Escape doesn't work (e.g., Touch Bar Macs), try the backtick key (`` ` ``, top-left corner) which acts as an Escape alias. As a last resort, hold the backslash key (`\`) for 3 seconds.

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
- Works on most systems: shim + GRUB + mmx64.efi signed boot chain
- Binaries updated to latest Ubuntu versions at build time (avoids SBAT revocation)
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
Bootloader (GRUB+Shim, hidden menu, auto-boots)
  └─ "Purple Computer" → live boot
  ↓
Load Ubuntu Kernel + Initramfs
  ├─ MODULES=most initramfs
  ├─ Comprehensive driver support
  └─ Modified initramfs (casper-bottom hook + ORDER)
  ↓
Casper mounts OUR squashfs → systemd starts
  └─ casper-bottom hook 80_purple_installer:
       restores dotfiles, sets debug mode, paints splash
  ↓
Auto-login as purple → purple-x11.service → Alacritty → Purple TUI
  ↓
LIVE: child plays. Internal disk untouched.
  ↓
(Optional install, from the running TUI)
Parent menu (hold Escape 1s, PIN) → "Install on this Computer"
  ├─ InstallProgressScreen shows data-loss confirmation
  └─ On confirm: install.sh (from /cdrom/purple/) writes golden image to disk
  ↓
Reboot → First Boot (Installed System)
  └─ Ubuntu 24.04 + Purple TUI
```

### Documentation

- **README.md:** Quick start and overview
- **MANUAL.md:** This file (complete reference)
- **guides/architecture-overview.md:** High-level explanation of the two-system design and design rationale
- **guides/ubuntu-live-installer.md:** Technical deep-dive on ISO remaster architecture
- **guides/play-room-design.md:** Play room evaluation philosophy and behavior reference

---

💜
