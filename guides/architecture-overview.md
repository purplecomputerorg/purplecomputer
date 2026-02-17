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
2. **Install (optional)**: A parent can select "Install Purple Computer" from the GRUB menu to write the system to the internal disk permanently.

### Boot Flow

```
Parent plugs in USB, presses boot key

    GRUB menu (5s auto-boot):
      > "Purple Computer" (default)        → live boot, no disk writes
        "Install Purple Computer"          → install to internal disk
        "Boot from next volume"            → skip USB
        "UEFI Firmware Settings"           → BIOS/UEFI

    ┌─────────────────────────────────────────────────────────┐
    │ LIVE BOOT PATH (default)                                │
    │                                                         │
    │ Kernel boots with: boot=casper quiet ...                │
    │ (NO purple.install=1)                                   │
    │     ↓                                                   │
    │ casper mounts OUR squashfs + overlayfs                  │
    │     ↓                                                   │
    │ Initramfs hook: no purple.install=1 → does nothing      │
    │     ↓                                                   │
    │ systemd starts → getty@tty1 auto-login as 'purple'      │
    │     ↓                                                   │
    │ .bashrc → startx → Alacritty → Purple TUI              │
    │     ↓                                                   │
    │ Child plays. Internal disk never touched.               │
    └─────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────┐
    │ INSTALL PATH (parent selects from GRUB menu)            │
    │                                                         │
    │ Kernel boots with: boot=casper ... purple.install=1     │
    │     ↓                                                   │
    │ casper mounts squashfs + overlayfs (same as live boot)  │
    │     ↓                                                   │
    │ Gate 1: hook finds purple.install=1                     │
    │   → Masks getty@tty1 (prevents auto-login/X11/Purple)  │
    │   → Writes purple-confirm.service to /root/etc/systemd/ │
    │   → Writes scripts to /run/purple/                      │
    │     ↓                                                   │
    │ Gate 2: purple-confirm.service on tty1                  │
    │   "This will erase all data. Press ENTER to continue."  │
    │     ↓                                                   │
    │ install.sh writes golden image to internal disk          │
    │     ↓                                                   │
    │ Reboot. USB can be removed.                             │
    └─────────────────────────────────────────────────────────┘
```

---

## What "Appliance" Means

**Appliance = does one job automatically, no configuration, no choices**

**The USB is an appliance (in live boot mode):**
- Boot from USB
- 5-second auto-boot to Purple Computer
- No menus, no prompts, no configuration
- Child plays immediately

**The installed system is NOT an appliance:**
- Normal Ubuntu 24.04 system
- Has apt, systemd, X11
- Receives updates from Ubuntu's servers
- Auto-logins to Purple TUI application

---

## Two-Gate Safety Model (Install Path Only)

Installation requires passing **two independent safety gates**:

| Gate | When | What | Purpose |
|------|------|------|---------|
| **Gate 1** | Initramfs (casper-bottom) | Check `purple.install=1` in cmdline | Design-time arming |
| **Gate 2** | Userspace (systemd) | Show confirmation, require ENTER | Runtime user consent |

**Arming != Asking user.** Gate 1 is set by the GRUB menu selection. Gate 2 requires explicit human action.

**Key insight:** The installer ONLY runs if:
1. `purple.install=1` was in kernel cmdline (Gate 1, selected from GRUB menu)
2. User pressed ENTER on confirmation screen (Gate 2)

In live boot mode, `purple.install=1` is absent, so the hook is a no-op.

---

## What We Modify in the ISO

| Surface | What we do |
|---------|------------|
| **Squashfs** | Replace Ubuntu Server's squashfs with our Purple Computer squashfs |
| **GRUB config** | Live boot default, install as menu option |
| **Initramfs** | Add one hook script to `/scripts/casper-bottom/` |
| **ISO filesystem** | Add `/purple/` directory with golden image payload |

### What stays identical to Ubuntu ISO

