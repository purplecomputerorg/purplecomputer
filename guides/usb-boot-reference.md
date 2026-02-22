# USB Boot Reference

How to boot a laptop from a Purple Computer USB drive, covering all major hardware.

This guide is the technical reference behind whatever user-facing materials we ship (printed card, help page, setup email). It documents every boot method we know about, the gotchas, and the fallbacks.

---

## The Three Paths

Almost every laptop falls into one of three boot paths:

| Path | Covers | Method |
|------|--------|--------|
| **F12 at power-on** | Most PC laptops | Tap F12 during startup, pick the USB drive |
| **Windows Shift+Restart** | All Windows PCs (universal fallback) | Hold Shift, click Restart, click "Use a device" |
| **Hold Option at power-on** | All Intel Macs | Hold Option key during startup, pick the USB drive |

F12 is the fastest. Shift+Restart is the most reliable (works regardless of brand, Fast Boot settings, or disabled boot menus). Hold Option is the only path for Macs.

---

## PC Laptops: Boot Key Reference

### Brand-to-Key Table

| Brand | Boot Menu Key | BIOS/UEFI Setup Key | Notes |
|-------|--------------|---------------------|-------|
| **Lenovo** (ThinkPad, IdeaPad, Yoga) | F12 | F1 (ThinkPad) or F2 (IdeaPad) | Some models: press Enter first to get an interrupt menu, then F12. Consumer models may need Fn+F12 if function keys are in media mode. |
| **Dell** (Latitude, Inspiron, XPS, Vostro) | F12 | F2 | Most reliable brand for this. F12 works consistently across all Dell laptops. |
| **HP** (Pavilion, EliteBook, ProBook, Spectre) | Esc, then F9 | Esc, then F10 | HP is a two-step: Esc opens a "Startup Menu" listing F1/F2/F9/F10/F11 options. Press F9 from that menu for boot device selection. Some models accept F9 directly. |
| **ASUS** (VivoBook, ZenBook, ROG) | Esc | F2 | Some older models use F8 instead of Esc. |
| **Acer** (Aspire, Swift, Nitro) | F12 (often disabled) | F2 | See "Acer Gotchas" section below. F12 is disabled by default on many models. |
| **Toshiba / Dynabook** | F12 | F2 | Straightforward, same as Dell/Lenovo. |
| **Samsung** | F10 | F2 | Notable outlier: F10 instead of F12. |
| **Sony VAIO** | F11 | F2 | Some models have a physical Assist button near the power button that's more reliable than F11. |
| **MSI** | F11 | Del | Common on gaming laptops. |
| **Fujitsu** | F12 | F2 | Same as Dell/Lenovo. |
| **Gateway** | F12 | F2 | Same as Acer (Gateway is an Acer brand). |

### The "Try This First" Instruction

For a parent who doesn't know their laptop brand (or doesn't want to look it up):

> Turn on the laptop and immediately start tapping F12 repeatedly. If a menu appears with your USB drive listed, select it and press Enter.

F12 is the single most common boot menu key. It works on Lenovo, Dell, Toshiba, Fujitsu, Gateway, and (when enabled) Acer. That's the majority of PC laptops.

---

## Universal Fallback: Windows Shift+Restart

This method works on **every Windows 10/11 PC regardless of brand**. It bypasses all boot key timing issues, Fast Boot, and disabled boot menus. It should be the primary "didn't work?" fallback.

### Steps

1. Plug in the Purple Computer USB drive
2. Open the Start menu, click the Power icon
3. **Hold the Shift key** and click **Restart**
4. The laptop restarts to a blue "Choose an option" screen
5. Click **Use a device**
6. Select the USB drive (may appear as "EFI USB Device", "USB Storage", or by the drive brand name like "SanDisk")

### Alternative paths to the same screen

**From Settings (Windows 10):**
Settings > Update & Security > Recovery > "Advanced startup" > Restart now

**From Settings (Windows 11):**
Settings > System > Recovery > "Advanced startup" > Restart now

### When this doesn't work

- **USB drive doesn't appear in the list**: the USB may not be bootable, or Secure Boot is blocking it. See "Secure Boot" section below.
- **"Use a device" option is missing entirely**: the firmware doesn't support this feature (rare, mostly very old machines), or no bootable USB is detected. Fall back to the F-key method or BIOS boot order change.
- **Windows isn't bootable**: if the laptop can't get to Windows at all, this method isn't available. Use the F-key method instead.

---

## Intel Macs

All Intel Macs (2012-2020) use the same basic method: hold Option at startup. The complication is the T2 security chip on 2018-2020 models.

### Pre-T2 Macs (2012-2017)

