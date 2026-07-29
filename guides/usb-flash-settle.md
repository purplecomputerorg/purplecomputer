# USB Boot-Settle After Flashing

Why `flash-all.sh` and `flash-to-usb.sh` boot each freshly flashed drive once in QEMU before it ships.

## Slow First Boot After Flashing (drive-side, confirmed 2026-07-08)

Freshly flashed drives take much longer on their first boot than on every boot after. Experiment: a 2011 Mac took 3.5 minutes to first-boot a fresh flash, reproduced twice across reflashes (right-side USB port). After a third flash, the same drive first-booted on a 2014 Mac in 1 minute; then, with no reflash, the 2011 Mac booted it in 15 seconds instead of 3.5 minutes.

Conclusion: the penalty is state on the USB drive (controller-level, likely post-write read recalibration or SLC cache folding), not per-machine UEFI caching. One boot on any machine clears it for all machines.

The sequential dd "settle" read pass in `flash-all.sh` did NOT clear it; an actual boot does. Fix: `boot_settle_drive` in `flash-lib.sh` boots each drive once in QEMU (raw `/dev/sdX` with `cache=none`, so guest reads hit the flash rather than the host page cache), detects boot completion from host-side `/sys/block` read counters, then keeps the drive powered briefly for background relocation. Used by both `flash-all.sh` (parallel) and standalone `flash-to-usb.sh`; skip with `--no-settle`, tune with `BOOT_SETTLE_*` env vars.

## Settle Boot Must Not Write (2026-07-22)

The settle boot runs with `snapshot=on`: guest writes land in a throwaway qcow2 overlay (forced to `TMPDIR=/var/tmp`, since sudo strips TMPDIR and QEMU would otherwise fill a tmpfs `/tmp` during parallel settles), never on the stick. Before this, the settle boot mutated every drive after checksum verification (casper relocated the backup GPT to the disk's true end and added a ~48GB "writable" persistence partition), so shipped bytes were not the verified bytes, and reflashed sticks accumulated conflicting GPT headers. `flash-to-usb.sh` now also zeroes stale history before every dd: the last MiB (relocated backup GPT) and 64MiB past the ISO extent (old "writable" superblock, which casper could otherwise reuse instead of mkfs'ing fresh, resurrecting a prior owner's data).

Known tradeoff: the old settle boot's real writes were pre-doing casper's one-time persistence setup (GPT relocation plus mkfs of the writable partition), so with `snapshot=on` that write work happens on the customer's first boot instead. Accepted deliberately for byte-exact shipping; the controller read recalibration (the penalty this feature exists for) is read-driven and survives. Gate: time one first boot on a freshly flashed drive; if it regresses badly, revisit (pre-creating the persistence partition at flash time would be the fallback).

## Timed-Out Settles Retry Themselves (2026-07-28)

An incomplete settle is usually a slow drive that was still booting when the window closed, not a broken one: in a 10-drive batch, one stick read 1030MB (5x the 200MB bar) and never got its 30s of quiet inside 600s, while its own flash verified clean. `boot_settle_with_retry` therefore gives a failed drive a second attempt with a doubled window before reporting anything, so a batch finishes unattended. `BOOT_SETTLE_ATTEMPTS=1` restores single-shot; raising it doubles again per attempt.

When a drive still fails, the report names it physically: `drive_location` prints product, serial and USB port path (e.g. `USB port 4-1.4`, meaning bus 4, root port 1, hub port 4), read from sysfs because the flash tools pause udev's exec queue and an ejected drive's `/dev` node stops resolving. The port string is stable per physical socket, so hub ports can be labeled once. The settle log also keeps a per-minute read trail, which separates "slow but progressing" from "stalled early"; the latter is worth a `just check-drive`.

To re-settle one drive by hand, `flash-to-usb.sh --settle-only --device /dev/sdX` skips flashing entirely. Unplug and replug first: the flash powers the drive off, and a settle on a media-less node fails immediately.
