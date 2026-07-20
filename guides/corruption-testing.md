# Corruption Testing (Backup-Image Fallback)

How to test that a decayed Purple Key self-heals during install, end to end. Cheap USB flash loses data in storage and transit; with-backup ISOs carry a second golden image copy, and `install.sh` retries from it when the primary fails its zstd integrity check mid-write. If both whole copies fail, a last-resort pass merges the good 4MiB ranges of each (flash decay scatters bad pages independently, so the union of two damaged copies is usually complete). Only when the same range is bad in both copies do parents see the replace-this-Key screen.

## Quick Start

```bash
PURPLE_WITH_BACKUP_ISO=1 just build   # need a with-backup ISO (shipped-USB variant)
just corrupt-test-iso                 # corrupt the primary copy (default scenario)
just flash-corrupt                    # flash the corrupt-test ISO
```

Then boot the USB (VM or real hardware), open the parent menu, and run Install.

## Scenarios

`just corrupt-test-iso [iso] [primary|backup|both|merge]`. Without an ISO path it uses the newest build's with-backup ISO and prints which one it picked. Arguments can come in any order.

| Scenario | Command | Expected install behavior |
|---|---|---|
| primary (default) | `just corrupt-test-iso` | Write fails within seconds, logs "First copy was damaged, writing from the backup copy...", install completes from the backup |
| backup | `just corrupt-test-iso backup` | Install succeeds normally from the primary; proves a bad backup alone is harmless |
| both | `just corrupt-test-iso both` | Both copies corrupted at the same offset: whole-copy attempts and the merge all fail, install aborts with the friendly damaged-Purple-Key screen |
| merge | `just corrupt-test-iso merge` | Both copies corrupted at different offsets: whole-copy attempts fail, logs "Both copies are damaged, combining the good parts of each...", install completes from the merged ranges |

## How It Works

`build-scripts/make-corrupt-test-iso.sh` copies the ISO to `<name>.corrupt-test-<scenario>.iso` (the scenario lives in the filename, so a flashed stick is self-describing) and overwrites 64KiB with garbage starting 8MiB into the chosen `/purple/*.img.zst` (past the zstd header, so the install fails in seconds instead of at 96%). The `merge` scenario corrupts the backup copy at 24MiB instead, so the two copies are damaged in different 4MiB ranges. It writes a matching `.sha256` sidecar, so flashing and booting behave completely normally; only zstd's frame checksums catch the damage during install.

The fallback itself lives in `build-scripts/install.sh` (search `BACKUP_IMAGE`): zstd verifies frame checksums while streaming to dd, a failed pipeline with a healthy dd means a bad copy, and the source list retries with `purple-os-backup.img.zst`. If both whole copies fail, `merge_ranges` streams each range from whichever copy matches its hash in `purple-os.img.zst.manifest` (range size plus per-range sha256s, written at build time by `01-remaster-iso.sh`, with-backup ISOs only). The merge reuses the same write pipeline, so the existing post-write disk verification backstops it; a range bad in both copies truncates the stream, zstd fails, and the install aborts exactly as before. Marker lines on stderr drive the UI: `[PURPLE-RETRY]` for the backup fallback, `[PURPLE-MERGING]` for the merge, `[PURPLE-CORRUPT-KEY]` for the unrecoverable-Key error, with friendly wording in `purple_tui/parent_menu.py`.

## Notes

- Corrupt-test ISOs are never auto-picked by normal ISO discovery (`just flash`, `just build` flows). Only `just flash-corrupt` or an explicit path flashes one.
- `just flash-corrupt` warns if the newest corrupt-test ISO came from an older build than your newest build; re-run `just corrupt-test-iso` after rebuilding.
- The `backup` and `both` scenarios need a with-backup ISO; a plain ISO has no backup copy to corrupt, and the script errors accordingly.
- Corruption is a plain byte overwrite of `X` characters, deterministic and repeatable; delete the `.corrupt-test-*.iso` files (and their `.sha256`/`.version` sidecars) when done to reclaim disk.
