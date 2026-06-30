# Purple Computer Architecture Overview

This document explains the Purple Computer build and boot architecture.

---

## The Two Systems

**There are two completely separate systems involved:**

| | USB (Live Boot) | Installed System |
|---|---------------|------------------|
| **What is it?** | Full Purple Computer running from USB | Permanent OS on laptop |
| **Where does it live?** | USB stick | Laptop's internal disk |
| **When is it used?** | Immediately, at any time | Every day, after installation |
| **What happens to it?** | Can be reused on any computer | Stays forever |
| **Does it touch the disk?** | No, internal disk is never mounted | It IS the internal disk |
| **Is it Ubuntu?** | Yes (Ubuntu 24.04 via casper live boot) | Yes (Ubuntu 24.04 LTS) |

These are **not** the same system. They share the same root filesystem (built once by debootstrap), but are packaged differently: squashfs for live boot, raw disk image for install.

---

## Architecture: Live Boot + Optional Install

The USB serves two purposes:

1. **Live boot (default)**: Boot directly into Purple Computer from USB. No installation, no disk writes, no waiting. The child plays immediately.
2. **Install (optional)**: A parent opens the parent menu inside the running TUI and chooses "Install on this Computer" to write the system to the internal disk permanently.

### Boot Flow

```
Parent plugs in USB, presses boot key

    GRUB menu (hidden, auto-boots):
      > "Purple Computer" (default)        → live boot
        "Boot from next volume"            → skip USB
        "UEFI Firmware Settings"           → BIOS/UEFI

    ┌─────────────────────────────────────────────────────────┐
    │ LIVE BOOT (the only production path)                    │
    │                                                         │
    │ Kernel boots with: boot=casper quiet ...                │
    │     ↓                                                   │
    │ casper mounts OUR squashfs + overlayfs                  │
    │     ↓                                                   │
    │ casper-bottom hook (80_purple_installer):               │
    │   restores dotfiles, sets debug mode, paints splash     │
    │   (does NOT gate install)                               │
    │     ↓                                                   │
    │ systemd starts → getty@tty1 auto-login as 'purple'      │
    │     ↓                                                   │
    │ purple-x11.service → Alacritty → Purple TUI            │
    │     ↓                                                   │
    │ Child plays. Internal disk never touched.               │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │ INSTALL (optional, from inside the running TUI)         │
    │                                                         │
    │ Parent menu (hold Escape 1s, PIN-gated)                 │
    │   → "Install on this Computer"                          │
    │     ↓                                                   │
    │ InstallProgressScreen runs /cdrom/purple/install.sh     │
    │   (sudo, while the live system keeps running)           │
    │     ↓                                                   │
    │ install.sh detects the internal disk, wipes it, and     │
    │ writes the golden image (purple-os.img.zst), then       │
    │ sets up UEFI boot                                       │
    │     ↓                                                   │
    │ "Press ENTER to restart" → execv into purple-reboot.    │
    │ USB can be removed after reboot.                        │
    └─────────────────────────────────────────────────────────┘
```

