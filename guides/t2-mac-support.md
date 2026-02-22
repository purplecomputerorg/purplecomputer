# T2 Mac Support

Apple Macs with the T2 Security Chip (2018-2020 models) are a viable hardware target for Purple Computer. The things that are "broken" on T2 Linux (Wi-Fi firmware, suspend, Touch ID) are all things Purple Computer doesn't need.

This guide covers what works, what's needed, and how to get Purple Computer running on T2 Macs.

---

## T2 Mac Models

All Intel Macs from late 2018 through 2020 have the T2 chip:

**Laptops (primary targets):**
- MacBook Air 13" (2018, 2019, 2020 Retina)
- MacBook Pro 13" (2018, 2019, 2020, various configs)
- MacBook Pro 15" (2018, 2019)
- MacBook Pro 16" (2019)

**Desktops (less relevant but supported):**
- Mac mini (2018)
- iMac 27" (2020)
- iMac Pro
- Mac Pro (2019)

The MacBook Air 2018-2020 is the best Purple Computer candidate: thin, light, Retina display, good speakers, abundant on the used market ($150-250), and often already sitting in parents' drawers.

Apple's full list: https://support.apple.com/en-us/103265

Note: M1/M2/M3 Macs (Apple Silicon) are a completely different situation and are NOT covered here. This guide is only about Intel Macs with the T2 chip.

---

## Why T2 Macs Were Previously Considered Difficult

The T2 chip acts as a gatekeeper for the internal SSD, keyboard, trackpad, audio, and boot process. On a stock T2 Mac:

1. **Secure Boot** only allows macOS and Windows by default
2. **External boot** (USB) is disabled by default
3. **Internal keyboard and trackpad** are routed through the T2 chip, not directly on the USB/SPI bus
4. **Internal SSD** is behind the T2's NVMe controller
5. **Audio** goes through the T2 chip

All of these have been solved by the [t2linux](https://t2linux.org/) community project.

---

## What Works for Purple Computer

Purple Computer's requirements are slim. Here's what matters and what doesn't:

| Purple Need | T2 Mac Status | Details |
|---|---|---|
| x86_64 CPU | All Intel (8th-10th gen) | Well above the 2GB RAM / 16GB storage minimums |
| Display | Retina, works out of the box | 2560x1600 on Airs, well above 1024x768 minimum |
| Audio output | Works | Via apple-bce driver, stable on recent kernels |
| Keyboard via evdev | Works | apple-bce exposes keyboard as standard USB HID in `/dev/input/` |
| Internal SSD | Works | NVMe supported since kernel 5.4 |

**Things Purple doesn't need (so their T2 Linux limitations don't matter):**

| Feature | T2 Linux Status | Purple Relevance |
|---|---|---|
| Wi-Fi | Needs macOS firmware extraction | Purple is offline, Wi-Fi not needed |
| Trackpad | Works but no force touch/palm rejection | Purple disables trackpad entirely |
| Suspend/Sleep | Broken since Sonoma firmware | Purple does lid-close shutdown |
| Touch ID | Not supported | Purple has no login/auth |
| Webcam | Works with driver | Purple doesn't use camera |
| Bluetooth | Occasional glitches | Purple doesn't use Bluetooth |
| Thunderbolt | Mostly works | Purple doesn't use external displays/docks |
| Touch Bar (Pro models) | Shows function keys by default | That's exactly what Purple wants |

---

## The Keyboard and evdev

This is the most important piece. Purple Computer reads keyboard input directly from evdev (`/dev/input/event*`), bypassing the terminal entirely. On T2 Macs:

1. The `apple-bce` (Buffer Copy Engine) kernel driver talks to the T2 chip
2. It creates a VHCI (Virtual USB Host Controller) over DMA
3. The internal keyboard appears as a standard USB keyboard
4. Linux's input subsystem picks it up and exposes it at `/dev/input/event*`
5. Purple's `EvdevReader` reads it like any other laptop keyboard

The existing `EvdevReader -> KeyboardStateMachine -> handle_keyboard_action()` pipeline should work unchanged. The keyboard just shows up like any other laptop.

**Important:** The `apple-bce` module must be loaded early in the boot process (in initramfs) for the keyboard to be available at boot time.

---

## One-Time Pre-Install Step: Disable Secure Boot

Before anything Linux can happen on a T2 Mac, someone must disable Secure Boot. This is a one-time, 2-minute GUI process in macOS Recovery. It cannot be automated or done from Linux.

### Steps

1. Turn on the Mac, immediately hold **Cmd+R** until the Apple logo appears
2. macOS Recovery loads (may take a minute)
3. Log in if prompted (any admin account)
4. Menu bar: **Utilities > Startup Security Utility**
5. Under "Secure Boot": select **No Security**
6. Under "External Boot": select **Allow booting from external or removable media**
7. Quit and restart

That's it. The Mac will now boot from USB drives and accept non-Apple operating systems.

### Who does this step?

- **Pre-configured Purple Laptops**: done once in the workshop before shipping. The parent never sees it.
- **DIY parents**: documented as "Step 1" with screenshots. It's a GUI with radio buttons, no terminal, no technical knowledge required.
- **If macOS is already gone**: Internet Recovery (Cmd+Option+R, requires internet once) restores the Recovery environment so you can access Startup Security Utility.

---

## Live Boot from USB

