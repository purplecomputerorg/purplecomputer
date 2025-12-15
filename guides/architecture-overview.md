# Purple Computer Architecture Overview

This document explains the Purple Computer installer architecture and the design decisions behind it.

---

## The Two Systems

**There are two completely separate systems involved:**

| | USB Installer | Installed System |
|---|---------------|------------------|
| **What is it?** | Temporary boot environment | Permanent OS on laptop |
| **Where does it live?** | USB stick | Laptop's internal disk |
| **When is it used?** | Once, during installation | Every day, by kids |
| **What happens to it?** | USB is removed and forgotten | Stays forever |
| **Is it Ubuntu?** | Yes (Ubuntu Server live) | Yes (Ubuntu 24.04 LTS) |

These are **not** the same system. They have different jobs. They are built differently.

---

## What "Appliance" Means

**Appliance = does one job automatically, no configuration, no choices**

**The USB installer is an appliance:**
- Boot from USB
- Automatically finds the internal disk
- Automatically writes the system image
- Automatically sets up the bootloader
- Automatically reboots

**The installed system is NOT an appliance:**
- Normal Ubuntu 24.04 system
- Has apt, systemd, X11
- Receives updates from Ubuntu's servers
- Auto-logins to Purple TUI application

---

## Architecture: Initramfs Injection

We intercept boot **before** Ubuntu's live system starts.

```
Boot Flow
=========

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
    │       └── If not found: Continue to casper
    │
    ▼
casper mounts squashfs (only if our hook didn't run)
    │
    ▼
Normal Ubuntu live boot
```

**Key insight:** We run our installer in initramfs, before casper ever mounts the squashfs. The squashfs and Ubuntu's live system are never touched.

---

## What We Modify

**Only the initramfs.** We add a single hook script to `/scripts/init-top/`.

The hook:
1. Checks if our payload exists on the boot device
2. If yes: mounts it, runs `install.sh`, reboots
3. If no: exits, lets casper continue normally

**Everything else is untouched:**
- Shim (Microsoft-signed)
- GRUB (Canonical-signed)
- Kernel (Canonical-signed)
- Squashfs (all layers)
- Casper scripts

---

## What Runs Where

### On the USB (temporary)

```
USB stick contains:
├── Ubuntu's boot stack (shim, GRUB, kernel)
├── Modified initramfs (with our hook)
├── Ubuntu's squashfs layers (untouched, never used)
└── /purple/
    ├── purple-os.img.zst (golden image)
    └── install.sh (installer script)
```

### On the internal disk (permanent)

```
Internal disk contains:
├── Standard Ubuntu 24.04 LTS
├── Linux kernel (Ubuntu's linux-image-generic)
├── GRUB bootloader
├── X11 + Alacritty terminal
├── Purple TUI application
└── Everything needed to run Purple Computer
```

---

## Why Initramfs Injection?

We tried many approaches before arriving here:

| Approach | Problem |
|----------|---------|
| Custom kernel | Missing hardware quirks, no Secure Boot |
| Custom initramfs | BusyBox can't load .ko.zst modules |
| Debootstrap live root | Casper dependency hell |
| Squashfs remastering (Server) | Layered squashfs is complex |
| Squashfs remastering (Desktop) | Also layered in 24.04 |

**Initramfs injection works because:**
- We use Ubuntu's initramfs-tools hook system (supported)
- We run before casper, so squashfs structure doesn't matter
- We keep all signed components intact (Secure Boot works)
- Minimal modification (one small script)

---

## Non-Goals

We are **NOT** trying to:

- Make Ubuntu's installer work offline
- Install packages during installation
- Minimize the live environment
- Build a custom kernel
- Modify the squashfs
- Understand layered squashfs internals

---

## Glossary

| Term | Meaning |
|------|---------|
| **Golden image** | Pre-built Ubuntu system, created with debootstrap, compressed as purple-os.img.zst |
| **Initramfs** | Early boot filesystem loaded by kernel, contains scripts that run before real root |
| **Casper** | Ubuntu's scripts for live boot, mounts squashfs, we bypass it entirely |
| **Hook script** | Our script in `/scripts/init-top/` that checks for and runs installer |

---

## Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE KEY INSIGHT                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   We don't modify Ubuntu live.                                  │
│   We intercept boot BEFORE Ubuntu live starts.                  │
│                                                                 │
│   Our hook runs in initramfs.                                   │
│   If our payload exists: install and reboot.                    │
│   If not: fall through to normal Ubuntu.                        │
│                                                                 │
│   The squashfs is never mounted when our installer runs.        │
│   Layered squashfs? Doesn't matter. We don't use it.            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