1. Plug in the Purple Computer USB drive
2. Turn off the Mac completely (Apple menu > Shut Down, not just close the lid)
3. Press the Power button
4. **Immediately press and hold the Option key** (labeled Alt on non-Apple keyboards)
5. Continue holding until Startup Manager appears (disk icons on screen)
6. Select the USB drive (may appear as "EFI Boot" with an orange icon)
7. Click the arrow or press Enter

That's it. No BIOS, no setup, no complications.

### T2 Macs (2018-2020): One-Time Setup Required

Macs with the T2 Security Chip block external boot by default. Before the Option key method will work, someone must disable this restriction once. See `guides/t2-mac-support.md` for the full details. The short version:

1. Turn on the Mac, immediately hold **Cmd+R** until the Apple logo appears
2. macOS Recovery loads (may take a minute)
3. Log in if prompted (any admin account on the machine)
4. Menu bar: **Utilities > Startup Security Utility**
5. Under "Secure Boot": select **No Security**
6. Under "External Boot": select **Allow booting from external or removable media**
7. Quit and restart

After this one-time step, the standard "hold Option" method works.

### Which Macs have the T2 chip?

All Intel Macs from late 2018 through 2020:
- MacBook Air (2018, 2019, 2020)
- MacBook Pro 13" (2018, 2019, 2020)
- MacBook Pro 15" (2018, 2019)
- MacBook Pro 16" (2019)
- Mac mini (2018)
- iMac 27" (2020)

If you're not sure: Apple menu > About This Mac. If it says "Chip: Apple M1/M2/M3", it's Apple Silicon (not supported). If it says "Processor: Intel" and the year is 2018+, it has a T2 chip.

### Apple Silicon Macs (M1/M2/M3, late 2020+)

**Not supported.** These use a completely different architecture (ARM, not x86_64). Purple Computer requires an Intel CPU. Don't attempt to boot the Purple USB on these machines.

### Mac-specific notes

- **USB-C ports**: MacBooks from 2016 onward only have USB-C ports. The Purple USB drive needs a USB-A to USB-C adapter, or you need a USB-C flash drive.
- **Option key location**: on Apple keyboards, Option is between Control and Command on the bottom row. On external PC keyboards plugged into a Mac, it's the Alt key.
- **If Startup Manager doesn't appear**: make sure the Mac was fully shut down (not sleeping). Hold the power button for 10 seconds to force off, then try again.

---

## Microsoft Surface

Surface devices don't use keyboard keys for boot menus. They use hardware volume buttons.

### Surface Pro (all generations) and Surface Go

1. Shut down the Surface completely
2. Plug in the USB drive
3. Press and hold the **Volume Down** button (on the left or top edge)
4. While still holding Volume Down, press and release the **Power** button
5. Continue holding Volume Down until you see spinning dots or the Surface logo
6. Release Volume Down; the device boots from USB

### Surface Laptop (no physical volume buttons)

Surface Laptops don't have volume buttons on the chassis. The volume keys are on the function row:

| Model | Volume Down Key |
|-------|----------------|
| Surface Laptop 1, 2 | **F5** |
| Surface Laptop 3, 4, 5 | **F3** |

Same process: hold the Volume Down function key, press and release Power, keep holding until the Surface logo appears.

### Surface Book

Volume Down is on the **tablet portion** (the screen), not the keyboard base. Same process as Surface Pro.

### Alternative: Shift+Restart from Windows

The universal Windows fallback (Shift + click Restart > Use a device) works on all Surface devices and is often easier than the hardware button method.

### Surface UEFI Settings

If you need to change boot order permanently or disable Secure Boot, use **Volume Up + Power** (instead of Volume Down) to enter Surface UEFI:

1. Shut down the Surface
2. Press and hold **Volume Up**
3. Press and release **Power**
4. Release Volume Up when the Surface UEFI screen appears

From UEFI:
- **Boot configuration**: drag "USB Storage" above "Windows Boot Manager"
- Make sure "Enable Boot from USB devices" is **On**
- To disable Secure Boot: Security > Secure Boot > Disabled

### Surface gotchas

- **USB-C adapters**: Surface Pro 8/9 and newer Surface Go models only have USB-C ports. Need a USB-A to USB-C adapter.
- **BitLocker**: many Surface devices ship with BitLocker (device encryption) enabled by default. Changing UEFI settings (like disabling Secure Boot) triggers a BitLocker recovery prompt next time Windows boots. This doesn't affect Purple Computer installation, but it means the parent can't easily go back to Windows without their BitLocker recovery key.

---

## Acer Gotchas

