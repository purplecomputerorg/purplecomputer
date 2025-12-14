# Purple Computer Architecture Overview

This document explains the Purple Computer installer architecture and the design decisions behind it. It's intended to prevent re-entering the same architectural loops we've already worked through.

---

## The Single Most Important Thing to Understand

**There are two completely separate systems involved:**

| | USB Installer | Installed System |
|---|---------------|------------------|
| **What is it?** | Temporary boot environment | Permanent OS on laptop |
| **Where does it live?** | USB stick | Laptop's internal disk |
| **When is it used?** | Once, during installation | Every day, by kids |
| **What happens to it?** | USB is removed and forgotten | Stays forever |
| **Is it Ubuntu?** | Yes (Ubuntu Server live) | Yes (Ubuntu 24.04 LTS) |
| **Can you apt install?** | Technically yes, but why | Yes, normal Ubuntu |

These are **not** the same system. They have different jobs. They are built differently. Keeping them separate in your head will prevent confusion.

---

## What "Appliance" Means Here

The word "appliance" appears in this project. Here's what it means:

**Appliance = does one job automatically, no configuration, no choices**

Think of a toaster. You put bread in, push the lever, toast comes out. You don't configure the toaster. You don't choose which heating algorithm to use. It just does its job.

**The USB installer is an appliance:**
- Boot from USB
- It automatically finds the internal disk
- It automatically writes the system image
- It automatically sets up the bootloader
- It automatically reboots
- Done

**The installed system is NOT an appliance:**
- It's a normal Ubuntu 24.04 system
- It has apt, systemd, X11, everything
- It can receive updates from Ubuntu's servers
- It happens to auto-login and run a specific application (Purple TUI)

**"Appliance" does NOT mean:**
- Not Ubuntu
- Not updateable
- Not a real Linux system
- Locked down or restricted

---

## What Runs Where

### On the USB (temporary, during installation)

```
USB stick contains:
├── Ubuntu's boot stack (shim, GRUB, kernel, initramfs)
├── Ubuntu's live infrastructure (casper)
├── Squashfs filesystem containing:
│   ├── Minimal Ubuntu Server environment
│   ├── Our installer script
│   ├── Our systemd service (runs instead of Subiquity)
│   └── The golden image (purple-os.img.zst) ← this is the prize
```

The USB environment's **only job** is to copy `purple-os.img.zst` to the internal disk. That's it. After reboot, the USB is garbage. You could throw it away.

### On the internal disk (permanent, what kids use)

```
Internal disk contains:
├── Standard Ubuntu 24.04 LTS
├── Linux kernel (Ubuntu's linux-image-generic)
├── GRUB bootloader
├── X11 + Alacritty terminal
├── Purple TUI application
├── Python, pygame, piper-tts, etc.
└── Everything needed to run Purple Computer
```

This is a **normal Ubuntu system**. It boots normally. It can run `apt update`. It has systemd. It's not special or magical. It just happens to auto-login to a specific application.

---

## What "Ubuntu Live" Means

**Ubuntu live = boots from removable media without touching the internal disk**

When you boot an Ubuntu ISO, you get a "live" environment. This means:
- The OS runs entirely from the USB/DVD
- The internal disk is untouched until you choose to install
- Changes are lost when you reboot (unless you install)

