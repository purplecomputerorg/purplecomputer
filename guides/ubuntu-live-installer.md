# Building and Testing the Purple Computer ISO

This guide covers how to build the Purple Computer ISO, test it in a VM, and verify both the live boot and install paths.

For the high-level architecture, see [architecture-overview.md](architecture-overview.md).

---

## What the ISO Does

The ISO serves two purposes from one USB stick:

1. **Live boot (default)**: Boots directly into Purple Computer. No installation, no disk writes, no waiting. The child plays immediately from the USB.
2. **Install (optional)**: A parent selects "Install Purple Computer" from the GRUB menu. The system is written to the internal disk permanently.

Both paths use the same root filesystem, built once by debootstrap and packaged two ways:
- **Squashfs** for live boot (casper mounts it read-only with an overlayfs on top)
- **Compressed disk image** for installation (dd'd directly to the internal disk)

---

## Building

### Prerequisites

- Docker (the build runs inside a container)
- ~20GB free disk space
- Internet connection (downloads Ubuntu Server ISO and packages)

### Full Build

```bash
cd build-scripts
./build-in-docker.sh
```

This runs two steps inside Docker:

| Step | Script | What it produces |
|------|--------|-----------------|
| 0 | `00-build-golden-image.sh` | `filesystem.squashfs` (live boot) + `purple-os.img.zst` (install) |
| 1 | `01-remaster-iso.sh` | Final ISO in `/opt/purple-installer/output/` |

### Partial Rebuilds

If you only changed the GRUB config or initramfs hook (not the root filesystem), skip step 0:

```bash
./build-in-docker.sh 1
```

### Validate Before Testing

```bash
./validate-build.sh
```

Checks:
- Build scripts exist and are executable
- Dockerfile has all required dependencies (including `squashfs-tools`)
- Golden image size is reasonable (1000-2000MB)
- Live squashfs size is reasonable (1500-3000MB)
- Final ISO size is reasonable (4000+ MB)
- ISO contains a Purple Computer squashfs (not Ubuntu's default)

---

## Testing in a VM (QEMU)

### Install QEMU

```bash
# Ubuntu/Debian
sudo apt-get install qemu-system-x86

# NixOS
nix-shell -p qemu

# macOS (Homebrew)
brew install qemu
```

### Automated Tests

These run headless, check serial output for success markers, and report pass/fail.

**Test live boot (default path):**

```bash
sudo ./test-boot.sh
```

Success: detects a login prompt (the system booted into our squashfs and reached getty).

**Test install path:**

```bash
sudo ./test-boot.sh --mode install
```

Success: detects `[PURPLE]` or `Purple Computer Installer` in serial output (the initramfs hook fired and the confirmation service started).

**Options:**

| Flag | Default | What it does |
|------|---------|-------------|
| `--mode live\|install` | `live` | Which boot path to test |
| `--timeout SECONDS` | `60` | How long to wait before failing |
| `--iso PATH` | auto-detect | Path to ISO (defaults to latest in output dir) |
| `--memory MB` | `2048` | QEMU memory allocation |
| `--interactive` | off | Open a QEMU window instead of headless |
| `--debug` | off | Enable verbose QEMU output |
| `--keep-logs` | off | Preserve logs after successful test |

### Interactive Testing

This opens a QEMU window where you can see and interact with everything:

```bash
sudo ./test-boot.sh --interactive
```

**What to verify visually:**

1. GRUB menu appears with "Purple Computer" as the highlighted default
2. 5-second countdown auto-selects "Purple Computer"
3. Kernel boots (scrolling text, then quiet)
4. Login prompt appears (or Purple TUI if X11 starts successfully in the VM)
5. Internal disk is never touched (the QEMU target disk stays empty)

To test the install path interactively, press the down arrow in GRUB within 5 seconds to select "Install Purple Computer", then verify the confirmation screen appears.

### Manual QEMU

For full control over the VM:

```bash
# Create a target disk (simulates the laptop's internal drive)
qemu-img create -f qcow2 /tmp/target.qcow2 20G

# Boot the ISO
qemu-system-x86_64 \
    -m 2048 \
    -hda /opt/purple-installer/output/purple-installer-*.iso \
    -hdb /tmp/target.qcow2 \
    -boot c
```

Add `-serial stdio` to see serial console output in your terminal alongside the QEMU window.

Add `-snapshot` to avoid writing to the ISO or target disk (useful for repeated testing).

---

## What to Check

### Live Boot Path

| Check | How to verify | Expected |
|-------|--------------|----------|
| GRUB default | Watch GRUB menu | "Purple Computer" is entry 0, highlighted |
| Auto-boot timeout | Wait 5 seconds | Boots automatically without input |
| No disk writes | `lsblk` inside VM | Internal disk has no mounts |
| Login prompt | Watch serial/screen | `purple-computer login:` appears |
| Purple TUI starts | Interactive mode | Purple Computer app loads (if X11 works in VM) |
| udisks2 masked | `systemctl status udisks2` | Inactive/masked (prevents internal disk auto-mount) |

### Install Path

| Check | How to verify | Expected |
|-------|--------------|----------|
| GRUB entry | Arrow down in GRUB | "Install Purple Computer" is entry 1 |
| Gate 1 fires | Serial output | `[PURPLE] ARMED: purple.install=1 found` |
| Getty masked | Serial output | `[PURPLE] Masked interfering services` |
| Gate 2 screen | Watch tty1 | "This will ERASE ALL DATA" confirmation appears |
| ESC cancels | Press ESC at Gate 2 | System reboots without installing |
| ENTER installs | Press ENTER at Gate 2 | Golden image written to target disk |

---

## Build Pipeline Details

### Step 0: Root Filesystem + Squashfs + Golden Image

`00-build-golden-image.sh` does everything in one pass:

```
1. Create 8GB disk image, partition (GPT: 512MB ESP + rest ext4)
2. Mount partitions
3. debootstrap Ubuntu 24.04 (minimal)
4. apt-get install: X11, Alacritty, Python, SDL, PulseAudio, fonts, ...
5. pip install: textual, rich, pygame, piper-tts, evdev, ...
6. Copy Purple TUI application, configs, scripts
7. Configure: auto-login, power management, .bashrc, .xinitrc
8. Create GRUB standalone EFI binary (for installed system's bootloader)
9. mksquashfs → filesystem.squashfs (for live boot)
10. Unmount, zstd compress → purple-os.img.zst (for install)
```

The squashfs is created from the mounted root filesystem **before** unmounting, so it contains the exact same files as the golden image. The only exclusion is `boot/efi` (the EFI partition contents are only needed for the installed system's bootloader, not for live boot).

### Step 1: ISO Remaster

`01-remaster-iso.sh` takes the Ubuntu Server ISO and modifies it:

```
1. Download Ubuntu Server 24.04 ISO (cached after first download)
2. Extract ISO contents via rsync
3. Replace casper/filesystem.squashfs with our Purple squashfs
4. Copy casper/filesystem.size
5. Extract initramfs, add install hook to casper-bottom, repack
6. Add /purple/ payload (golden image, install.sh, purple-confirm.sh)
7. Replace GRUB config (live boot default, install as option)
8. Rebuild ISO with xorriso (preserves boot records)
```

### GRUB Configuration

```
"Purple Computer" (default, auto-selected after 5s)
    boot=casper quiet console=tty1
    systemd.mask=udisks2.service  ← prevents internal disk auto-mount
    (no purple.install=1)         ← install hook does nothing

"Install Purple Computer"
    boot=casper console=tty1 console=ttyS0,115200
    purple.install=1              ← triggers install hook

"Boot from next volume"           ← skips USB, tries next boot device
"UEFI Firmware Settings"          ← enters BIOS/UEFI setup
```

The timeout is 5 seconds (configurable via `GRUB_TIMEOUT` env var during build). Since the default action is safe (live boot, no disk writes), a short timeout is appropriate. Parents who want to install have 5 seconds to press the down arrow.

---

## ISO Structure

```
purple-installer.iso
├── boot/grub/grub.cfg          ← Purple boot menu (live default)
├── casper/
│   ├── vmlinuz                 ← Ubuntu kernel (untouched)
│   ├── initrd                  ← Modified (install hook added)
│   ├── filesystem.squashfs     ← Purple Computer root filesystem (REPLACED)
│   └── filesystem.size
├── EFI/                        ← Secure Boot chain (untouched)
└── purple/                     ← Install payload
    ├── purple-os.img.zst       ← Golden image (compressed)
    ├── install.sh              ← Installer script
    └── purple-confirm.sh       ← Gate 2 confirmation script
```

---

## Troubleshooting

### Build Issues

**"Live squashfs not found"**
Step 0 didn't produce the squashfs. Rebuild from step 0:
```bash
./build-in-docker.sh 0
```

**Squashfs too small (<500MB)**
The mksquashfs step ran but the root filesystem wasn't fully populated. Check the step 0 logs for package installation failures.

**ISO too small (<3000MB)**
The squashfs or golden image wasn't included in the ISO. Check step 1 logs for copy errors.

### Live Boot Issues

**GRUB shows Ubuntu menu instead of Purple**
The GRUB config wasn't replaced. Check that step 7/8 in `01-remaster-iso.sh` found `boot/grub/grub.cfg` in the extracted ISO.

**Boots to Ubuntu Server instead of Purple**
The squashfs wasn't replaced. Run `validate-build.sh` to check the squashfs inside the ISO. If it's small (~2GB instead of ~2.5GB+), the copy step failed.

**"login:" appears but Purple TUI doesn't start**
This is expected in QEMU without GPU passthrough. X11 may fail to start because the VM lacks proper graphics drivers. On real hardware, it should work. Check `/var/log/Xorg.0.log` inside the live system.

**Internal disk auto-mounted**
The `systemd.mask=udisks2.service` kernel parameter is missing from the live boot GRUB entry. Check the GRUB config.

### Install Issues

**Install hook doesn't fire**
Check serial output for `[PURPLE]` messages. If absent:
- The initramfs hook wasn't added (check ORDER file)
- `purple.install=1` is missing from the kernel cmdline

**"Payload not found"**
The hook can't find `/purple/install.sh` on the boot media. The ISO structure may be wrong. Mount the ISO and check that `/purple/install.sh` exists.

**Gate 2 screen doesn't appear**
The systemd service failed to start. Boot interactively and check:
```bash
systemctl status purple-confirm.service
journalctl -u purple-confirm.service
```

### QEMU-Specific Notes

- QEMU's default graphics may not support X11. The live boot test considers a login prompt as success, not the full Purple TUI.
- Use `-m 2048` or more. The live squashfs is large and casper needs RAM for the overlay.
- The `-snapshot` flag prevents writes to the ISO file, which is important for repeated testing.
- Serial console (`-serial stdio` or `-serial file:log.txt`) captures kernel and initramfs messages that aren't visible on the graphical console.

---

## Testing on Real Hardware

After VM testing passes, flash the ISO to a USB stick:

```bash
sudo ./flash-to-usb.sh /dev/sdX
```

Or manually:

```bash
sudo dd if=/opt/purple-installer/output/purple-installer-*.iso of=/dev/sdX bs=4M status=progress
sync
```

Then boot a test laptop from USB and verify:
1. GRUB menu shows "Purple Computer" as default
2. Auto-boot reaches Purple TUI (full experience, not just login prompt)
3. Internal disk is untouched (check with `lsblk` from tty2: Ctrl+Alt+F2)
4. Selecting "Install" from GRUB shows the confirmation screen
5. Pressing ESC at confirmation reboots safely
6. Pressing ENTER at confirmation writes the system to disk
