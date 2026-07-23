# USB Boot-Settle After Flashing

Why `flash-all.sh` and `flash-to-usb.sh` boot each freshly flashed drive once in QEMU before it ships.

## Slow First Boot After Flashing (drive-side, confirmed 2026-07-08)

Freshly flashed drives take much longer on their first boot than on every boot after. Experiment: a 2011 Mac took 3.5 minutes to first-boot a fresh flash, reproduced twice across reflashes (right-side USB port). After a third flash, the same drive first-booted on a 2014 Mac in 1 minute; then, with no reflash, the 2011 Mac booted it in 15 seconds instead of 3.5 minutes.

Conclusion: the penalty is state on the USB drive (controller-level, likely post-write read recalibration or SLC cache folding), not per-machine UEFI caching. One boot on any machine clears it for all machines.

The sequential dd "settle" read pass in `flash-all.sh` did NOT clear it; an actual boot does. Fix: `boot_settle_drive` in `flash-lib.sh` boots each drive once in QEMU (raw `/dev/sdX` with `cache=none`, so guest reads hit the flash rather than the host page cache), detects boot completion from host-side `/sys/block` read counters, then keeps the drive powered briefly for background relocation. Used by both `flash-all.sh` (parallel) and standalone `flash-to-usb.sh`; skip with `--no-settle`, tune with `BOOT_SETTLE_*` env vars.

## Settle Boot Must Not Write (2026-07-22)

The settle boot runs with `snapshot=on`: guest writes land in a throwaway qcow2 overlay (forced to `TMPDIR=/var/tmp`, since sudo strips TMPDIR and QEMU would otherwise fill a tmpfs `/tmp` during parallel settles), never on the stick. Before this, the settle boot mutated every drive after checksum verification (casper relocated the backup GPT to the disk's true end and added a ~48GB "writable" persistence partition), so shipped bytes were not the verified bytes, and reflashed sticks accumulated conflicting GPT headers. `flash-to-usb.sh` now also zeroes stale history before every dd: the last MiB (relocated backup GPT) and 64MiB past the ISO extent (old "writable" superblock, which casper could otherwise reuse instead of mkfs'ing fresh, resurrecting a prior owner's data).

Known tradeoff: the old settle boot's real writes were pre-doing casper's one-time persistence setup (GPT relocation plus mkfs of the writable partition), so with `snapshot=on` that write work happens on the customer's first boot instead. Accepted deliberately for byte-exact shipping; the controller read recalibration (the penalty this feature exists for) is read-driven and survives. Gate: time one first boot on a freshly flashed drive; if it regresses badly, revisit (pre-creating the persistence partition at flash time would be the fallback).