Acer is the most troublesome brand for USB booting. The F12 boot menu is **disabled by default** on most Acer laptops manufactured after ~2015.

### The problem

Pressing F12 at startup does nothing on a stock Acer laptop. The key is recognized by the BIOS, but the boot device selection feature is turned off. The parent taps F12, nothing happens, and they're stuck.

### Solution 1: Shift+Restart (recommended)

If Windows is running, the universal Shift+Restart method completely bypasses this problem. No BIOS changes needed, no F12 required. This is the best path for Acer owners.

### Solution 2: Enable F12 in BIOS

If Shift+Restart isn't available (Windows is gone or broken):

1. Turn off the laptop, plug in the USB drive
2. Turn it on and immediately start tapping **F2** to enter BIOS Setup
3. Navigate to the **Main** tab
4. Find **F12 Boot Menu** and change it from Disabled to **Enabled**
5. Press **F10** to save and exit
6. The laptop reboots. Now tap **F12** during startup.
7. Select the USB drive from the boot menu

### Solution 3: Change boot order in BIOS

Instead of enabling the F12 menu, you can change the permanent boot order:

1. Enter BIOS with F2 (same as above)
2. Navigate to the **Boot** tab
3. Use F5/F6 (or +/-) to move the USB device to the top of the boot priority list
4. Press F10 to save and exit

The USB drive **must be plugged in** when you enter BIOS, otherwise it won't appear in the list. This changes the boot order permanently (until you change it back).

### Additional Acer quirks

- **Fn key mode**: if F2 doesn't work, try **Fn+F2**. Some Acer laptops default to media keys on the function row.
- **Supervisor Password gate**: on some Acer models, Secure Boot and boot order settings are **grayed out** in BIOS until you set a Supervisor Password. The workaround: go to Security tab > Set Supervisor Password, set any password, then the boot settings become editable. After making changes, you can clear the password by setting it to blank.
- **UEFI-only mode**: if the BIOS is set to UEFI-only (common on newer Acers), a USB drive formatted as MBR/Legacy won't appear at all. Purple Computer's USB is GPT/EFI, so this shouldn't be a problem.
- **Alt+F10**: this launches Acer's factory recovery partition, **not** the boot menu. It's not useful for USB booting.

---

## Lenovo Novo Button

Some Lenovo consumer laptops (IdeaPad, Yoga, Legion) have a small **Novo button**: a tiny pinhole button on the side or near the power button. Pressing it with a paperclip when the laptop is off opens a boot menu. This is an alternative to F12 on these models.

ThinkPads don't have a Novo button (they use F12 or the Enter key interrupt menu).

---

## Secure Boot

### Does Purple Computer work with Secure Boot enabled?

Yes, on most hardware. Purple Computer's USB uses Ubuntu's signed shim and GRUB bootloader, which are trusted by most UEFI firmware. Secure Boot can stay enabled.

### When Secure Boot causes problems

- **Surface devices with recent firmware**: a 2023+ firmware update introduced "NX mode" which can cause the MOK (Machine Owner Key) enrollment screen to freeze. Workaround: disable Secure Boot entirely in Surface UEFI.
- **Some Acer laptops**: Secure Boot settings are grayed out until a Supervisor Password is set (see Acer section above).
- **Very old UEFI implementations**: some 2012-2013 era firmware doesn't trust the Ubuntu shim. Disable Secure Boot if the USB fails to appear.
- **Custom/unsigned kernels**: if we ship a T2-patched kernel or any non-Ubuntu-signed kernel, Secure Boot must be disabled on that machine.

### How to disable Secure Boot (generic)

1. Enter BIOS/UEFI setup (F2, F10, Del, or Esc depending on brand)
2. Find "Secure Boot" under the Security or Boot tab
3. Change to Disabled
4. Save and exit (usually F10)

On Macs, Secure Boot is handled differently through Startup Security Utility (see the Mac section above).

---

## Fast Boot

Some laptops ship with "Fast Boot" or "Ultra Fast Boot" enabled in BIOS. This skips the POST screen and goes straight to the OS, making it impossible to press any boot key (F12, F2, Esc, etc.).

### Symptoms

The laptop powers on and jumps straight to the Windows login screen. No manufacturer logo, no "Press F2 for Setup" text, no opportunity to press anything.

### Workaround

The Shift+Restart method works even with Fast Boot enabled, because it instructs the firmware to show the boot menu on the next restart.

If you need to disable Fast Boot permanently:
1. Use Shift+Restart to get to the blue "Choose an option" screen
2. Click **Troubleshoot > Advanced options > UEFI Firmware Settings > Restart**
3. This opens BIOS/UEFI setup
4. Find "Fast Boot" under the Boot tab and disable it
5. Save and exit