There is no "Install Purple Computer" GRUB entry and no `purple.install=1` arming in production: consent happens in the PIN-gated parent menu and the install confirmation screen, inside the TUI. (`purple.install=1` survives only as a developer/test switch that suppresses X11 so the install path can be exercised on a tty; see `test-boot.sh --mode install` and the debug ISO's "test install failure" entry.)

---

## What "Appliance" Means

**Appliance = does one job automatically, no configuration, no choices**

**The USB is an appliance (in live boot mode):**
- Boot from USB
- Hidden GRUB menu, auto-boots to Purple Computer
- No menus, no prompts, no configuration
- Child plays immediately
- USB can be removed after boot (see "USB Safe Removal" below)

**The installed system is NOT an appliance:**
- Normal Ubuntu 24.04 system
- Has apt, systemd, X11
- Auto-logins to Purple TUI application

(Offline by design: there are no over-the-air updates. A newer version means re-flashing the Purple Key.)

---

## Install Consent (Install Path Only)

Installation is wiping the internal disk, so it requires explicit consent, all inside the running TUI:

| Step | Where | What |
|------|-------|------|
| **Open parent menu** | Hold Escape 1s | PIN-gated, so kids can't reach it |
| **Choose install** | Parent menu | "Install on this Computer" |
| **Confirm** | Install screen | Clear data-loss warning before anything is written |

There is no GRUB-level or kernel-cmdline arming in production: the old `purple.install=1` + `purple-confirm.service` two-gate model has been replaced by this in-TUI flow. `install.sh` only runs when a parent walks through all three steps.

---

## What We Modify in the ISO

| Surface | What we do |
|---------|------------|
| **Squashfs** | Replace Ubuntu Server's squashfs with our Purple Computer squashfs |
| **GRUB config** | Hidden auto-boot menu, single "Purple Computer" live-boot entry |
| **Initramfs** | Add one casper-bottom hook (restores dotfiles, sets debug mode, paints splash) |
| **ISO filesystem** | Add `/purple/` directory with golden image payload + install.sh |

### What stays identical to Ubuntu ISO

| Component | Location | Why |
|-----------|----------|-----|
| Kernel | `/casper/vmlinuz` | Hardware compatibility |
| Shim/GRUB binaries | EFI partition | Secure Boot chain |
| Casper internals | Inside initramfs | Live boot plumbing |
| Boot configuration | EFI/MBR boot records | Boot on all hardware |

We never modify the kernel or casper's own scripts. The shim, GRUB, and MOK Manager binaries in the ISO's EFI partition are replaced at build time with the latest Ubuntu signed versions to avoid SBAT revocation on machines with updated firmware.

---

## USB Safe Removal (Live Boot)

After booting from USB, the system caches the entire squashfs filesystem into RAM so the USB drive can be physically removed.

**How it works:**

The live boot uses casper's overlayfs: the squashfs (read-only, on USB) is the lower layer, and a tmpfs (writable, in RAM) is the upper layer. Normally this means the USB must stay inserted because reads go to the squashfs on the USB.

At boot, a background process in xinitrc reads the entire squashfs file, which populates the kernel's page cache (RAM). Once every block has been read, all future filesystem reads are served from RAM, not from the USB. The USB is no longer needed.

**User-facing indicator:**

The TUI title bar shows a blinking USB icon while caching is in progress. When caching completes, the icon changes to a green eject symbol (⏏), telling the parent it's safe to remove the USB drive.

**Why not `toram`?** Casper supports a `toram` kernel parameter that copies the squashfs into RAM before booting. This blocks the entire boot until the copy finishes (30-90 seconds on USB 2.0). Our approach lets the child start playing immediately while caching happens in the background.

**Why we disable `casper-md5check.service`:** Ubuntu's casper includes an integrity check that reads the entire squashfs at boot to verify its MD5 checksum. We mask this service because: (1) if the squashfs is corrupted, the system is already broken since casper mounts it as the root filesystem, so corrupted files would cause crashes or missing files whether or not the check ran, (2) the check only logs a warning and proceeds with the corrupted squashfs anyway, it doesn't prevent boot or repair anything, and (3) reading the full squashfs at boot adds 30-90 seconds on USB.

**Note on install:** The "Install Purple Computer" option in the parent menu requires the USB to still be inserted, since the golden image payload (`purple/purple-os.img.zst`) is on the USB and is not part of the squashfs cache. If the USB has been removed, the install cannot proceed.

---

## Build Pipeline

### DRY Principle: One Root Filesystem, Two Packages

The same debootstrap root filesystem becomes both:
- **Squashfs** (for live boot): `filesystem.squashfs`
- **Golden image** (for install): `purple-os.img.zst`

```
debootstrap → full Purple root filesystem
    ├── mksquashfs → filesystem.squashfs (live boot)
    └── dd + zstd → purple-os.img.zst (install to disk)
```

### Step 0: Build root filesystem (`00-build-golden-image.sh`)

1. Create disk image, partition (GPT: ESP + root)
2. Debootstrap Ubuntu 24.04 minimal
3. Install packages (X11, Alacritty, Python, Purple TUI, etc.)
4. Configure system (auto-login, power management, etc.)
5. Create squashfs from the mounted root (`mksquashfs`)
6. Unmount, compress disk image (`zstd`)

### Step 1: Remaster ISO (`01-remaster-iso.sh`)

1. Download Ubuntu Server 24.04 ISO
2. Extract ISO contents
3. Replace squashfs with our Purple Computer squashfs
4. Modify initramfs (add install hook to casper-bottom)
5. Add golden image payload to `/purple/`
6. Update GRUB config (live boot default)
7. Rebuild ISO with xorriso

---

## What Runs Where

### On the USB

```
USB stick contains:
├── Signed boot stack (latest shim, GRUB, mmx64.efi, Ubuntu kernel)
├── Modified initramfs (with install hook)
├── casper/
│   ├── filesystem.squashfs  ← Purple Computer root filesystem
│   └── filesystem.size
├── boot/grub/grub.cfg       ← Live boot default menu
└── purple/
    ├── purple-os.img.zst    ← Golden image (for install only)
    └── install.sh           ← Run by the parent menu's install option
```

### On the internal disk (after install)

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

## Safety Design (Install Path)

Install is gated entirely in the running TUI, not in the boot chain:

1. **Parent menu is PIN-gated.** Reaching install means holding Escape for 1s and entering the PIN, so a child can't trigger it.
2. **Explicit data-loss confirmation.** `InstallProgressScreen` shows a clear warning before `install.sh` writes anything.
3. **`install.sh` self-protects.** It detects the internal disk while excluding USB/removable devices, so it won't wipe the Purple Key itself, and refuses to proceed if no safe target disk is found.

Live boot never touches the internal disk: nothing runs `install.sh` unless a parent walks the menu flow above. The casper-bottom hook is not part of this path; it only restores dotfiles, sets debug mode, and paints the splash.

---

## Initramfs/Casper Debugging Notes

General casper-bottom lessons that still apply when editing `80_purple_installer`:

### Path Confusion in Initramfs

The hook runs before the real root is pivoted in, so paths are not what they look like:

| What | Write to | Why |
|------|----------|-----|
| Files for the booted system | `/root/...` (e.g. `/root/home/purple/`) | `/root` is the mounted live root, becomes `/` |
| Runtime-only state | `/run/...` | The `/run` tmpfs is **moved** into the new root |
| **NOT** | `/root/run/...` | Gets shadowed when `/run` tmpfs is moved on top |

### ORDER File

Casper-bottom scripts are NOT auto-discovered. The file `/scripts/casper-bottom/ORDER` explicitly lists which scripts run and in what order. If your script isn't in ORDER, it will be silently ignored.

### Debugging Tips

1. **Add verbose logging**: Use `echo "[PREFIX] message" >/dev/console` to see output during boot
2. **Check serial console**: VM serial logs capture boot messages
3. **Test live boot**: `sudo ./test-boot.sh` (default mode)
4. **Test install**: `sudo ./test-boot.sh --mode install`
5. **Interactive**: `sudo ./test-boot.sh --interactive` to see the boot screen

---

## Glossary

| Term | Meaning |
|------|---------|
| **Golden image** | Pre-built Ubuntu system, created with debootstrap, compressed as purple-os.img.zst |
| **Squashfs** | Compressed read-only filesystem used by casper for live boot |
| **Initramfs** | Early boot filesystem loaded by kernel, contains scripts that run before real root |
| **Casper** | Ubuntu's scripts for live boot: mounts squashfs, sets up overlayfs |
| **Hook script** | Our script in `/scripts/casper-bottom/` (`80_purple_installer`) that restores dotfiles, sets debug mode, and paints the boot splash |
| **Live boot** | Running Purple Computer directly from USB via casper + squashfs |

---

## Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE KEY INSIGHT                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   The USB boots into Purple Computer by default.                │
│   No installation, no waiting, no disk writes.                  │
│                                                                 │
│   We replace Ubuntu's squashfs with our own (same root          │
│   filesystem that becomes the golden image). casper handles     │
│   all the live boot plumbing.                                   │
│                                                                 │
│   Installation is optional, started from the parent menu        │
│   inside the running TUI (PIN-gated, with a data-loss           │
│   confirmation) rather than from GRUB.                          │
│                                                                 │
│   Same root filesystem, two packages:                           │
│     squashfs (live boot) + disk image (install)                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
