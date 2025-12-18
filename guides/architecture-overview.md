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

## Architecture: Two-Gate Safety Model

Installation requires passing **two independent safety gates**:

| Gate | When | What | Purpose |
|------|------|------|---------|
| **Gate 1** | Initramfs (casper-bottom) | Check `purple.install=1` in cmdline | Design-time arming |
| **Gate 2** | Userspace (systemd) | Show confirmation, require ENTER | Runtime user consent |

**Arming ≠ Asking user.** Gate 1 is set by the ISO builder. Gate 2 requires explicit human action.

```
Boot Flow (Two-Gate Model)
==========================

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
casper mounts squashfs, sets up /run
    │
    ▼
═══════════════════════════════════════════════════════════
                    GATE 1: DESIGN-TIME ARMING
═══════════════════════════════════════════════════════════
casper runs casper-bottom scripts (after /run is ready)
    │
    ├── [Purple hook: 80_purple_installer]
    │       │
    │       ├── Check cmdline for purple.install=1
    │       │       │
    │       │       ├── NOT ARMED → Gate 1 CLOSED → normal Ubuntu boot
    │       │       │
    │       │       └── ARMED → check payload at /cdrom/purple/
    │       │               │
    │       │               ├── Found → write runtime artifacts to /run/:
    │       │               │           - /run/purple/armed (marker)
    │       │               │           - /run/purple/confirm.sh (script)
    │       │               │           - /run/systemd/system/purple-confirm.service
    │       │               │           Gate 1 PASSED → continue boot
    │       │               │
    │       │               └── Not found → Gate 1 CLOSED → normal Ubuntu boot
    │
    ▼
systemd starts (picks up runtime units from /run/systemd/system/)
    │
    ▼
═══════════════════════════════════════════════════════════
                    GATE 2: RUNTIME USER CONFIRMATION
═══════════════════════════════════════════════════════════
purple-confirm.service runs (only if /run/purple/armed exists)
    │
    ├── Shows large warning: "This will ERASE ALL DATA"
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

**Key insight:** The installer ONLY runs if:
1. `purple.install=1` was in kernel cmdline (Gate 1)
2. User pressed ENTER on confirmation screen (Gate 2)

---

## Immutable Components (DO NOT TOUCH)

The following must remain **identical to the official Ubuntu ISO**:

| Component | Location | Why |
|-----------|----------|-----|
| Kernel | `/casper/vmlinuz` | Hardware compatibility |
| Kernel modules | Inside squashfs | Driver support |
| Casper internals | Inside initramfs | Live boot magic |
| Squashfs layers | `/casper/*.squashfs` | Live root filesystem |
| Live rootfs | `/usr`, `/etc`, `/lib` inside squashfs | Ubuntu's system |

**We NEVER:**
- Unsquash or resquash filesystem layers
- Search for or guess a "main" squashfs
- Create custom squashfs overlays
- Write to `/etc` or `/usr` inside the live system
- Add files to casper layers
- Modify live rootfs systemd units

## What We Modify (ONLY THESE)

| Surface | What we do |
|---------|------------|
| **GRUB config** | Add `purple.install=1` to cmdline, add debug entry |
| **Initramfs** | Add one hook script to `/scripts/casper-bottom/` |
| **ISO filesystem** | Add `/purple/` directory with payload |

The casper-bottom hook (`80_purple_installer`):
1. Checks if `purple.install=1` is in kernel cmdline (Gate 1)
2. If not armed: exits immediately, normal Ubuntu boot
3. If armed: checks for payload at `/root/cdrom/purple/` (see path notes below)
4. If payload found: writes runtime artifacts to `/root/run/`, continues boot
5. If no payload: exits, lets boot continue normally

**Why casper-bottom (not init-top)?**
- `init-top` runs BEFORE casper mounts the live root
- Files written to `/run` in `init-top` are LOST during `switch_root`
- `casper-bottom` runs AFTER the real `/run` tmpfs is mounted
- This is the same mechanism Ubuntu's own scripts use (e.g., `55disable_snap_refresh`)

**Critical path notes for casper-bottom scripts:**
- In casper-bottom, the real root filesystem is mounted at `/root`
- The live media (ISO/USB) is mounted at `/root/cdrom`, NOT `/cdrom`
- **Systemd units must go to `/root/etc/systemd/system/`** (NOT `/root/run/systemd/system/`)
  - `/run` tmpfs gets mounted OVER `/root/run` during switch_root, hiding any files written there
  - `/etc/systemd/system/` has highest priority in systemd's unit load path and survives switch_root
- Scripts can go to `/root/run/purple/` (the `/run` tmpfs is moved, not remounted fresh)
- The ORDER file (`/scripts/casper-bottom/ORDER`) controls which scripts run - scripts not listed are silently ignored

**Gate 2 is implemented via systemd units written to `/root/etc/systemd/system/`** - NOT by modifying squashfs.

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

## Safety Design

The installer follows strict safety requirements to prevent accidental data loss.

### Two-Gate Model Explained

| | Gate 1 (Arming) | Gate 2 (Confirmation) |
|---|-----------------|----------------------|
| **When** | Early boot (initramfs) | Userspace (systemd) |
| **Who sets it** | ISO builder (design-time) | User (runtime) |
| **How to pass** | `purple.install=1` in cmdline | Press ENTER |
| **How to fail** | Remove from cmdline | Press ESC or timeout |
| **What happens on fail** | Normal Ubuntu boot | Reboot, no install |

**Arming ≠ Confirmation:**
- Arming (Gate 1) is a design decision made when building the ISO
- Confirmation (Gate 2) is a runtime decision made by the user

### Gate 1: Casper-Bottom Hook

The hook script `/scripts/casper-bottom/80_purple_installer`:

1. Checks for `purple.install=1` in kernel cmdline
2. Checks for payload at `/root/cdrom/purple/` (where casper mounts live media)
3. Writes artifacts:
   - `/run/purple/confirm.sh` - confirmation script (to `/run`, NOT `/root/run`!)
   - `/root/etc/systemd/system/purple-confirm.service` - systemd unit
   - Service masks in `/root/etc/systemd/system/`
4. Exits cleanly—after switch_root, systemd loads unit and runs `/run/purple/confirm.sh`

**What the hook is NOT allowed to do:**
- ❌ Run the installer
- ❌ Source external scripts (only `/scripts/functions`)
- ❌ Load kernel modules
- ❌ Modify squashfs or casper behavior
- ❌ Block indefinitely on any operation
- ❌ Include UI logic
- ❌ Write to squashfs or live rootfs

### Gate 2: Confirmation Service

The systemd service `purple-confirm.service`:

1. Only runs if `/run/purple/armed` exists
2. Shows large, clear warning about data erasure
3. Waits for explicit user input (ENTER to proceed, ESC to cancel)
4. Has timeout (5 minutes) to prevent stuck systems
5. Handles keyboard failures gracefully (shows error, reboots)

**What the confirmation screen shows:**
```
╔══════════════════════════════════════════╗
║   ⚠️   WARNING: DATA LOSS AHEAD   ⚠️      ║
╚══════════════════════════════════════════╝

This will ERASE ALL DATA on this computer's internal drive.
Everything currently on the hard drive will be permanently deleted.
This action CANNOT be undone.

Press ENTER to install Purple Computer
Press ESC to cancel and reboot
```

### Fail-Open Behavior

Every failure mode results in safe state (no installation):

| Failure | Gate | Result |
|---------|------|--------|
| No `purple.install=1` | 1 | Normal Ubuntu boot |
| No payload found | 1 | Normal Ubuntu boot |
| Device scan timeout | 1 | Continue scan, then normal boot |
| No `/run/purple/armed` | 2 | Service doesn't run |
| User presses ESC | 2 | Reboot, no install |
| Input timeout (5 min) | 2 | Reboot, no install |
| Keyboard disconnected | 2 | Show error, reboot |
| Payload removed | 2 | Show error, reboot |

### Bounded Operations

All operations have limits:

| Operation | Timeout/Limit |
|-----------|---------------|
| Device wait (Gate 1) | 10 seconds |
| Device scan (Gate 1) | 20 devices max |
| User input (Gate 2) | 5 minutes |
| Keyboard test (Gate 2) | 10 seconds |

### Loud Logging

All operations log to `/dev/console`:

```
[PURPLE] === Purple Computer Installer Hook (Gate 1) ===
[PURPLE] ARMED: purple.install=1 found in cmdline
[PURPLE] Gate 1: OPEN - Proceeding to payload check
[PURPLE] Scanning for Purple installer payload...
[PURPLE]   Checking /dev/sda1...
[PURPLE] FOUND: Purple installer payload on /dev/sda1
[PURPLE] Gate 1: PASSED
[PURPLE-CONFIRM] Gate 2: Marker file found - Gate 1 passed
[PURPLE-CONFIRM] Waiting for user confirmation...
```

### Debug Boot

The ISO includes a GRUB menu entry "Debug Mode (no install)" that:

- Boots without `purple.install=1`
- Gate 1 fails immediately
- Drops into normal Ubuntu Server live environment
- Allows manual inspection and recovery

### Test Matrix

| Scenario | Gate 1 | Gate 2 | Result |
|----------|--------|--------|--------|
| Normal install | PASS | PASS (ENTER) | ✅ Installs |
| User cancels | PASS | FAIL (ESC) | ❌ Reboots |
| Debug boot | FAIL | N/A | ❌ Ubuntu live |
| Broken payload | FAIL | N/A | ❌ Ubuntu live |
| USB removed mid-boot | FAIL | N/A | ❌ Ubuntu live |
| Keyboard unplugged | PASS | FAIL (error) | ❌ Reboots |
| Input timeout | PASS | FAIL (timeout) | ❌ Reboots |

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

## Initramfs/Casper Debugging Notes

Hard-won lessons from debugging the casper-bottom hook:

### Path Confusion in Initramfs

The initramfs environment has a confusing filesystem layout:

| What | Write to | Why |
|------|----------|-----|
| Systemd units | `/root/etc/systemd/system/` | Persists on root filesystem, becomes `/etc/systemd/system/` |
| Runtime scripts | `/run/purple/` | The `/run` tmpfs is **moved** into new root |
| Marker files | `/run/purple/armed` | Same reason - use `/run`, not `/root/run` |
| **NOT** | `/root/run/...` | Gets shadowed when `/run` tmpfs is moved on top |

**The `/run` shadowing trap:**

There are TWO different locations that look similar:
- **`/run/`** - A tmpfs that gets **moved** into the new root. Files survive.
- **`/root/run/`** - A directory on the root filesystem. When `/run` tmpfs is moved on top, files here get **hidden**.

Think of it like putting a file in a folder, then someone places a box on top - the file is still there but inaccessible.

**Path translation for marker files:**

Paths found during initramfs (e.g., `/root/cdrom/purple`) must be translated for post-switch_root use:
```bash
# In initramfs: /root/cdrom/purple
# After switch_root: /cdrom/purple
PAYLOAD_PATH_FINAL=$(echo "$PAYLOAD_PATH" | sed 's|^/root||')
```

### ORDER File

Casper-bottom scripts are NOT auto-discovered. The file `/scripts/casper-bottom/ORDER` explicitly lists which scripts run and in what order. If your script isn't in ORDER, it will be silently ignored.

To add a script:
```bash
sed -i '/99casperboot/i /scripts/casper-bottom/80_purple_installer "$@"\n[ -e /conf/param.conf ] && . /conf/param.conf' ORDER
```

### Casper Functions

Casper-bottom scripts must source casper functions:
```bash
. /scripts/casper-functions
log_begin_msg "$DESCRIPTION"
# ... your code ...
log_end_msg
```

### Debugging Tips

1. **Add verbose logging** - Use `echo "[PREFIX] message" >/dev/console` to see output during boot
2. **Check serial console** - VM serial logs capture boot messages: `/var/log/libvirt/qemu/*-serial.log`
3. **List mounts** - Run `mount | grep -E "(cdrom|vda|loop)"` to see what's mounted where
4. **Debug mode** - Boot without `purple.install=1` to get a normal Ubuntu live shell

### Common Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| Hook doesn't run | Not in ORDER file | Add to ORDER file |
| "Payload not found" (in hook) | Used `/cdrom` instead of `/root/cdrom` | Use `/root/cdrom` in initramfs |
| "Payload not found" (at runtime) | Marker has `/root/cdrom/...` path | Strip `/root` prefix before writing marker |
| Service never starts | Wrote unit to `/root/run/systemd/system/` | Use `/root/etc/systemd/system/` |
| ExecStart script not found | Wrote script to `/root/run/...` | Write to `/run/...` (no /root prefix) |
| Service fails with 203/EXEC | Shebang or permissions issue | Use `ExecStart=/bin/bash /path/to/script` |
| Black screen after boot | Getty masked but service failed | Check `systemctl status purple-confirm.service` |

---

## Glossary

| Term | Meaning |
|------|---------|
| **Golden image** | Pre-built Ubuntu system, created with debootstrap, compressed as purple-os.img.zst |
| **Initramfs** | Early boot filesystem loaded by kernel, contains scripts that run before real root |
| **Casper** | Ubuntu's scripts for live boot, mounts squashfs—we let it run normally, Gate 2 runs in userspace |
| **Hook script** | Our script in `/scripts/casper-bottom/` that checks for arming and writes runtime artifacts to `/run/` |

---

## Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    THE KEY INSIGHT                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   We don't modify Ubuntu's live system (squashfs).              │
│   We only modify GRUB config and initramfs.                     │
│                                                                 │
│   Gate 1 (casper-bottom hook):                                  │
│     - Finds payload at /root/cdrom/purple/                      │
│     - Writes scripts to /run/purple/ (NOT /root/run!)           │
│     - Writes systemd unit to /root/etc/systemd/system/          │
│     - Translates paths: /root/cdrom -> /cdrom for marker        │
│                                                                 │
│   Gate 2 (systemd service):                                     │
│     - Shows confirmation screen                                 │
│     - User presses ENTER = install proceeds                     │
│     - User presses ESC or timeout = safe reboot                 │
│                                                                 │
│   The squashfs is never modified.                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
