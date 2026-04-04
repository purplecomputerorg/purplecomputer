# Secure Boot

How Purple Computer boots on Secure Boot-enabled machines, and how we stay ahead of SBAT revocations.

## Boot chain

```
UEFI firmware (trusts Microsoft's key)
  -> shimx64.efi  (signed by Microsoft via Canonical)
    -> grubx64.efi  (signed by Canonical)
      -> vmlinuz  (signed by Canonical)
```

All three binaries come from Ubuntu's official `shim-signed` and `grub-efi-amd64-signed` packages. We don't sign anything ourselves.

`mmx64.efi` (MOK Manager) is also placed alongside shim in every EFI directory. Shim loads it by relative path if a user needs to enroll custom keys. We don't use MOK, but shipping it prevents shim from erroring on machines that trigger the enrollment flow.

## Where the binaries live

| Context | EFI paths | Source |
|---------|-----------|--------|
| Live USB (ISO) | Fresh EFI image built at remaster time | `$BUILD_DIR/signed-efi/` |
| Installed system | `/EFI/BOOT/`, `/EFI/purple/`, `/EFI/Microsoft/Boot/`, `/EFI/ubuntu/` | Golden image EFI partition |

Both pull from the same `apt-get download shim-signed grub-efi-amd64-signed` run during the golden image build. The binaries are saved to `$BUILD_DIR/signed-efi/` so the remaster script can reuse them without downloading again.

## SBAT revocation

SBAT (Secure Boot Advanced Targeting) lets Microsoft revoke specific versions of shim/GRUB that have known vulnerabilities. The revocation list (DBX) is stored in UEFI NVRAM on the motherboard, not fetched live.

**How machines get revocations:**
- Windows Update (most common path)
- BIOS/firmware updates from the manufacturer
- Factory-installed on new hardware

**What a revocation looks like to the user:** "Security Violation" screen at boot, or Rufus warning "Revoked UEFI bootloader detected" when flashing.

**Historical frequency:** roughly every 1-2 years (2022 BlackLotus response, August 2024 shim CVE batch). Rollout is gradual over months.

## How we handle it

The ISO's EFI partition is built fresh at remaster time (`01-remaster-iso.sh` step 8) rather than reusing the base Ubuntu ISO's EFI image. This means:

1. Every build gets whatever shim/GRUB versions are current in Ubuntu's repos
2. No dependency on the base ISO's age (we use Ubuntu 24.04.1 but get latest signed binaries)
3. No size constraints from the original EFI partition (we size the image to fit)

**If a shipped USB gets revoked:** rebuild and reflash. There is no way to avoid this short of signing our own shim with Microsoft (expensive, long process, not worth it at our scale).

## Installed system

The installed system's EFI partition uses the same signed binaries from the golden image build. These are copied to four paths for hardware compatibility (see CLAUDE.md "UEFI Boot" section). Since the installed system has Ubuntu's apt repos, a future `apt upgrade` of `shim-signed` would also update the binaries, though Purple Computer doesn't run unattended updates.

## Troubleshooting

**"Security Violation" on a machine that previously worked:** The machine received a firmware or Windows Update that revoked the shim version on the USB. Rebuild the ISO with current packages and reflash.

**Boots to GRUB shell instead of Purple Computer:** The signed GRUB can't find its config. It looks for `/EFI/ubuntu/grub.cfg` on the EFI partition (compiled-in prefix), then falls back to searching for `/.disk/info` on other partitions. Both paths should be set up by the remaster script. If this happens, the EFI image build likely failed silently.

**MOK enrollment screen appears:** Shim is asking to enroll a key. This shouldn't happen with our chain (all binaries are already trusted), but if it does, the user can skip/cancel and boot should continue. `mmx64.efi` must be alongside shim for this screen to render.
