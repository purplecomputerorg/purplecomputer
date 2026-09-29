# Corruption Testing (Backup-Image Fallback)

How to test that a decayed Purple Key self-heals during install, end to end. Cheap USB flash loses data in storage and transit, and some laptops cannot read a stick reliably. `install.sh` reads the compressed image into RAM in 4MiB ranges, each checked against the manifest, before it wipes the disk. A bad range comes from the backup copy on with-backup ISOs, and every range gets a few retries for a stick that drops out for a moment. Only when a range is bad in every copy do parents see the replace-this-Key screen, and then the computer has not been touched.

## Quick Start

```bash
PURPLE_WITH_BACKUP_ISO=1 just build   # need a with-backup ISO (shipped-USB variant)
just corrupt-test-iso                 # corrupt the primary copy (default scenario)
just flash-corrupt                    # flash the newest corrupt-test ISO
```

`just flash-corrupt <scenario>` flashes a specific scenario's ISO; without one it takes the newest corrupt-test ISO whatever its scenario (after `corrupt-test-iso all` that's `merge`).

Then boot the USB (VM or real hardware), open the parent menu, and run Install.

To test every scenario in one pass, plug in four whitelisted drives and:

```bash
just corrupt-test-iso all             # make all four scenario ISOs
just flash-corrupt-all                # flash one scenario per drive, in parallel
```

`flash-corrupt-all` ends with an identification phase: unplug the drives one at a time, and as each disappears it prints which scenario that stick got (and the expected install behavior) so you can label it. To make this work, corrupt-mode flashes skip the power-off eject (a powered-off drive vanishes from the bus, so its unplug would be undetectable); that's safe because writes are synced and read back verified. Corrupt mode also skips the QEMU boot-settle and never records to the orders app. Pass scenario names to flash a subset, e.g. `just flash-corrupt-all merge both` with two drives.

## Scenarios

`just corrupt-test-iso [iso] [primary|backup|both|merge|all]`. Without an ISO path it uses the newest build's with-backup ISO and prints which one it picked. Arguments can come in any order; `all` makes every scenario ISO.

| Scenario | Command | Expected install behavior |
|---|---|---|
| primary (default) | `just corrupt-test-iso` | The damaged range comes from the backup while the image is read into memory (status "Double-checking with a backup copy..."), install completes |
| backup | `just corrupt-test-iso backup` | Install succeeds normally from the primary; proves a bad backup alone is harmless |
| both | `just corrupt-test-iso both` | Both copies corrupted at the same offset: the read into memory fails before the disk is wiped, install stops with the friendly damaged-Purple-Key screen and the old contents intact |
| merge | `just corrupt-test-iso merge` | Both copies corrupted at different offsets: each damaged range comes from the other copy in the same pass, install completes |

## How It Works

`build-scripts/make-corrupt-test-iso.sh` copies the ISO to `<name>.corrupt-test-<scenario>.iso` (the scenario lives in the filename, so a flashed stick is self-describing) and overwrites 64KiB with garbage starting 8MiB into the chosen `/purple/*.img.zst` (past the zstd header, so the install fails in seconds instead of at 96%). The `merge` scenario corrupts the backup copy at 24MiB instead, so the two copies are damaged in different 4MiB ranges. It writes a matching `.sha256` sidecar, so flashing and booting behave completely normally; only zstd's frame checksums catch the damage during install.

The reading itself lives in `build-scripts/install.sh` (`image_ranges` and `read_range`). The manifest (`purple-os.img.zst.manifest`, range size plus per-range sha256s) is written by `01-remaster-iso.sh` on every ISO. With enough free RAM (the image plus 512MB) the ranges fill a tmpfs at `/run/purple-stage` before `wipefs`; without it, the same checked ranges stream into the write and a failure lands after the wipe, as it always did. The "try everything" boot menu entry copies the image into that tmpfs at boot, and `install.sh` then reads the stick only for ranges that copy got wrong. Marker lines on stderr drive the UI: `[PURPLE-RETRY]` when a range comes from the backup, `[PURPLE-CORRUPT-KEY]` for the unrecoverable-Key error, with friendly wording in `purple_tui/parent_menu.py`. The range logic is unit tested in `tests/test_install_image_ranges.py`.

## Notes

- All four scenarios verified end to end on 2026-07-23 with the earlier whole-copy fallback; the read-into-memory path (2026-09-29) needs the same pass on hardware.
- Corrupt-test ISOs are never auto-picked by normal ISO discovery (`just flash`, `just build` flows). Only `just flash-corrupt` or an explicit path flashes one.
- `just flash-corrupt` warns if the newest corrupt-test ISO came from an older build than your newest build; re-run `just corrupt-test-iso` after rebuilding.
- The `backup` and `both` scenarios need a with-backup ISO; a plain ISO has no backup copy to corrupt, and the script errors accordingly.
- Corruption is a plain byte overwrite of `X` characters, deterministic and repeatable; delete the `.corrupt-test-*.iso` files (and their `.sha256`/`.version` sidecars) when done to reclaim disk. `all` makes four full-size copies (`cp --reflink=auto` makes them nearly free on a reflink filesystem, roughly 24GB otherwise).