T2-Ubuntu ISOs come with the `apple-bce` driver pre-loaded, so the internal keyboard works from the live environment without an external keyboard.

### Boot flow

1. Plug in Purple Computer USB
2. Turn on Mac, hold **Option** key
3. Select the orange **EFI Boot** volume
4. Purple Computer boots from USB

### Adapting Purple's live boot for T2

Purple Computer's installer is a remastered Ubuntu Server ISO. To support T2 Macs, the live image needs:

1. **T2 kernel patches** included (either the t2linux patched kernel, or apply [linux-t2-patches](https://github.com/t2linux/linux-t2-patches) to the stock kernel)
2. **`apple-bce` module in initramfs** (so keyboard works immediately at boot)
3. **`efi=noruntime`** kernel parameter may be needed on some T2 models to avoid boot hangs

On non-T2 hardware, the apple-bce driver simply doesn't find a T2 chip and does nothing. So a single ISO can support both T2 and non-T2 machines.

---

## Full Install to Internal SSD

The internal NVMe SSD works with Linux. You can wipe macOS completely and single-boot Purple Computer.

### What's needed in the installed system

1. **T2-patched kernel**: the [T2-Debian-and-Ubuntu-Kernel](https://github.com/t2linux/T2-Debian-and-Ubuntu-Kernel) project provides pre-built .deb packages for Ubuntu 24.04 Noble, actively maintained (latest: Jan 2026, kernel 6.18.5)
2. **`apple-bce` in initramfs**: add `apple-bce` to `/etc/initramfs-tools/modules` and rebuild initramfs
3. **GRUB as bootloader**: install to the EFI System Partition. T2 Macs use standard EFI boot. Some users report needing [rEFInd](https://www.rodsbooks.com/refind/) if GRUB doesn't appear automatically, but for a wiped-macOS single-boot setup, GRUB at `/EFI/BOOT/BOOTX64.EFI` should work

### Partitioning

Standard GPT layout works:
- Partition 1: EFI System Partition (FAT32, 512MB)
- Partition 2: Root filesystem (ext4, rest of disk)

Use UUID-based root identification (consistent with Purple's existing boot setup).

### Boot after install

With macOS wiped and GRUB installed to the EFI fallback path, the Mac should boot directly into Purple Computer without holding any keys. If it doesn't, installing GRUB to additional EFI paths (same belt-and-suspenders approach Purple already uses for other hardware) should help:

```
/EFI/BOOT/BOOTX64.EFI           # UEFI spec fallback
/EFI/ubuntu/grubx64.efi          # Ubuntu default path
```

---

## Implementation Path

This doesn't need to be solved all at once. A reasonable progression:

### Phase 1: Manual validation

1. Get a T2-era MacBook Air (2018 or 2020 are the cheapest)
2. Disable Secure Boot via macOS Recovery
3. Boot a [T2-Ubuntu 24.04 live USB](https://github.com/t2linux/T2-Ubuntu/releases)
4. Verify: does `ls /dev/input/event*` show the internal keyboard?
5. Verify: does `evtest` show key events from the internal keyboard?
6. Verify: does audio output work (`aplay`, `speaker-test`)?

### Phase 2: Purple on T2 (manual install)

1. Install Ubuntu 24.04 with T2 kernel on the MacBook
2. Install Purple Computer normally
3. Verify the full experience: keyboard, audio, display, TTS, all three modes

### Phase 3: Unified installer ISO

1. Add T2 kernel patches to the golden image build
2. Add `apple-bce` to initramfs modules
3. Test that the same ISO still works on non-T2 hardware (ThinkPads, Dells, etc.)
4. Document the Secure Boot disable step for DIY parents

---

## Kernel Maintenance

The T2 kernel is an ongoing dependency. The [t2linux/T2-Debian-and-Ubuntu-Kernel](https://github.com/t2linux/T2-Debian-and-Ubuntu-Kernel) project:

- Actively maintained (releases through Jan 2026+)
- Tracks upstream Ubuntu kernel versions
- Provides pre-built .deb packages
- Applies a small, stable set of [patches](https://github.com/t2linux/linux-t2-patches)

Options for Purple Computer:
1. **Use their pre-built kernel .debs** (simplest, depends on t2linux project staying active)
2. **Apply their patches to Purple's kernel build** (more work, more control)
3. **Wait for upstream**: some T2 patches (Touch Bar, keyboard backlight) are being upstreamed to mainline Linux. The `apple-bce` driver is the big one that hasn't been upstreamed yet.

---

## References

- [t2linux wiki](https://wiki.t2linux.org/): main documentation hub
- [Hardware support state](https://wiki.t2linux.org/state/): what works and what doesn't
- [T2-Ubuntu (GitHub)](https://github.com/t2linux/T2-Ubuntu): Ubuntu ISOs for T2 Macs
- [T2 Debian/Ubuntu Kernel](https://github.com/t2linux/T2-Debian-and-Ubuntu-Kernel): pre-built kernel packages
- [apple-bce driver](https://github.com/t2linux/apple-bce-drv): keyboard/trackpad/audio driver source
- [linux-t2-patches](https://github.com/t2linux/linux-t2-patches): kernel patch set
- [Pre-install steps](https://wiki.t2linux.org/guides/preinstall/): Secure Boot disable guide
- [Apple T2 Mac models](https://support.apple.com/en-us/103265): official model list