---

## Troubleshooting

### "No bootable device" or USB doesn't appear in boot menu

1. Try a different USB port (some BIOS firmwares only detect USB-A ports, not USB-C)
2. Make sure the USB drive is fully inserted
3. Try the Shift+Restart method (if Windows is available)
4. Check that the USB was flashed correctly (`flash-to-usb.sh` includes verification)
5. Check Secure Boot settings (try disabling it)
6. On Acer: F12 boot menu may be disabled (see Acer section)

### Boot menu appears but USB drive isn't listed

1. The USB drive may not be bootable (reflash it)
2. UEFI-only firmware won't show MBR/Legacy USB drives (Purple's USB is GPT/EFI, so this should be fine)
3. Some firmware needs the USB plugged in **before** power-on, not after

### USB boots but hangs or shows a black screen

1. Try adding `nomodeset` to the kernel command line (press `e` in GRUB, add `nomodeset` to the `linux` line, press F10)
2. On T2 Macs, `efi=noruntime` may be needed
3. Wait 30 seconds, some hardware is slow to initialize displays

### "Shift+Restart" doesn't show "Use a device"

1. Make sure the USB is plugged in **before** clicking Restart
2. The firmware may not support this feature (rare, mostly pre-2014 machines)
3. Fall back to the F-key method

---

## Quick Reference Card Content

This is the content for a printed card shipped with the USB drive. Designed to fit on a small insert (business card or postcard size).

### Front

```
SETUP: BOOT FROM USB

1. Plug in the Purple Computer USB drive

2. Turn off the laptop completely

3. Turn it back on and immediately
   start tapping F12

4. Pick the USB drive from the list
   and press Enter

   Didn't work?  →  Flip this card
```

### Back

```
IF F12 DIDN'T WORK

From Windows:
  1. Plug in the USB
  2. Hold Shift and click Restart
  3. Click "Use a device"
  4. Pick the USB drive

Got a Mac?
  1. Shut down the Mac
  2. Turn it on while holding
     the Option key
  3. Pick the USB drive

Still stuck? [help URL or QR code]
[SUPPORT_EMAIL]
```

### Design notes

- The front covers ~65% of PC laptops (F12 works)
- The back covers the rest: Shift+Restart handles all the tricky PC brands (HP, Acer, ASUS, Samsung) without needing a brand lookup table, and "hold Option" handles all Macs
- QR code on the back links to a help page covering T2 Macs, Surface, Acer BIOS quirks, Secure Boot, and other long-tail issues
- No jargon: "BIOS", "UEFI", "EFI", "boot menu" never appear on the card
- The card says "Pick the USB drive", not "Select EFI Boot" because the exact label varies by firmware

---

## Hardware-Specific Notes for the Help Page

These are too detailed for the printed card but should live on a web help page (linked via QR code).

### HP laptops

> Your HP laptop uses a two-step process. Press **Esc** right when the laptop turns on, then press **F9** from the menu that appears. Or use the Shift+Restart method from Windows (see above).

### ASUS laptops

> Press **Esc** right when the laptop turns on. If that doesn't work, try **F8** (used on older ASUS models). Or use the Shift+Restart method from Windows.

### Samsung laptops

> Samsung uses **F10** instead of F12. Press F10 right when the laptop turns on. Or use the Shift+Restart method from Windows.

### Acer laptops

> Acer laptops often have the boot menu turned off. The easiest path is the Shift+Restart method from Windows. If Windows isn't available, you'll need to enter the laptop's settings: tap **F2** at startup, find "F12 Boot Menu" and turn it on, save and restart, then tap F12.

### Microsoft Surface

> Surface devices use the volume button instead of a keyboard key. Shut down the Surface, hold the **Volume Down** button, press Power, and keep holding Volume Down until you see the Surface logo. If your Surface doesn't have a volume button on the side (Surface Laptop), use the Shift+Restart method from Windows instead.

### Macs from 2018-2020 (T2 chip)

> These Macs need a one-time setup before USB boot will work. Turn on the Mac while holding **Cmd+R** to enter Recovery Mode. Go to Utilities > Startup Security Utility. Set Secure Boot to "No Security" and External Boot to "Allow." Restart, then follow the normal Mac instructions (hold Option at startup).

### Chromebooks

> Purple Computer does not work on Chromebooks. Chromebooks use a different kind of processor and operating system that isn't compatible.

Note: some Chromebooks do have x86 CPUs and can technically run Linux, but the boot process (Developer Mode, legacy BIOS via ctrl+L) is complex enough that we should not support or document it.
