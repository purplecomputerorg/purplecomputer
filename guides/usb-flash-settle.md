# USB Boot-Settle After Flashing

Why `flash-all.sh` and `flash-to-usb.sh` boot each freshly flashed drive once in QEMU before it ships.

## Slow First Boot After Flashing (drive-side, confirmed 2026-07-08)

Freshly flashed drives take much longer on their first boot than on every boot after. Experiment: a 2011 Mac took 3.5 minutes to first-boot a fresh flash, reproduced twice across reflashes (right-side USB port). After a third flash, the same drive first-booted on a 2014 Mac in 1 minute; then, with no reflash, the 2011 Mac booted it in 15 seconds instead of 3.5 minutes.

Conclusion: the penalty is state on the USB drive (controller-level, likely post-write read recalibration or SLC cache folding), not per-machine UEFI caching. One boot on any machine clears it for all machines.

Reconfirmed 2026-08-13 on a MacBook5,2 (USB 2.0): first boot of an unsettled fresh flash took roughly 10 minutes (untimed; this also included casper's first-boot persistence setup), second boot of the same stick took 37 seconds. Settled drives still showed 60s+ first-boot penalties versus their second boot, which closed the snapshot=on tradeoff gate: see the next section.

The sequential dd "settle" read pass in `flash-all.sh` did NOT clear it; an actual boot does. Fix: `boot_settle_drive` in `flash-lib.sh` boots each drive once in QEMU (raw `/dev/sdX` with `cache=none`, so guest reads hit the flash rather than the host page cache), detects boot completion from host-side `/sys/block` read counters, then keeps the drive powered briefly for background relocation. Used by both `flash-all.sh` (parallel) and standalone `flash-to-usb.sh`; skip with `--no-settle`, tune with `BOOT_SETTLE_*` env vars.

## Settle Boot Writes Again (2026-08-13, reverting 2026-07-22's snapshot=on)

From 2026-07-22 to 2026-08-13 the settle boot ran with `snapshot=on`, sending guest writes to a throwaway qcow2 overlay so shipped bytes stayed byte-exact with the verified ISO. That deliberately deferred casper's one-time persistence setup (relocating the backup GPT to the disk's true end, creating and mkfs'ing the ~48GB "writable" partition) to the customer's first boot, with a gate: revisit if first boot regresses badly. It did: settled drives still paid 60s+ on their first real boot versus their second, which is exactly the deferred persistence setup. So the settle boot writes for real again and casper's setup happens in the factory.

The two problems `snapshot=on` was introduced for are both covered by mechanisms that landed independently:

- **Reflashed sticks accumulating conflicting GPT headers:** `flash-to-usb.sh` zeroes stale history before every dd: the last MiB (relocated backup GPT) and 64MiB past the ISO extent (old "writable" superblock, which casper could otherwise reuse instead of mkfs'ing fresh, resurrecting a prior owner's data). The writable partition a shipped stick now carries is a factory-fresh mkfs, so there is no owner data to resurrect.
- **Shipped bytes differing from verified bytes:** `recheck_after_settle` re-hashes the drive against the ISO after the settle boot, so the bytes that ship are verified after all writes. It skips the first MiB (`GPT_SKIP_BYTES`): adding the writable partition rewrites the primary GPT there, so that region legitimately differs from the ISO. Everything from 1MiB to the end of the ISO's last partition (`iso_partitioned_bytes`) must still match. The ISO file's tail past that holds only its backup GPT and xorriso padding, and casper starts the writable partition on the next 2MiB boundary after the last partition, which lands inside that tail on roughly one build in five (the 2026-08-28 build: partition 2 ended 237 sectors short of a boundary, so mkfs's superblock sat 256KiB inside the file and every stick read as "decaying"). Comparing the whole file would flag those builds; comparing through the last partition covers every byte that boots or installs.

Side effect worth knowing: settle boots were anecdotally slower under `snapshot=on` (every guest write paid qcow2 allocation into an O_DIRECT overlay on `/var/tmp`); with real writes that overhead is gone, at the cost of the mkfs writes going to the stick during settle.

## Timed-Out Settles Retry Themselves (2026-07-28)

An incomplete settle is usually a slow drive that was still booting when the window closed, not a broken one: in a 10-drive batch, one stick read 1030MB (5x the 200MB bar) and never got its 30s of quiet inside 600s, while its own flash verified clean. `boot_settle_with_retry` therefore gives a failed drive a second attempt with a doubled window before reporting anything, so a batch finishes unattended. `BOOT_SETTLE_ATTEMPTS=1` restores single-shot; raising it doubles again per attempt.

When a drive still fails, the report names it physically: `drive_location` prints product, serial and USB port path (e.g. `USB port 4-1.4`, meaning bus 4, root port 1, hub port 4), read from sysfs because the flash tools pause udev's exec queue and an ejected drive's `/dev` node stops resolving. The path under the hub is stable per physical socket, so hub sockets can be labeled once with `just label-ports`; labeled reports read `USB port 4-1.4 (top row 3)`. Labels are keyed by that path without the bus number (`1.4`), so they survive the hub's uplink moving to another port on the server and cover both the USB 2.0 and 3.0 sides of the hub, which enumerate as separate buses. The settle log also keeps a per-minute read trail, which separates "slow but progressing" from "stalled early"; the latter is worth a `just check-drive`.

To re-settle one drive by hand, `flash-to-usb.sh --settle-only --device /dev/sdX` skips flashing entirely. Unplug and replug first: the flash powers the drive off, and a settle on a media-less node fails immediately.

## Re-Read After Settling, Before Ejecting (2026-07-29)

A drive can pass its post-write readback and still be wrong minutes later. One stick verified clean, then read back with a single 32KB region of `0x55` filler; a targeted rewrite of that region fixed it permanently, so it was a lost write rather than dying flash. Both `flash-all.sh` and `flash-to-usb.sh` now re-hash the ISO extent off each drive after the settle boot (`recheck_after_settle`) and refuse to ship a mismatch. `--no-reverify` skips it on `flash-all`. Cost: a full ISO re-read per drive, four at a time.

The ordering is load-bearing, not stylistic. The re-read must come after boot-settling and before `eject_drive`. Ejecting powers the drive off, which leaves a media-less node in `/dev` whose reads return garbage that is indistinguishable from decaying flash. A "drift" alarm during development was exactly that: reading a node the flash script had already powered off, on a drive that was fine. If this call ever moves, it moves before the eject or not at all.

## Per-Drive Pipelines (2026-08-14)

`flash-all.sh` used to run in stages with barriers: all flashes, then a retry round, then all settles, then all re-verifies, then ejects. One sick drive delayed every healthy one at each barrier; its retry reflash alone held the whole batch's settling. Now each drive runs its own background job through the entire chain (flash with power-cycle retries, settle, re-verify, eject), so a slow or failing drive only slows itself.

The constraints the barriers used to enforce moved into shared primitives: settle concurrency (RAM-bounded, `boot_settle_max_jobs`) and the four-at-a-time re-verify are `flock` slot directories (`slot_acquire` in `flash-lib.sh`), and the udev exec queue stays paused until the last drive finishes writing, with each job waiting on a marker file only before its eject, the one stage that needs `udevadm settle`. Jobs report back through result files; the parent folds them into `ST_OK`/`ST_TRIES` for the batch summary.

Finding a failed stick physically: the failure report names its socket by the label from `just label-ports`, and offers to blink the socket's LED by toggling port power (`just blink /dev/sdX` standalone). Blinking is a repeated power cycle, so it's only ever offered for failed drives.

## Unattended Retries and Why Nothing Matches Device Letters (2026-07-29)

A ten-drive batch should not need a human between the first drive stalling and the last one finishing, so both failure modes retry themselves: a flash that fails verification is re-run after power-cycling the drive's hub port (`--retries`, default 1), and a settle that times out gets a doubled window (see above). Most failures are recoverable: across a 212-flash manifest, 3 of 102 distinct sticks ever failed, and only one was genuinely dying (now in `.flash-denylist.conf`). Retry first, deny second.

The port power cycle writes to the hub port's sysfs `disable` attribute, which is the only way to bring back a drive that failed and left the bus without hands on the hub. `usb_port_control` derives that path, and `flash-all.sh` captures every drive's port up front, while all of them are still enumerated: a failed or ejected drive has no `/sys/block` entry left to derive one from.

Everything after a flash attempt is keyed by index, never by device node. A power-cycled drive re-enumerates under whatever letter is free, which may be the one another stick just gave up, so a node lookup can answer for the wrong drive: re-flashing the old letter could write to an unrelated disk, and skipping a "failed" letter could quietly drop a healthy drive from settling and ejecting. `ST_OK[i]` is the single source of truth, `ST_SER[i]` identifies the physical stick, and `dev_for_serial` maps a serial back to whatever node it currently holds.
