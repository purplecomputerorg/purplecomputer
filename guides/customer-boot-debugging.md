# Debugging a customer's boot from the stick they already have

Every Purple stick records its own boot, and every stick can show the boot menu
when P is held. This guide is the outward-facing version: what to ask a customer
to do, what comes back, and how to read it. The mechanisms behind it are in
`boot-hang-debugging.md`.

## What every stick does on its own

Nothing here needs the debug ISO or any key press. It ships on the standard ISO.

- **`PURPLE-LOG.TXT`** on the `PURPLEUSB` drive, one file with two parts. First
  the report, rewritten every 5 seconds for the first five minutes, then once
  a minute: machine and BIOS, kernel command line, whether P was held, failed
  services, what every process is waiting on, Purple's own logs, the journal.
  It starts as soon as the kernel finds the stick: the initramfs writes a
  first version before the system is even mounted (and again right before
  mounting it, and at the end of casper-bottom), so a boot that never reaches
  Purple still leaves one. If the file starts with `purple-initramfs:`, boot
  stopped at that stage. After the report, past some reserved blank space, the
  kernel log written live, flushed at least once a second early in boot, so
  the last seconds before a hang are in it. The file is a fixed 12MB and its
  date is the build date; the report's own time is on its first line.
- **The turn-it-off-first note** and this drive are what a parent sees when they
  plug the stick into a running Windows or Mac computer. The file opens in
  Notepad or TextEdit.

## What to tell a customer

For a boot that hangs or never shows Purple:

1. Wait two minutes after the screen stops changing.
2. Hold the power button until the laptop turns off.
3. Plug the stick into your usual computer. A drive named `PURPLEUSB` appears.
   If Windows asks to format a disk, or a Mac says a disk is not readable,
   choose Cancel or Ignore. Never Format or Initialize.
4. Email `PURPLE-LOG.TXT` from that drive, plus one photo of the last thing on
   the laptop's screen.

That is usually enough. Ask for the next step only when the reports say the
fix needs a different boot.

## Hold P: the boot menu on any stick

Holding P while the laptop starts opens the same menu the debug ISO shows.
Instruction for the customer, exactly:

> Hold down the P key before you press the power button, and keep holding it
> until you see text on the screen. On a Mac, hold Option to pick the USB drive
> as usual, and start holding P the moment you press Enter on it.

Two layers make this work, and the customer does not need to know which one
fired:

- **GRUB's hotkey.** The key waits in the firmware's keyboard buffer and GRUB
  matches it in the single poll it makes before its zero timeout. The full menu
  opens with no delay added to ordinary boots. Works on firmware that keeps the
  buffer across the handoff to the bootloader, which is most PCs and Macs.
- **The initramfs check.** A second or two into the kernel, Linux reads the
  held-key state from every keyboard it can see (`purple-keyheld`, evdev, so
  Apple SPI keyboards count) and, if P is down, puts the kernel log on the
  screen with the earlier lines replayed and turns debug mode on. This layer
  cannot change kernel arguments, so it gives the verbose boot but not the USB
  workarounds.

The menu, in order:

| Entry | Use it when |
|---|---|
| Troubleshooting: start Purple and show what's happening | Default after 10s. Verbose boot, kernel and service lines on screen. |
| Troubleshooting: try every fix for USB drive problems | USB read errors (`SQUASHFS error`, `I/O error, dev loop0`). IOMMU off, 32-bit USB DMA, no USB autosuspend, no PCIe power saving, system copied into RAM, bigger kernel log. One boot instead of five. |
| Start Purple normally | The ordinary boot, for someone who held P by accident or for comparison. |
| More options (for support) | A submenu: keyboard test, the USB fixes one at a time (for narrowing down which one mattered), recovery shell, our two failure-page self-tests, boot from the next volume, firmware settings. |

What to ask for after a menu boot: the same file plus a photo, or a video
of the screen when the problem is early (before the stick is found, the screen
is the only record).

## Reading what comes back

- **`PURPLE-LOG.TXT` starts with `purple-initramfs:`** and the message names
  the stage: the boot never got past mounting the system. The dmesg section
  shows why (USB errors, missing driver, memory).
- **`debug mode: on, P held at start: yes`** in the header: the customer held P
  and the initramfs saw it, so the screen showed the kernel log.
- **`purple-initramfs: copying the system`** followed by
  `THE USB STICK COULD NOT BE READ after N bytes`: the RAM copy hit a bad
  read at that offset. Compare with the failing sectors in the dmesg lines.
- **The file still says "This stick has not been started yet":** the kernel
  never found the stick, or the stick does not accept writes. Ask for a video
  of the boot with the menu's first entry.
- **The kernel log at the end stops mid-boot** while the report above it looks
  complete: the stick stopped accepting writes at that moment. The last lines
  there are the ones just before it.

## When a different ISO is still needed

The debug ISO is the same image with the menu shown on every boot. Use it, or a
one-off, when a customer cannot hold a key (a firmware that drops it and a
keyboard the initramfs cannot see are both rare) or when you want a build from
a specific commit:

```
just ship-oneoff <commit> <name>       # files.purplecomputer.org/oneoff/<name>.iso
```

Then the instructions are: flash it, boot it, pick the entry by number, and
send the same file and a photo.
