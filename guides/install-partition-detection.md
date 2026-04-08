# Install Partition Detection

How `install.sh` writes the golden image to disk and detects partitions afterwards. Covers the pre-write cleanup, the partition probing strategy, and why the naive approach fails on some hardware.

---

## The Problem

After `dd` writes the golden image to the internal disk, the kernel needs to re-read the partition table to create device nodes (e.g. `/dev/nvme0n1p1`). The naive approach (`blockdev --rereadpt`) fails with EBUSY on machines that previously had macOS, APFS, LVM, or any filesystem whose signatures cause the kernel or udev to hold partition references open.

This was first observed on a Touch Bar MacBook with NVMe: the `dd` succeeded (SHA256 verified), but partition device nodes never appeared.

---

## Root Cause: Two Kernel Interfaces

| | `BLKRRPART` (blockdev --rereadpt) | `BLKPG` (partprobe from parted) |
|---|---|---|
| How it works | Kernel re-reads entire partition table atomically | Userspace parses the table, then adds/deletes individual partitions |
| Fails when | ANY partition on the disk has `open_count > 0` | Only the SPECIFIC partition being modified is in use |
| Used by | `blockdev --rereadpt`, busybox `partprobe`, `sfdisk -R` | GNU `partprobe` (parted package), `partx`, `kpartx` |

The key difference: `BLKRRPART` is all-or-nothing. If udev has briefly opened `/dev/nvme0n1p2` to probe its filesystem type, `BLKRRPART` fails for the entire disk. `BLKPG` would still succeed at adding `/dev/nvme0n1p1`.

**Important:** BusyBox's `partprobe` only does `BLKRRPART`. The real `partprobe` from the `parted` package uses `BLKPG`. Our image installs the `parted` package to get the real one.

---

## The Fix: Three Phases

### Phase 1: Pre-write cleanup

Before `dd`, clear old partition state so the kernel has no stale references:

```bash
# Unmount any existing partitions
for part in $(lsblk -ln -o NAME "/dev/$TARGET" | tail -n +2); do
    umount "/dev/$part" 2>/dev/null || true
done

# Remove device-mapper entries (APFS, LVM)
dmsetup remove ... || true

# Wipe old filesystem signatures (APFS, HFS+, ext4)
# This calls BLKRRPART internally, clearing the kernel's partition cache
wipefs -a "/dev/$TARGET"

# Let udev finish processing the wipe
udevadm settle --timeout=5
```

After `wipefs`, the kernel thinks the disk has zero partitions. Nothing to hold open.

### Phase 2: Write golden image

Standard `zstd -dc | dd` with `conv=fsync`. No changes here.

### Phase 3: Partition detection

After `dd` + `sync`, probe for the new partition table:

```bash
udevadm settle --timeout=5

for attempt in $(seq 1 20); do
    partprobe "/dev/$TARGET"          # BLKPG: per-partition, resilient
    sleep 0.2                          # Let kernel create device nodes
    udevadm trigger --subsystem-match=block
    udevadm settle --timeout=5
    [ -b "/dev/${TARGET}p1" ] && break
    sleep 1
done
```

The 200ms sleep before `udevadm settle` is deliberate: there's a race window after `partprobe` where the kernel has created partitions but hasn't sent uevents to udevd yet. Without the sleep, `udevadm settle` returns immediately (nothing to settle) and the device node doesn't exist yet.

---

## What Other Installers Do

- **Ubuntu Curtin** (Subiquity/MAAS backend): `partprobe` + `udevadm trigger` + `udevadm settle` in a retry loop. References LP: #1489521 (known EBUSY bug).
- **Calamares**: Uses `partprobe` from parted.
- **CoreOS Installer**: 20 retries at 100ms intervals, then `udevadm settle`.

Our approach matches the Curtin/CoreOS pattern.

---

## Debugging

If partition detection fails, `install.sh` dumps diagnostics:

```
lsblk /dev/nvme0n1        # What the kernel sees
grep nvme0n1 /proc/partitions  # Raw kernel partition table
```

For deeper debugging from a recovery shell:

```bash
# Check if anything holds the disk open
lsof /dev/nvme0n1*

# Check device-mapper state
dmsetup ls

# Manual partition probe with verbose output
partprobe -s /dev/nvme0n1

# Check kernel's view of the partition table
cat /proc/partitions | grep nvme

# Try the lower-level approach
blockdev --rereadpt /dev/nvme0n1
# If this prints "EBUSY", something has an old partition open
```

---

## Related

- [ubuntu-live-installer.md](ubuntu-live-installer.md): Full build and test guide
- [t2-mac-support.md](t2-mac-support.md): Apple T2 hardware notes
- `build-scripts/install.sh`: The installer script
- `build-scripts/00-build-golden-image.sh`: Golden image creation (partition layout)