| Component | Location | Why |
|-----------|----------|-----|
| Kernel | `/casper/vmlinuz` | Hardware compatibility |
| Shim/GRUB binaries | EFI partition | Secure Boot chain |
| Casper internals | Inside initramfs | Live boot plumbing |
| Boot configuration | EFI/MBR boot records | Boot on all hardware |

We never modify the kernel, shim, GRUB binary, or casper's own scripts.

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
├── Ubuntu's boot stack (shim, GRUB, kernel)
├── Modified initramfs (with install hook)
├── casper/
│   ├── filesystem.squashfs  ← Purple Computer root filesystem
│   └── filesystem.size
├── boot/grub/grub.cfg       ← Live boot default menu
└── purple/
    ├── purple-os.img.zst    ← Golden image (for install only)
    ├── install.sh
    └── purple-confirm.sh
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

### Gate 1: Casper-Bottom Hook

The hook script `/scripts/casper-bottom/80_purple_installer`:

1. Checks for `purple.install=1` in kernel cmdline
2. If NOT found: exits immediately (live boot continues normally)
3. If found: checks for payload at `/root/cdrom/purple/`
4. If payload found: writes runtime artifacts, masks getty@tty1
5. If no payload: exits, live boot continues

### Gate 2: Confirmation Service

The systemd service `purple-confirm.service`:

1. Only runs if `/run/purple/armed` exists
2. Shows large, clear warning about data erasure
3. Waits for explicit user input (ENTER to proceed, ESC to cancel)
4. Has timeout (5 minutes) to prevent stuck systems

**What the confirmation screen shows:**
```
╔══════════════════════════════════════════╗
║   WARNING: DATA LOSS AHEAD              ║
╚══════════════════════════════════════════╝

This will ERASE ALL DATA on this computer's internal drive.
Everything currently on the hard drive will be permanently deleted.
This action CANNOT be undone.

Press ENTER to install Purple Computer
Press ESC to cancel and reboot
```

### Fail-Open Behavior

Every failure mode results in safe state (live boot, no installation):

| Failure | Gate | Result |
|---------|------|--------|
| No `purple.install=1` | 1 | Live boot (normal) |
| No payload found | 1 | Live boot (normal) |
| No `/run/purple/armed` | 2 | Service doesn't run |
| User presses ESC | 2 | Reboot, no install |
| Input timeout (5 min) | 2 | Reboot, no install |
| Keyboard disconnected | 2 | Show error, reboot |

### Test Matrix

| Scenario | Gate 1 | Gate 2 | Result |
|----------|--------|--------|--------|
| Live boot (default) | SKIP | N/A | Purple Computer from USB |
| Normal install | PASS | PASS (ENTER) | Installs to disk |
| User cancels | PASS | FAIL (ESC) | Reboots |
| Broken payload | FAIL | N/A | Live boot |
| USB removed mid-boot | FAIL | N/A | Live boot |
| Keyboard unplugged | PASS | FAIL (error) | Reboots |
| Input timeout | PASS | FAIL (timeout) | Reboots |

---

## Initramfs/Casper Debugging Notes

Hard-won lessons from debugging the casper-bottom hook:

### Path Confusion in Initramfs

| What | Write to | Why |
|------|----------|-----|
| Systemd units | `/root/etc/systemd/system/` | Persists on root filesystem, becomes `/etc/systemd/system/` |
| Runtime scripts | `/run/purple/` | The `/run` tmpfs is **moved** into new root |
| Marker files | `/run/purple/armed` | Same reason: use `/run`, not `/root/run` |
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
| **Hook script** | Our script in `/scripts/casper-bottom/` that checks for arming and writes runtime artifacts |
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
│   Installation is optional, accessed via GRUB menu:             │
│     - Gate 1 (initramfs hook): checks purple.install=1         │
│     - Gate 2 (systemd service): requires ENTER to proceed      │
│                                                                 │
│   Same root filesystem, two packages:                           │
│     squashfs (live boot) + disk image (install)                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