**Using Ubuntu live does NOT mean:**
- Using Ubuntu's graphical installer
- Using Subiquity (Ubuntu Server's installer)
- Using any installer UI at all

**Subiquity is just an application.** It happens to run by default on Ubuntu Server live ISOs. But it's not magic. It's not required. We simply... don't run it.

Our approach:
1. Take Ubuntu Server's live ISO
2. Disable Subiquity (mask the systemd service)
3. Enable our own service instead
4. That service runs our installer script
5. Our script writes a disk image

We're not "hacking" Ubuntu live. We're just running a different program.

---

## Step-by-Step: What Actually Happens

### Installation (one time)

```
1. Human inserts USB into old laptop
2. Human boots from USB
   └── UEFI loads shim → GRUB → kernel → initramfs → casper
3. Ubuntu live environment starts
   └── This is Ubuntu Server, running from USB, in RAM
4. Systemd starts services
   └── Subiquity is masked → doesn't start
   └── purple-installer.service → STARTS
5. Our installer script runs automatically
   ├── Finds internal disk (not the USB)
   ├── Writes purple-os.img.zst to disk (dd)
   └── Sets up UEFI boot entries
6. Script prompts: "Remove USB and press Enter"
7. System reboots
8. USB is no longer involved in anything, ever
```

### Daily use (forever after)

```
1. Kid presses power button
2. Laptop boots from internal disk
   └── Normal Ubuntu boot: GRUB → kernel → systemd
3. Auto-login to 'purple' user
4. X11 starts, runs Alacritty + Purple TUI
5. Kid uses Purple Computer
6. (Optional: system updates via apt in background)
```

The USB installer is **completely irrelevant** after step 8. The installed system is **completely independent**.

---

## Why Earlier Approaches Were Confusing

We kept trying to make **one system** do **two conflicting jobs**:

| Goal A: Minimal Installer | Goal B: Full Ubuntu Boot |
|---------------------------|--------------------------|
| Tiny, fast, simple | Comprehensive driver support |
| Custom initramfs | Ubuntu's casper infrastructure |
| Hand-picked packages | Let apt resolve dependencies |
| We control everything | Ubuntu controls boot stack |

**These goals conflict.** Every time we tried to satisfy both, we created problems:

- Custom kernel → missing platform drivers, no Secure Boot
- Custom initramfs → dependency hell, missing casper scripts
- Debootstrap live root → casper package conflicts, missing lzma
- Manual module loading → BusyBox can't load .ko.zst files

**The solution was to stop trying.** We separated the concerns:

- **Installer USB:** Use Ubuntu's official ISO. Don't rebuild anything. Just add our payload.
- **Installed system:** Use debootstrap to build exactly what we want.

---

## Why We Stopped Building Ubuntu Live From Scratch

We tried. Multiple times. Here's what happened:

### Attempt 1: Custom kernel with all drivers built-in
- **Problem:** Missing platform quirks (Surface, Dell, HP all have ACPI weirdness)
- **Problem:** No Secure Boot (our kernel isn't signed)
- **Lesson:** Ubuntu's kernel exists for a reason

### Attempt 2: Ubuntu kernel + custom initramfs
- **Problem:** BusyBox can't load .ko.zst modules (Ubuntu uses zstd compression)
- **Problem:** Module dependency resolution is complex
- **Lesson:** Ubuntu's kmod and initramfs-tools exist for a reason

### Attempt 3: Debootstrap a live root with casper
- **Problem:** Casper has unlisted dependencies
- **Problem:** Circular dependency issues
- **Problem:** Different Ubuntu versions have different casper requirements
- **Lesson:** Ubuntu's ISO build process exists for a reason

### Attempt 4 (current): Remaster official Ubuntu ISO
- **Result:** It just works
- **Why:** We stopped fighting Ubuntu's boot stack and started using it

**The key insight:** We don't need to build Ubuntu's live boot infrastructure. We just need to run a different program after it boots.

---

## Explicit Non-Goals

To prevent future confusion, here's what we are **NOT** trying to do:

### We are NOT making Subiquity work offline
Subiquity is Ubuntu's server installer. It's designed to download packages from the internet. We don't use it at all. We replace it entirely with a simple disk-imaging script.

### We are NOT installing packages during installation
The installed system is pre-built (the "golden image"). During installation, we just copy bytes to disk. No apt. No dpkg. No package resolution. Just `zstd -dc | dd`.

### We are NOT minimizing the live environment
The USB environment includes the full Ubuntu Server live system. It's "wasteful" (~2.5GB squashfs). We don't care. It works. Disk space is cheap. Our time is not.

### We are NOT building a custom kernel for the installer
Ubuntu's kernel works. It has Secure Boot signatures. It has all the drivers. We use it as-is.

### We are NOT building a custom initramfs for the installer
Ubuntu's initramfs works. It has casper. It handles hardware detection. We use it as-is.

### We are NOT modifying Ubuntu's boot stack
Shim, GRUB, kernel, initramfs, casper - all untouched from the official Ubuntu ISO. We only modify the squashfs to add our payload and disable Subiquity.

---

## Glossary

| Term | Meaning in this project |
|------|------------------------|
| **Golden image** | The pre-built Ubuntu system that gets installed. Created with debootstrap. Compressed as purple-os.img.zst. |
| **Live environment** | An OS that boots from removable media without installing. The USB runs Ubuntu live. |
| **Casper** | Ubuntu's scripts for live boot. Mounts squashfs, sets up overlayfs, etc. We don't modify it. |
| **Squashfs** | Compressed read-only filesystem. The USB's live root is stored as squashfs. |
| **Subiquity** | Ubuntu Server's installer UI. We disable it completely. |
| **Remaster** | Taking an existing ISO and modifying it. We remaster Ubuntu Server ISO. |
| **Appliance** | A device that does one job automatically. The USB installer is an appliance. |

---

## Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE TWO SYSTEMS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   USB INSTALLER                    INSTALLED SYSTEM             │
│   ─────────────                    ────────────────             │
│   • Ubuntu Server live ISO         • Ubuntu 24.04 LTS           │
│   • Remastered (not rebuilt)       • Built with debootstrap     │
│   • Runs once                      • Runs forever               │
│   • Job: copy image to disk        • Job: be Purple Computer    │
│   • Discarded after use            • Updated via apt            │
│                                                                 │
│   We use Ubuntu's boot stack       We build exactly what we     │
│   exactly as-is. We only add       want. Standard Ubuntu with   │
│   our payload and disable          Purple TUI pre-installed.    │
│   Subiquity.                                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

The USB installer's only job is to copy the installed system to disk.
After that, the USB is irrelevant. These are separate systems.
```

---

The two-system mental model is the key to understanding everything else in this project.
