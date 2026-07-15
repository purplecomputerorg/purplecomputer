# USB Boot-Settle After Flashing

Why `flash-all.sh` and `flash-to-usb.sh` boot each freshly flashed drive once in QEMU before it ships.

## Slow First Boot After Flashing (drive-side, confirmed 2026-07-08)

Freshly flashed drives take much longer on their first boot than on every boot after. Experiment: a 2011 Mac took 3.5 minutes to first-boot a fresh flash, reproduced twice across reflashes (right-side USB port). After a third flash, the same drive first-booted on a 2014 Mac in 1 minute; then, with no reflash, the 2011 Mac booted it in 15 seconds instead of 3.5 minutes.

Conclusion: the penalty is state on the USB drive (controller-level, likely post-write read recalibration or SLC cache folding), not per-machine UEFI caching. One boot on any machine clears it for all machines.

The sequential dd "settle" read pass in `flash-all.sh` did NOT clear it; an actual boot does. Fix: `boot_settle_drive` in `flash-lib.sh` boots each drive once in QEMU (raw `/dev/sdX` with `cache=none`, so guest reads hit the flash rather than the host page cache), detects boot completion from host-side `/sys/block` read counters, then keeps the drive powered briefly for background relocation. Used by both `flash-all.sh` (parallel) and standalone `flash-to-usb.sh`; skip with `--no-settle`, tune with `BOOT_SETTLE_*` env vars.
