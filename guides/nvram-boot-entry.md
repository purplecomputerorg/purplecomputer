# NVRAM Boot Entry (efibootmgr)

## Why this exists

Purple's installer writes shim+GRUB to three fallback paths on the ESP:

1. `/EFI/BOOT/BOOTX64.EFI` — UEFI spec removable-media fallback
2. `/EFI/Microsoft/Boot/bootmgfw.efi` — Windows path hijack (HP, Surface, some Dells)
3. `/EFI/purple/shimx64.efi` — vendor path, target of the NVRAM entry

Plus a fourth "layer": a `Boot####` NVRAM entry named `PurpleOS` pointing at `\EFI\purple\shimx64.efi`, with `BootOrder` updated to put it first.

Fallback paths alone are *not* sufficient on all hardware. Older strict-UEFI firmwares (notably Dell Latitude E6420-era, 2011-2013) only boot what's in NVRAM `BootOrder` — they do not scan the ESP for fallback EFI files on fixed disks. Without a NVRAM entry, they cold-boot to a blinking cursor. F12 → "UEFI Boot" still works because that menu option manually invokes the ESP fallback path.

## The bug we fixed

`install.sh` has always had Layer 4 logic that runs `efibootmgr -c` and `efibootmgr -o`. But `efibootmgr` was never added to the golden image package list. The code is gated on `command -v efibootmgr`, so it silently skipped on every install. No machine ever got a NVRAM entry.

Machines that "worked" did so via fallback paths — modern Lenovo/HP/Surface scan `/EFI/BOOT/BOOTX64.EFI`, HPs/Surfaces hit the Microsoft path, machines with prior OS installs inherited stale `ubuntu`/`Windows Boot Manager` entries that happened to chainload our shim.

Fix: add `efibootmgr` to `build-scripts/00-build-golden-image.sh` package list. Layer 4 now runs for real.

## Why this doesn't regress existing targets

**Modern PCs (Lenovo, HP, Surface, newer Dell):** adding a NVRAM entry doesn't remove the fallback files. Firmware uses the NVRAM entry instead of the fallback — same shim, same chain. No behavior change.

**Pre-T2 Intel Macs (2006-2017, a first-class Purple target):** Apple EFI ignores foreign `Boot####` entries entirely. On a Mac where macOS has been wiped, firmware finds no blessed system and falls through to `/EFI/BOOT/BOOTX64.EFI` — same as today. The entry we create is inert on Macs. Zero regression.

**T2 Macs (2018-2020):** not currently supported; see `t2-mac-support.md`. efibootmgr change is orthogonal.

**Windows dual-boot:** `install.sh:443-447` already preserves real `bootmgfw.efi`; BootOrder logic prepends Purple but keeps existing entries. Windows stays reachable.

**Failure modes:** every `efibootmgr` call is wrapped `2>/dev/null || true`. If NVRAM is full, efivarfs isn't mounted, or firmware rejects the write, install completes and fallback paths still boot the machine.

## Historical "efibootmgr bricks Macs" concern

The folklore comes from a 2012-2016 kernel bug where *large* EFI variable writes (crash dump variables, `dump-type0-*`) filled Apple's small NVRAM and bricked the firmware. That is not what efibootmgr does. Creating a `Boot####` entry is a few hundred bytes and has been routine on Macs for a decade. Current kernels also refuse writes when NVRAM is >50% full as a safety net.

## Verification after an install

```
sudo efibootmgr -v
```

Expect to see `BootOrder: XXXX,...` with `XXXX*` labeled `PurpleOS` pointing at `HD(...)/File(\EFI\purple\shimx64.efi)`. On Macs, the entry will be created but firmware won't use it — that's expected.

## Future work

- **Auto-boot Purple on Mac dual-boot installs:** would need `bless --setBoot` (macOS-only) or rEFInd. efibootmgr doesn't solve this because Apple EFI ignores standard NVRAM entries. Out of scope for now — wiped-internal Mac installs already cold-boot Purple via the ESP fallback path.
- **Older Dells with Legacy Option ROMs enabled:** if a machine is stuck in mixed/legacy mode, even a correct NVRAM entry can lose to PXE/legacy HDD attempts. BIOS-side fix, not installer-side.
