# Install Partition Detection

How `install.sh` writes the golden image to disk and gets the kernel to see partitions afterwards. Covers the pre-write cleanup, the post-write GPT rebuild (which fixes 4K-sector drives, oversized targets, and is required for `resize2fs`), the partition probing strategy, and why naive approaches fail on some hardware.

---

## The Two Failure Modes

After `dd` writes the golden image to the internal disk, the kernel needs to read a partition table from the device and create device nodes (e.g. `/dev/nvme0n1p1`). Two distinct things can go wrong:

**1. Stale partition references (EBUSY).** On machines that previously had macOS, APFS, LVM, or any filesystem whose signatures cause udev or device-mapper to hold partition references open, `blockdev --rereadpt` fails with EBUSY because `BLKRRPART` is all-or-nothing.

**2. Sector-size mismatch (silent failure).** The golden image's GPT was built with `parted` on a regular file, which uses 512-byte sector addressing. On drives with non-512B logical sectors — notably the Apple NVMe in MacBook Pro 2016/2017 (Touch Bar) models, which uses **4096-byte logical sectors** — the kernel looks for the GPT header at LBA 1 = byte 4096, but the image placed it at byte 512. The kernel can't find a partition table at all. `partprobe` runs without error and returns no partitions. The dd write itself succeeds and the SHA256 verifies, because the bytes are correct; only the GPT *metadata location* is wrong for the drive.

Both failure modes were observed on Touch Bar MacBooks. Mode 1 was hit first (fixed by `wipefs` pre-clean). Mode 2 then surfaced on a different unit and required a different fix.

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

## The Fix: Five Phases

### Phase 1: Pre-write cleanup

Before `dd`, clear old partition state so the kernel has no stale references:

```bash
# Unmount any existing partitions
for part in $(lsblk -ln -o NAME "/dev/$TARGET" | tail -n +2); do
    umount "/dev/$part" 2>/dev/null || true
done

# Wipe old filesystem signatures (APFS, HFS+, ext4)
# This calls BLKRRPART internally, clearing the kernel's partition cache
wipefs -a "/dev/$TARGET"

# Let udev finish processing the wipe
udevadm settle --timeout=5
```

After `wipefs`, the kernel thinks the disk has zero partitions. Nothing to hold open.

**Why no `dmsetup` cleanup:** an earlier version of this script also looped over `dmsetup ls --target linear` to remove leftover APFS/LVM mappings. We dropped it: in the live-USB environment, `libdevmapper` is version-mismatched against the running kernel and every `dmsetup` command silently fails ("Incompatible libdevmapper ... and kernel driver"). Phase 3's GPT rebuild on the real device makes pre-write dm cleanup unnecessary anyway — the partition table is rewritten from scratch, and `wipefs` already removes the on-disk filesystem signatures that would let dm re-attach.

### Phase 2: Write golden image

Standard `zstd -dc | dd` with `conv=fsync`. We `tee` the decompressed stream into `sha256sum` so we can verify the disk read-back without decompressing twice.

zstd verifies frame checksums as it streams, so a corrupt image file fails the pipeline mid-write. With-backup ISOs carry a second copy of the image (`purple-os-backup.img.zst`), and the write retries from it when the primary fails integrity (cheap USB flash can decay after a verified flash; seen in the field on a shipped key). A `dd` failure is classified as an internal-disk problem instead (zstd dying of SIGPIPE downstream of a dead `dd` is not evidence of a bad copy), and is not retried. Test the fallback end to end with `just corrupt-test-iso <iso> [primary|backup|both]`.

### Phase 3: Rebuild the partition table on the real device

The most important phase. Done **unconditionally** on every install (one code path = robust):

```bash
SECTOR_SIZE=$(cat /sys/block/$TARGET/queue/logical_block_size)
log "Disk sector size: logical=${SECTOR_SIZE}B"

parted -s /dev/$TARGET mklabel gpt
parted -s /dev/$TARGET mkpart ESP fat32 1MiB 513MiB
parted -s /dev/$TARGET set 1 esp on
parted -s /dev/$TARGET -- mkpart primary ext4 513MiB -2MiB
parted -s /dev/$TARGET -- mkpart primary -2MiB 100%
parted -s /dev/$TARGET set 3 bios_grub on
sync
```

