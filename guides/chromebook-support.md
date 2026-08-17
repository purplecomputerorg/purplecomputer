# Chromebook Support

> This guide is LLM-generated. The repo-side details were checked against the code; the Chromebook firmware and hardware claims were not verified on a real device.

Purple Computer does not support Chromebooks. We don't test on them and don't fix Chromebook-only bugs.

On an x86 Chromebook it can work after replacing the firmware. This guide covers what that involves.

---

## Why a Chromebook won't boot our USB

Chromebooks run Google's **depthcharge** firmware, which only boots ChromeOS-signed kernel partitions. It has no boot menu and no EFI boot manager.

Our ISO is an ordinary Ubuntu-shaped live image: shim → GRUB → casper, plus a legacy BIOS GRUB image. Depthcharge can't see any of that, so the stick doesn't appear. This is one layer below the ISO, so nothing on our side changes it.

**Ctrl+U does not help.** In Developer Mode it boots ChromeOS-format external media, not a normal Linux installer USB.

Changing the firmware is what the [MrChromebox](https://docs.mrchromebox.tech/) project does. MrChromebox knows nothing about Purple, and Purple knows nothing about Chromebooks. MrChromebox makes the machine boot normal x86 media, and our USB then behaves as it does on any other PC.

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

Both MrChromebox firmware options are compatible on paper. Secure Boot isn't active under MrChromebox firmware, so our signed chain goes unused, which is harmless.

---

## The two firmware options

| Option | What it does | Cost |
|---|---|---|
| **RW_LEGACY** | Adds an alternate bootloader alongside ChromeOS | No case opening, keeps ChromeOS, reversible |
| **Full UEFI ROM** | Replaces the firmware entirely, machine behaves like a normal PC | Wipes ChromeOS, requires disabling write protect |

### RW_LEGACY

Every boot lands on the Developer Mode "OS verification is OFF" screen: a 30 second delay, a beep, and Ctrl+L to continue. Pressing space at that screen re-enables verification and wipes the machine.

That makes it a good way to test, since it needs no screwdriver and is reversible, and a poor permanent setup for a machine a kid uses unsupervised.

### Full UEFI ROM

Removes the Developer Mode screen and gives a normal boot. Requires disabling firmware write protect first. On CR50/H1-era boards (most 2019+ Chromebooks) that means opening the back, unplugging the battery connector, and flashing while on AC power. Check the specific board on the [MrChromebox supported devices](https://docs.mrchromebox.tech/docs/supported-devices.html) page.

---

## Audio is the biggest unknown

Chromebooks of this era don't use standard HDA audio. They use I2S codecs (commonly `da7219` + `max98357a`) driven through SOF, with board-specific ALSA UCM profiles. Purple relies on speech, so silent TTS degrades it badly even when everything else works.

The golden image ships `firmware-sof-signed`, `alsa-ucm-conf`, and `alsa-topology-conf` (see `build-scripts/00-build-golden-image.sh`). Chromebook-specific UCM coverage is uneven and we have never tested it. Test speech before doing anything irreversible.

Expected to work but untested: the keyboard (Chrome EC presents a standard i8042 device, real Esc key, top row emits F1-F10, so the Ctrl+Alt+F2 escape hatch should work) and the display.

---

## Steps

Steps 1 through 6 are reversible. Step 7 is not, and it removes ChromeOS.

1. **Check the machine isn't enterprise-enrolled.** Managed Chromebooks block Developer Mode, and firmware work can't get around it. Check before buying a used unit.
2. **Enable Developer Mode.** This wipes local ChromeOS user data.
3. **Install RW_LEGACY** via the MrChromebox Firmware Utility Script. No case opening, ChromeOS stays put.
4. **Boot the Purple USB**: Ctrl+L at the Developer Mode screen, then Esc for the boot menu.
5. **Test audio.** If speech is silent, the rest won't fix it.
6. Check the keyboard, the screen, and that the parent menu is reachable.
7. **If that all passes:** disable write protect, flash the Full UEFI ROM, and install to the internal eMMC.

---

## Reporting back

None of this is tested or supported, so Chromebook-only bugs aren't ones we'll chase.

The most useful result to send back is the audio one: which board, whether speech produced sound, and the output of `aplay -l`.

Customer-facing wording lives in `guides/usb-boot-reference.md` (Chromebooks section).

---

## References

- [MrChromebox docs](https://docs.mrchromebox.tech/)
- [Supported devices](https://docs.mrchromebox.tech/docs/supported-devices.html) (board names, RW_LEGACY vs UEFI support)
- [Firmware types](https://docs.mrchromebox.tech/docs/firmware/types.html) (RW_LEGACY vs Full ROM)
- [Getting started](https://docs.mrchromebox.tech/docs/getting-started.html) (write protect, the utility script)
