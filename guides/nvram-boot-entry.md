# Hybrid Boot (UEFI + BIOS)

Purple's installer sets up **both** UEFI and BIOS boot paths so a freshly installed Purple boots on everything from a 2011 Dell Latitude to a 2024 ThinkPad to a 2015 MacBook Pro without the user touching F12 or BIOS settings.

## Why both

Firmware behavior at cold boot is wildly inconsistent:

- **Modern UEFI PCs** (Lenovo/HP/Surface/newer Dell, 2015+) auto-scan the ESP for `/EFI/BOOT/BOOTX64.EFI` and boot it. UEFI path is sufficient.
- **Strict older UEFI PCs** (Dell Latitude E6420-era, 2011-2013) only honor NVRAM `BootOrder`. Without a NVRAM entry they cold-boot to a blinking cursor. UEFI path alone is insufficient.
- **Legacy/CSM-mode firmwares** (those older Dells often default to Legacy-first; some budget laptops are Legacy-only) never enter UEFI mode on internal HDD attempts. They read MBR and jump to BIOS boot code. **Only the BIOS path works here.**
- **Pre-T2 Intel Macs** (2006-2017) ignore foreign NVRAM entries but fall through to `/EFI/BOOT/BOOTX64.EFI` when no macOS is blessed. UEFI fallback path works.

Covering all of these requires both a UEFI bootloader on the ESP and a BIOS bootloader in MBR + `bios_grub` partition.

## Partition layout

```
p1  ESP        fat32        1MiB        - 513MiB         (from golden image)
p2  root       ext4         513MiB      - (end - 2MiB)   (from golden image, grown by resize2fs)
p3  bios_grub  (unformatted) last 2MiB                   (empty on disk; filled by grub-install)
```

`bios_grub` is placed **last** deliberately:

- Keeps p1/p2 partition numbers identical to the pre-hybrid layout — no cascade of variable renames in `install.sh`.
- Requires zero changes to the golden image's byte layout. The golden image ends well before the last 2MiB of any target disk, so `bios_grub` sits in the post-image zero region, ready for `grub-install` to write `core.img` into it.
- GRUB's BIOS boot doesn't care where on disk the `bios_grub` partition sits; the LBA gets baked into `boot.img` at install time.
- Slight unconventionality (most distros put `bios_grub` first) in exchange for much smaller diff surface.

## Install.sh boot layers

| Layer | Path | Purpose |
|-------|------|---------|
| 1 | `/EFI/BOOT/BOOTX64.EFI` + `grubx64.efi` | UEFI spec removable-media fallback (from golden image) |
| 2 | `/EFI/purple/shimx64.efi` + grub + mmx64 | Vendor path targeted by the NVRAM entry |
| 3 | `/EFI/Microsoft/Boot/bootmgfw.efi` + grub | Windows-path hijack (HP, Surface, some older Dells) |
| 4 | NVRAM `Boot####` entry "PurpleOS" → `\EFI\purple\shimx64.efi`, prepended to `BootOrder` | Primary UEFI boot for compliant firmware |
| 5 | `/boot/grub/grub.cfg` UUID rewrite (both EFI and root copies) | Deterministic boot on multi-disk systems |
| 6 | MBR `boot.img` + `core.img` in `bios_grub` partition | Legacy BIOS / CSM path |

Layer 4 requires `efibootmgr` in the live environment — added to the golden image package list.
Layer 6 requires `grub-pc-bin` (provides `grub-install --target=i386-pc` and `/usr/lib/grub/i386-pc/*.mod`) — also added to the golden image.

## The bug this fixed

Two silent gaps in the pre-hybrid installer:

1. **`efibootmgr` was not in the golden image.** `install.sh` Layer 4 was gated on `command -v efibootmgr` and silently skipped on every install, so no machine ever got a `PurpleOS` NVRAM entry. Machines that "worked" did so via fallback paths or inherited stale `ubuntu`/`Windows Boot Manager` entries chainloading our shim.

2. **No BIOS boot path.** `install.sh` only set up UEFI. Legacy/CSM firmwares (and legacy-first mixed-mode firmwares, common on 2011-2013 Dells) attempted MBR boot on the "Internal HDD" entry, found nothing bootable on the GPT disk, and hung at a blinking cursor. User had to hit F12 → pick "UEFI Boot" manually every cold boot.

The fix added `efibootmgr` + `grub-pc-bin` to the golden image, added a 2MiB `bios_grub` partition at the end of the disk, and a `grub-install --target=i386-pc` call as Layer 6.

## Regression analysis

**Modern UEFI PCs:** firmware uses the NVRAM entry (or `/EFI/BOOT/` fallback) first, ignoring MBR BIOS code. Same shim/GRUB/kernel as before. No behavior change.

**Pre-T2 Intel Macs (first-class Purple target):** Apple EFI ignores foreign NVRAM entries and ignores MBR BIOS code. Boots via `/EFI/BOOT/BOOTX64.EFI` fallback, same as today. The new NVRAM entry and MBR code are inert. Zero regression.

**T2 Macs (2018-2020):** not currently supported; see `t2-mac-support.md`. Change is orthogonal.

**Legacy/CSM-mode PCs (E6420 etc.):** previously broken at cold boot, now boot via MBR → `core.img` → `grub.cfg` → kernel. ✅ The core fix.

**Windows dual-boot:** not a Purple scenario (we own the disk), but the `bootmgfw.efi` preservation logic (`install.sh:443-447`) is unchanged. User can reinstall Windows later from a USB installer — that path uses firmware's built-in USB boot menu, which doesn't need our NVRAM entries.

**Failure modes:** every new step is wrapped `2>/dev/null || true` or logs to a temp file and warns. If `efibootmgr`, `grub-install`, or NVRAM writes fail, install completes and the remaining layers still boot the machine.

## Historical "efibootmgr bricks Macs" concern

The folklore comes from a 2012-2016 kernel bug where *large* EFI variable writes (crash dump variables, `dump-type0-*`) filled Apple's small NVRAM and bricked the firmware. That is not what `efibootmgr` does. Creating a `Boot####` entry is a few hundred bytes and has been routine on Macs for a decade. Current kernels also refuse writes when NVRAM is >50% full as a safety net.

## NVRAM-full machines (E6420 edge case)

One known failure mode not fixed by the installer: a machine whose NVRAM is already so full that shim's own `MokListRT` variable write fails with "Out of Resources" during install. On such machines, our `efibootmgr -c` call also fails silently — no `PurpleOS` entry gets created. Fix is BIOS-side: reset NVRAM / clear settings in firmware setup, then reinstall. The BIOS-path Layer 6 still works on these machines regardless.

## Verification after an install

```
sudo efibootmgr -v                    # UEFI path: expect PurpleOS first in BootOrder
sudo parted /dev/$TARGET print        # expect 3 partitions, last one with bios_grub flag
sudo dd if=/dev/$TARGET bs=446 count=1 2>/dev/null | xxd | head -2   # MBR should contain GRUB boot.img (non-zero)
```

## Future work

- **Auto-boot Purple on Mac dual-boot installs** (macOS kept alongside Purple): needs `bless --setBoot` (macOS-only) or rEFInd. `efibootmgr` doesn't solve this because Apple EFI ignores standard NVRAM entries. Out of scope — wiped-internal Mac installs already cold-boot Purple via ESP fallback.
- **Conservative NVRAM cleanup** (delete stale `Boot####` entries pointing to removed disks, delete `dump-type0-*` efivars): considered and deferred. Low payoff for the E6420 (its issue is legacy-mode firmware, not NVRAM clutter) and adds brick risk.
