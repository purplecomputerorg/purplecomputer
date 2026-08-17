# Chromebook Support

**Official answer: Purple Computer does not support Chromebooks.** We don't test on them, we don't ship instructions for them, and we don't fix Chromebook-only bugs.

This guide exists because the question comes up, and because the honest technical answer is more interesting than "no." On an x86 Chromebook it *can* work, but only after the owner replaces the firmware. That's a job for someone comfortable opening a laptop, not for a parent.

---

## Why a Chromebook won't boot our USB

Chromebooks don't have a normal PC firmware. They run Google's **depthcharge**, which only boots ChromeOS-signed kernel partitions. It has no boot menu, no EFI boot manager, and no notion of "boot this USB stick."

Our ISO is an ordinary Ubuntu-shaped live image: shim → GRUB → casper, plus a legacy BIOS GRUB image. Depthcharge can't see any of that, so the stick simply doesn't appear. Nothing on our side can fix this: the block is one layer below the ISO.

A common misconception: **Ctrl+U does not help.** In Developer Mode, Ctrl+U boots ChromeOS-format external media, not a normal Linux installer USB.

The fix is to change the firmware, which is what the [MrChromebox](https://docs.mrchromebox.tech/) project does. MrChromebox knows nothing about Purple, and Purple knows nothing about Chromebooks. MrChromebox just turns the machine into something that boots normal x86 media, and after that our USB is unremarkable.

---

## What our ISO needs from the firmware

Verified in this repo, not on Chromebook hardware:

| Requirement | Status |
|---|---|
| Legacy BIOS boot | ISO carries a BIOS El Torito entry (`/boot/grub/i386-pc/eltorito.img`) |
| UEFI boot | ISO carries the UEFI El Torito entry + `/EFI/BOOT/BOOTX64.EFI` |
| Installed system boots either way | `install.sh` writes UEFI paths *and* MBR + `core.img` in a `bios_grub` partition |
| eMMC storage | `install.sh` handles `mmcblk0` → `mmcblk0p1` naming |
| Disk size | 16 GB minimum, so a 32 GB eMMC is fine |
| Display | 1366x768 is our fallback baseline in `scripts/calc_font_size.py` (15.0pt font) |

So both MrChromebox firmware options are compatible on paper. Secure Boot won't be active under MrChromebox firmware; our signed chain just goes unused, which is harmless.

---

## The two firmware options

| Option | What it does | Cost | Good enough for Purple? |
|---|---|---|---|
| **RW_LEGACY** | Adds an alternate bootloader alongside ChromeOS | No case opening, keeps ChromeOS, reversible | **Testing only** |
| **Full UEFI ROM** | Replaces the firmware entirely, machine behaves like a normal PC | Wipes ChromeOS, requires disabling write protect (usually a battery disconnect) | Yes |

### Why RW_LEGACY is not a shipping config

It works, but every single boot lands on the Developer Mode "OS verification is OFF" screen: a 30 second delay, a loud beep, and Ctrl+L required to continue. Worse, pressing space at that screen re-enables verification and **wipes the machine**.

That is disqualifying for a kids' computer. It's still the right way to *test*, because it's non-destructive and needs no screwdriver.

### Full UEFI ROM

Removes the Developer Mode screen entirely and gives a normal boot. Requires disabling firmware write protect first. On CR50/H1-era boards (most 2019+ Chromebooks) that means opening the back, unplugging the battery connector, and flashing while on AC power. Check the specific board on the [MrChromebox supported devices](https://docs.mrchromebox.tech/docs/supported-devices.html) page.

---

## The real risk is audio, not boot

Boot is the visible problem, so it gets all the attention. Audio is the one that actually decides whether Purple is usable.

Chromebooks of this era don't use standard HDA audio. They use I2S codecs (commonly `da7219` + `max98357a`) driven through SOF, with board-specific ALSA UCM profiles. Purple is speech-heavy: if TTS is silent, everything boots fine and the product is still badly degraded.

We ship the right package set in the golden image (`firmware-sof-signed`, `alsa-ucm-conf`, `alsa-topology-conf`, see `build-scripts/00-build-golden-image.sh`), but Chromebook-specific UCM coverage is uneven and we have never tested it. **Test speech before doing anything irreversible.**

Expected to be fine, but untested: the keyboard (Chrome EC presents a standard i8042 device, real Esc key, top row emits F1-F10, so the Ctrl+Alt+F2 escape hatch should work) and the display.

---

## If someone wants to DIY it anyway

Order matters here. Do the cheap reversible test first, and only then do the irreversible part.

1. **Check the machine isn't enterprise-enrolled.** Managed school Chromebooks block Developer Mode outright, and no amount of firmware work gets around it. Verify this before buying a used unit.
2. **Enable Developer Mode.** This wipes local ChromeOS user data.
3. **Install RW_LEGACY** via the MrChromebox Firmware Utility Script. No case opening, ChromeOS stays put.
4. **Boot the Purple USB** (Ctrl+L at the Developer Mode screen, then Esc for the boot menu).
5. **Test audio first.** If speech is silent, stop: the rest isn't worth it.
6. Also check the keyboard, the screen, and that the parent menu is reachable.
7. **Only if all that passes:** disable write protect, flash the Full UEFI ROM, and install to the internal eMMC.

Steps 1 through 6 are reversible. Step 7 is not, and it removes ChromeOS.

---

## What we support

Nothing on this page is tested or supported. Someone doing this is on their own, and Chromebook-only bugs aren't ones we'll chase.

If someone does try it, the audio result is the single most useful thing they can report back: which board, whether speech produced sound, and the output of `aplay -l`.

Customer-facing wording lives in `guides/usb-boot-reference.md` (Chromebooks section) and stays a simple "this won't work."

---

## References

- [MrChromebox docs](https://docs.mrchromebox.tech/)
- [Supported devices](https://docs.mrchromebox.tech/docs/supported-devices.html) (board names, RW_LEGACY vs UEFI support)
- [Firmware types](https://docs.mrchromebox.tech/docs/firmware/types.html) (RW_LEGACY vs Full ROM)
- [Getting started](https://docs.mrchromebox.tech/docs/getting-started.html) (write protect, the utility script)
