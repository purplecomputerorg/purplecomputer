# Ubuntu ISO Remaster Architecture

This document describes the technical details of the ISO remaster process.

For the high-level architecture and design rationale, see [architecture-overview.md](architecture-overview.md).

---

## Why ISO Remaster?

### The Journey

The installer has gone through several iterations:

1. **Custom Kernel (v1)**: Built Linux 6.8.12 with all drivers `=y`. Failed on diverse hardware due to missing platform quirks and no Secure Boot.

2. **Debootstrap Live Root (v2)**: Built a live filesystem from scratch with Ubuntu's kernel, casper, and initramfs-tools. Failed due to complex dependency management and casper configuration issues.

3. **ISO Remaster (v3, current)**: Download the official Ubuntu Server ISO and modify it. This works because we treat Ubuntu's boot stack as a black box.

### Why Remaster Works

The key insight: **we don't need to build Ubuntu's live boot infrastructure—we just need to replace what runs after boot.**

Ubuntu Server ISO already has:
- Signed shim bootloader (Microsoft CA)
- Signed GRUB (Canonical)
- Signed kernel (Canonical)
- Working initramfs with casper
- All hardware quirks and drivers

All we do is:
1. Unsquash the filesystem
2. Mask Subiquity services
3. Add our payload
4. Resquash and rebuild ISO

---

## Architecture Overview

```
ISO Remaster Process
═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│                   Ubuntu Server 24.04 ISO                        │
│  • Official release from releases.ubuntu.com                    │
│  • Contains: shim, GRUB, kernel, initramfs, casper, Subiquity   │
│  • ~2.5 GB download (cached after first build)                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼ mount + extract
┌─────────────────────────────────────────────────────────────────┐
│                   ISO Contents Extraction                        │
│  • Copy all files to remaster/iso-contents/                     │
│  • Unsquash casper/filesystem.squashfs                          │
│  • Result: full Ubuntu live root in squashfs-root/              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼ modify squashfs-root
┌─────────────────────────────────────────────────────────────────┐
│                   Payload Injection                              │
│                                                                 │
│  1. Mask Subiquity services:                                    │
│     • subiquity.service                                         │
│     • snap.subiquity.* services                                 │
│     • cloud-init services                                       │
│     • snapd services                                            │
│                                                                 │
│  2. Add purple-installer.service:                               │
│     • Runs /opt/purple-installer/install.sh                     │
│     • Starts after multi-user.target                            │
│     • Outputs to tty1                                           │
│                                                                 │
│  3. Copy payload:                                               │
│     • /opt/purple-installer/purple-os.img.zst (golden image)    │
│     • /opt/purple-installer/install.sh (installer script)       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼ mksquashfs + xorriso
┌─────────────────────────────────────────────────────────────────┐
│                   ISO Rebuild                                    │
│  • Resquash modified filesystem                                 │
│  • Rebuild ISO with xorriso (preserves boot structure)          │
│  • Result: purple-installer-YYYYMMDD.iso                        │
│  • Size: ~4-5 GB                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## What We DON'T Touch

The following components remain **completely untouched** from the Ubuntu ISO:

| Component | Location | Why We Don't Touch It |
|-----------|----------|----------------------|
| Shim | `[BOOT]/` EFI partition | Microsoft-signed, enables Secure Boot |
| GRUB | `boot/grub/` | Canonical-signed, boot menu works |
| Kernel | `casper/vmlinuz` | Canonical-signed, has all drivers |
| Initramfs | `casper/initrd` | Casper scripts work, hardware detection works |
| GRUB config | `boot/grub/grub.cfg` | Boot parameters already correct |
| ISOLINUX | `isolinux/` | BIOS boot works |

---

## What We DO Modify

### 1. Mask Services

We mask these systemd services so they don't start:

```bash
SERVICES_TO_MASK=(
    "subiquity.service"
    "subiquity-service.service"
    "snap.subiquity.subiquity-service.service"
    "snap.subiquity.subiquity-server.service"
    "console-conf.service"
    "cloud-init.service"
    "cloud-init-local.service"
    "cloud-config.service"
    "cloud-final.service"
    "snapd.service"
    "snapd.socket"
    "snapd.seeded.service"
)
```

Masking creates symlinks to `/dev/null` in `/etc/systemd/system/`.

### 2. Add Installer Service

```ini
[Unit]
Description=Purple Computer Installer
After=multi-user.target
ConditionPathExists=/opt/purple-installer/purple-os.img.zst

[Service]
Type=oneshot
ExecStart=/opt/purple-installer/install.sh
StandardInput=tty
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes

[Install]
WantedBy=multi-user.target
```

### 3. Add Payload Files

```
/opt/purple-installer/
├── purple-os.img.zst    # Golden image (~1.5 GB compressed)
└── install.sh           # Installation script
```

---

## Boot Flow

```
USB Boot Flow (Remastered ISO)
═══════════════════════════════════════════════════════════════════

