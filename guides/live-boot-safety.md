# Live Boot Safety: Your Existing System Is Untouched

When you boot a laptop from the Purple Computer USB, **nothing on the laptop changes**.
Your existing OS (Windows, macOS, Linux) is exactly as you left it. Remove the USB,
restart, and the laptop boots normally as if nothing happened.

This document explains how that guarantee works.

---

## The Short Answer

Purple Computer boots via Ubuntu Casper, a standard live-boot system that runs entirely
from RAM. The internal disk is never opened, never read for the OS, and never written to.
Removing the USB and restarting leaves the laptop exactly as it was.

---

## How It Works, Layer by Layer

### 1. Casper overlayfs (kernel-level)

Ubuntu's Casper mounts the squashfs from the USB as a read-only base, then adds a
RAM-backed overlay on top. Every write during the session goes to RAM. When you reboot,
that RAM is cleared. The internal disk is never involved.

### 2. Auto-mount is disabled

The GRUB boot entry passes `systemd.mask=udisks2.service` on the kernel command line.
udisks2 is the daemon that auto-mounts drives when they appear. With it masked, the
internal drive never gets mounted, even if a user found a terminal and poked around.

### 3. The boot hook does nothing to the internal disk

The only script that runs automatically at boot is `80_purple_installer` (a casper-bottom
hook). It:
- Restores a few dotfiles into the live overlay (RAM, not disk)
- Optionally creates a debug flag in the live overlay
- Paints the terminal purple

That is all. Its own source comment says: *"Installation is handled by the parent menu
in the running TUI, not by this hook."*

### 4. Installation requires deliberate action

The install-to-disk path requires all of these steps in sequence:

1. The system must be running from a live USB (checked via `/proc/cmdline`)
2. The USB payload file must be present at `/cdrom/purple/install.sh`
3. A parent must open the hidden parent menu (Escape hold)
4. A parent must navigate to and select the Install option
5. A confirmation dialog appears. The default button is **Cancel**. The parent must
   actively navigate up and press Enter to choose "Yes, install"
6. Only then does `install.sh` run

There is no way to reach this path by accident.

### 5. `install.sh` picks the internal disk carefully

Even after explicit confirmation, `install.sh` uses four independent checks before
touching any drive:

- Skips loop, RAM, ROM, and device-mapper devices by name
- Skips the boot device (identified by the `PURPLE_INSTALLER` volume label)
- Skips any device with `removable=1` in sysfs
- Skips any device with `transport=usb` (checked via both sysfs and udevadm)

If none survive all four filters, the script exits with an error. The wrong disk
cannot be selected.

### 6. NVRAM and EFI are only touched during install

`efibootmgr` and EFI partition writes only happen inside `install.sh`. They never run
during a live boot session. The GRUB config, casper hook, and systemd services that run
on live boot contain no NVRAM or EFI writes.

---

## Dual-Boot and Windows Machines

When installing to a machine that already has Windows:

- The installer checks for an existing `EFI/Microsoft/Boot/bootmgfw.efi` that matches
  Windows's expected file size range. If found, it is left alone.
- The installer writes Purple's boot files to additional EFI paths (`/EFI/BOOT/`,
  `/EFI/purple/`) that do not conflict with Windows.

This only applies during an explicit install, not during live boot.

---

## Files Referenced in This Document

| File | Role |
|------|------|
| `build-scripts/01-remaster-iso.sh` | Builds the ISO, sets GRUB params, creates boot hook |
| `build-scripts/install.sh` | Runs only on explicit install, handles disk detection and EFI setup |
| `purple_tui/rooms/parent_menu.py` | Install UI, confirmation dialogs, casper detection |