The third partition is the tiny `bios_grub` region for hybrid UEFI+BIOS boot (see `nvram-boot-entry.md`); root ends 2MiB short of the disk to make room for it. Because `parted` uses byte-based offsets (`MiB`), it computes the correct LBAs for whatever the device's actual logical sector size is. The filesystem data already at byte offset 1MiB (ESP) and 513MiB (root) is left untouched: only the GPT metadata at the start and end of the disk is rewritten.

This single step fixes three things at once:

1. **4K-sector drives** (Apple NVMe in MBP 2016/2017): GPT now points to the right LBAs.
2. **Backup GPT in the wrong place.** The image's backup GPT header sits at the end of the *image*, not the end of the *target drive*. Many UEFI firmwares warn or refuse to boot when the backup header is missing/wrong. Re-running `parted mklabel gpt` writes a fresh backup at the actual end of the disk.
3. **Root partition spans the full drive.** `mkpart ... 513MiB -2MiB` extends the root partition to the end of the real device (minus the 2MiB `bios_grub` tail), not the end of the image. (Phase 5 then grows the filesystem inside.)

On 512-byte-sector drives (the common case), this is effectively a no-op rewrite of the same layout. Cost is ~1 second; eliminates the need for any sector-size special-casing.

**Risk:** if `parted` failed mid-write, the partition table would be invalid but the filesystem data on disk would be intact (we already verified the `dd` byte-for-byte). Phase 5's partprobe would fail and we'd error out the same as today — no silent corruption.

### Phase 4: Partition detection

After Phase 3, probe for the new partition table:

```bash
udevadm settle --timeout=5

for attempt in $(seq 1 20); do
    PARTPROBE_STDERR=$(partprobe "/dev/$TARGET" 2>&1 >/dev/null) || true
    sleep 0.2                          # Let kernel create device nodes
    udevadm trigger --subsystem-match=block
    udevadm settle --timeout=5
    [ -b "/dev/${TARGET}p1" ] && break
    sleep 1
done
```

The 200ms sleep before `udevadm settle` is deliberate: there's a race window after `partprobe` where the kernel has created partitions but hasn't sent uevents to udevd yet. Without the sleep, `udevadm settle` returns immediately (nothing to settle) and the device node doesn't exist yet.

We **capture** `partprobe` stderr (instead of suppressing it) and dump it on the final failure, alongside the logical/physical sector size, `lsblk`, and `/proc/partitions`. Earlier versions of this script silently swallowed `partprobe`'s output, which made the 4K-sector failure mode much harder to diagnose.

### Phase 5: Grow root filesystem to fill the partition

The golden image's ext4 was sized to the image, not the target disk. After Phase 3 the root *partition* spans 513MiB to 2MiB short of end-of-disk, but the filesystem inside it is still at image size (~16GB). `resize2fs` extends the ext4 to fill the partition:

```bash
e2fsck -fy "${PART_PREFIX}2"   # required by resize2fs before offline grow
resize2fs "${PART_PREFIX}2"
```

`-y` is safe because the dd write was just verified byte-for-byte; there's nothing genuine to prompt about. Both commands log warnings rather than `error` out, because a usable (if smaller) install is better than no install.

---

## What Other Installers Do

- **Ubuntu Curtin** (Subiquity/MAAS backend): `partprobe` + `udevadm trigger` + `udevadm settle` in a retry loop. References LP: #1489521 (known EBUSY bug).
- **Calamares**: Uses `partprobe` from parted.
- **CoreOS Installer**: 20 retries at 100ms intervals, then `udevadm settle`.

Our approach matches the Curtin/CoreOS pattern.

---

---

## Sleep Screen Inhibit During Install

The install runs for 10-15 minutes with no keyboard activity, well past Purple's idle-sleep threshold. Without intervention, the sleep screen overlays the install progress modal mid-install.

`PurpleApp` exposes a reason-keyed inhibitor set:

```python
self.app.inhibit_idle("install")    # in InstallProgressScreen.on_mount
self.app.uninhibit_idle("install")  # in InstallProgressScreen.on_unmount
```

`_check_idle_state` returns early when `_idle_inhibitors` is non-empty, but **only after** the lid-close handling block. This is intentional: closing the lid mid-install must still trigger shutdown (kid closes the laptop and walks away). Reason-keyed (a `set[str]`) so multiple long-running operations could compose without stomping on each other in the future.

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