UEFI Firmware
    │
    ▼
shimx64.efi (Microsoft-signed, from Ubuntu ISO)
    │
    ▼
grubx64.efi (Canonical-signed, from Ubuntu ISO)
    │
    ▼
vmlinuz + initrd (Ubuntu kernel + casper initramfs, from Ubuntu ISO)
    │
    ▼
Casper live boot (from Ubuntu ISO, unchanged)
    │  • Mounts filesystem.squashfs
    │  • Sets up overlayfs
    │  • Switches to live root
    │
    ▼
systemd in live root
    │  • Subiquity is MASKED → doesn't start
    │  • purple-installer.service → STARTS
    │
    ▼
/opt/purple-installer/install.sh
    │  • Detects internal disk
    │  • Writes purple-os.img.zst to disk
    │  • Sets up UEFI boot entries
    │  • Reboots
    │
    ▼
Installed Purple Computer boots
```

---

## Build Scripts

### 00-build-golden-image.sh

Creates the pre-built Ubuntu system that gets written to disk:

- Uses debootstrap to create Ubuntu 24.04 base
- Installs linux-image-generic, grub-efi-amd64, X11, Alacritty
- Copies Purple TUI application
- Compresses to purple-os.img.zst (~1.5 GB)

### 01-remaster-iso.sh

Downloads and remasters the Ubuntu Server ISO:

1. **Download** Ubuntu Server ISO (cached)
2. **Mount** ISO read-only
3. **Extract** all files to working directory
4. **Unsquash** filesystem.squashfs
5. **Mask** Subiquity and cloud-init services
6. **Add** purple-installer.service
7. **Copy** payload (golden image + install script)
8. **Resquash** filesystem
9. **Rebuild** ISO with xorriso

### build-all.sh

Orchestrates the build:

```bash
./build-all.sh       # Run both steps
./build-all.sh 0     # Only golden image
./build-all.sh 1     # Only ISO remaster (uses existing golden image)
```

### build-in-docker.sh

Runs build inside Docker container for reproducibility.

---

## Comparison: Previous Approaches

| Aspect | Custom Kernel | Debootstrap Live | ISO Remaster |
|--------|---------------|------------------|--------------|
| Boot stack | Custom | Built from scratch | Ubuntu's (untouched) |
| Secure Boot | No | Theoretically yes | Yes |
| Hardware support | Limited | Depends on config | Excellent |
| Complexity | Very high | High | Low |
| Maintenance | High | High | Low |
| Debug difficulty | Hard | Hard | Easy |
| Build time | 60-90 min | 30-45 min | 20-35 min |

---

## Troubleshooting

### Build Issues

**"Failed to download Ubuntu ISO"**
- Check internet connection
- ISO URL may have changed; update `config.sh`

**"mksquashfs: Permission denied"**
- Run in Docker with `--privileged`
- Or run as root

**"xorriso: Cannot find isolinux.bin"**
- Ensure `isolinux` package is installed in Docker image

### Boot Issues

**Subiquity still appears**
- Service masking failed; check symlinks in squashfs-root
- Verify services are masked before resquash

**"No such file: purple-os.img.zst"**
- Golden image not copied to squashfs
- Check step 0 completed successfully

**Kernel panic or hang**
- This is Ubuntu's boot stack, not ours
- Try different USB port or device
- Check BIOS settings

### Installation Issues

**"No target disk found"**
- Disk may be USB-attached (shows as removable)
- Check `lsblk` output on tty2 (Alt+F2)

---

## Why Not Subiquity?

Subiquity is Ubuntu's server installer. We disable it because:

1. **Interactive**: Subiquity requires user input; we want zero-interaction
2. **Network-dependent**: Subiquity expects to download packages
3. **Wrong UX**: Subiquity installs packages; we write a disk image
4. **Snap-based**: Complex dependency on snapd

By masking Subiquity and adding our own service, we get:
- Automatic, non-interactive installation
- Fully offline operation
- Deterministic disk imaging
- Simple, auditable installer script

---

## Security Considerations

### Secure Boot

The remastered ISO maintains Secure Boot compatibility because:
- Shim is Microsoft-signed (unchanged)
- GRUB is Canonical-signed (unchanged)
- Kernel is Canonical-signed (unchanged)
- We only modify the squashfs (userspace)

### Supply Chain

The build downloads:
- **Ubuntu Server ISO**: From `releases.ubuntu.com` (HTTPS)
- **Ubuntu packages**: From `archive.ubuntu.com` (via debootstrap)

Both are official Ubuntu sources. Consider verifying ISO checksums in production.

---

**Document Version:** 2.0 (ISO Remaster)
**Architecture:** Ubuntu ISO Remaster
**Ubuntu Base:** 24.04.1 LTS (Noble Numbat)
