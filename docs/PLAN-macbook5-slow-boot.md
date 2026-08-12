# Plan: MacBook5,x Slow Boot (about 5 minutes to first paint)

> **Status: INVESTIGATING, instrumented.** The delay is measured and located, but not yet root-caused. Section B (the bugs found along the way) is implemented and awaiting an ISO. Section A now has a tool: `purple-boot-timing` on the image reports the boot-phase split, initrd size and fragmentation, disk sequential and seek latency, and SMART, and `--menu on` flips the installed GRUB to a visible menu so the firmware-versus-GRUB split can be observed without hand-editing `grub.cfg` on a machine that is painful to type on.

## Symptom

On an Apple MacBook5,x (NVIDIA MCP79/9400M, late 2008 / 2009), the installed system takes roughly 5 minutes from power-on to Purple appearing. The screen sits on `EFI stub: Loaded initrd ...` for the whole wait, both warm and cold restarts. The live USB boot and the install itself work normally.

## What the evidence rules out

Measured on the machine, boot of 2026-08-11:

```
Startup finished in 4.579s (kernel) + 23.554s (userspace) = 28.133s
graphical.target reached after 23.510s
```

`/var/log/purple/boot.log` agrees end to end: wait-display 15:36:38 (display ready in 0.0s), X server ready :44, Alacritty :49, python :50, first render :54, mixer ok :59. Purple is fully up about 21 seconds after userspace starts.

`dmesg` is gapless from 0.0 to 13.6 seconds, where it ends. The largest gap in the whole log is about 1.5s around nouveau init. Specifically ruled out:

- **Not entropy starvation.** `random: crng init done` at 2.66s.
- **Not ATA/optical-drive link timeouts.** Both SATA links up at 1.92s, no resets, no `SRST failed`.
- **Not a blind framebuffer.** `fbcon: Taking over console` at 7.388s, `purple-splash.service` finished at 7.407s. The splash does paint once Linux is running.
- **Not swap or memory pressure.** No thrash in the log, boot completes in 28s.
- **Not any Purple service.** The slowest is `purple-audio-dump.service` at 13.764s, which is its deliberate `sleep 12` and does not block `graphical.target`.

## Where the time goes

Everything Linux can see accounts for 28 seconds. The remaining 4-plus minutes are spent **before the kernel's clock starts**, in Apple firmware, GRUB, and the EFI stub. That matches the visible symptom: the stub line is the last thing printed before the kernel takes over the display, so a stall anywhere in that window leaves exactly that text frozen on screen.

One command confirms it: `cat /proc/uptime` at first paint. If it reads about 35 after a 5-minute wait, every lost second is pre-kernel.

## The live USB does not have the delay

Booting the same machine from the live USB reaches Purple normally. This is the sharpest constraint we have, and it rules out most of the obvious explanations:

- **Not raw read volume.** The live boot reads a *larger* casper initrd, then a multi-GB squashfs, over USB 2.0, through the same firmware. If bytes-through-EFI were the bottleneck, live would be the slow one.
- **Not Apple's boot-device scan.** `BootCurrent: 0000` and `Boot0000* PurpleOS -> \EFI\purple\shimx64.efi`: the firmware goes straight to our NVRAM entry. No scanning phase to blame.
- **Not the shim/GRUB chain itself.** Both paths run shim then GRUB.

What differs is the **source medium and filesystem**: installed reads `/boot/vmlinuz` and `/boot/initrd.img` from ext4 on the internal SATA disk, live reads them from ISO9660 on the USB stick.

## Can we make the pre-kernel phase faster?

Two candidate causes remain, both actionable.

1. **The internal drive is slow or failing.** A 2009 Fujitsu doing read retries would crawl under firmware I/O while Linux, with its own driver and error handling, still boots in 28 seconds. This also explains the live-USB contrast on its own, since the live boot never touches `/dev/sda`. Settled by `dd` throughput and SMART counters. If this is it, the fix is a drive, not code.

   The drive is audibly loud during boot. Which noise it is discriminates between this and #2: continuous seeking that runs the whole wait and stops when Purple paints points at seek-thrashing under GRUB's access pattern (#2, fixable in layout); rhythmic clicking or repeated spin-up points at a failing drive (#1, fixable with a replacement); a brief whir at power-on then quiet means the disk is not the bottleneck during the wait at all.

   Note the tension with #1 as a pure hardware failure: Linux read the same drive with zero ATA errors in a 28-second boot. A drive that is healthy under Linux but slow under the pre-kernel path (one small blocking read at a time, no readahead, no NCQ) is consistent with everything observed; a dying drive is not, unless SMART says otherwise.
2. **GRUB's ext4 access pattern over Apple's EFI Block I/O.** GRUB's ext4 driver issues many small block reads. If Apple's Block I/O has millisecond-scale per-call latency, 76MB of kernel plus initrd in 4KB reads is minutes, while the same bytes off ISO9660 (fewer, larger, sequential reads) are not. This fits every observation including the live-USB contrast.

If it is #2, the fix is to stop reading big files off ext4 in the pre-kernel phase:

- **Stage `vmlinuz` and `initrd.img` on the ESP.** It is FAT, already 512MB, and mostly empty. GRUB's FAT driver reads large contiguous runs, and this is the standard layout for Mac Linux installs. Needs a copy step in `install.sh` plus a kernel-update hook, and a `grub.cfg` that points at `(hd0,gpt1)`.
- **Unified kernel image on the ESP.** Collapses shim, GRUB, kernel, and initrd into one file read. Bigger change to the signed boot chain, but the cleanest end state if file-count overhead turns out to dominate.

Secondary levers, cheap to test while we are in there:

3. **Shrink the initrd.** 61MB today. `MODULES=dep` typically gets to 20-30MB. Less compelling now that volume looks like the wrong axis, but it scales down whatever the per-byte cost turns out to be. Testable in place with `update-initramfs -u`.
4. **`efi=nochunk`.** The stub reads files in 1MB chunks to work around firmware that chokes on large reads; where per-call overhead dominates, chunking hurts. One cmdline word.
5. **Skip GRUB's `search`.** `search --no-floppy --label PURPLE_ROOT` scans every partition on every disk. The installer already knows the root UUID, so it can pin `set root=` instead. Seconds, not minutes, but free.

What we cannot do: paint anything during this window. The kernel does not own the display yet, so a progress indicator is impossible. If the delay proves unfixable on this class of hardware, the answer is a supported-hardware statement, not a UI change.

## Plan

### A. Root-cause the pre-kernel delay

1. **Disk health and speed first.** `dd` throughput and SMART counters. If the drive is sick, everything below is moot. Note both tools report to stderr, so add `2>&1` until the terminal fix ships.
2. Confirm pre-kernel with `/proc/uptime` read *at first paint*. A reading taken later only shows how long you have been sitting there.
3. Split firmware time from GRUB time: set `timeout=10` and `timeout_style=menu` in the installed `/boot/grub/grub.cfg`. Watch which side of the menu the wait falls on, and whether GRUB itself is sluggish to redraw (a slow GRUB UI is its own tell that firmware I/O is expensive).
4. **Test the ext4 hypothesis directly.** Copy `vmlinuz` and `initrd.img` to the ESP and add a menuentry loading them from `(hd0,gpt1)`. If that boots fast, the cause is GRUB reading ext4 over Apple Block I/O and the fix is a layout change, not a hardware limit.
5. Test the secondary levers, re-timing each: initrd shrink, then `efi=nochunk`.
6. Fold whatever wins into the golden image and `install.sh`: ESP staging plus a kernel-update hook, `initramfs.conf`, and/or the installed cmdline.

### B. Confirmed bugs, independent of A (implemented, needs an ISO to verify)

6. **In-app terminal is invisible.** `_run_shell` (`purple_tui/rooms/parent_menu.py:2506`) runs `subprocess.run([shell, '-i'])`, which inherits fd 2 pointing at `/tmp/purple-stderr.log` (`purple_tui/stderr_guard.py:47`). bash writes its prompt and readline's echo to stderr, so the shell runs but shows no prompt and no typed characters. Confirmed on hardware: blind-typing `ls` produces a listing. Fix: pass `stderr_guard`'s dup of the real terminal as the child's stderr.
7. **Ctrl+Alt+F2 spawns a second shell on tty2.** `_switch_to_tty2` (`purple_tui/input.py:441`) runs `openvt -s -f -c 2 -- login -f purple` while the autologin agetty (`00-build-golden-image.sh:746`) already owns tty2. Two processes reading one tty split the input stream, which is the dropped-character symptom seen on hardware. Fix: `chvt 2` and use the shell already there, matching the existing Ctrl+Alt+F1 path.
8. **`StartLimitIntervalSec` in the wrong section.** `purple-x11.service:53` puts it in `[Service]`; it belongs in `[Unit]`. systemd logs `Unknown key name ... ignoring`, so X restart rate-limiting has never been in effect.
9. **`purple-audio-dump.service` on installed images.** Its deliberate `sleep 12` puts it at the top of `systemd-analyze blame`, which misleads anyone debugging a slow boot. Debug-gate it.
10. Low priority: the installed `grub.cfg` lacks the `i915.enable_psr=0 i915.enable_fbc=0` that every live cmdline carries. Irrelevant on this nouveau Mac, but an unintended live-vs-installed asymmetry.

### C. Verify and ship

11. Build an ISO with 6-9. Retest on this MacBook plus one Intel machine and one PC, since 6 and 7 touch the VT and terminal paths everywhere.
12. `docs/UX_LOG.md` entry for the terminal fix.
13. Guide section on MacBook5,x once A concludes.
14. Release-pick decisions: 6, 7, 8 read as fixes. 9 and 10 are judgment calls to propose and confirm.

## Checklist to run on the machine

On the next ISO this is one command:

```bash
sudo purple-boot-timing
```

It reports the boot-phase split, time to first paint, kernel and initrd size, their extent counts, sequential read throughput, per-seek latency over 200 random 4K reads, and SMART. Then:

```bash
sudo purple-boot-timing --menu on    # reboot, watch which side of the menu the wait is on
```

Reading the numbers:

- **Sequential under ~10 MB/s, or nonzero reallocated/pending sectors**: the drive is the problem, and the code plan mostly evaporates.
- **Seek latency above ~50ms**: seeks dominate, which supports the ext4-access-pattern theory and makes ESP staging the fix.
- **Both healthy, and the menu appears promptly with the wait after it**: firmware per-call overhead on file reads, so try `efi=nochunk` and ESP staging.
- **Both healthy, and the wait is before the menu appears**: Apple firmware, and there is likely nothing to fix in software.

Also worth capturing by ear: whether the drive noise spans the whole wait and stops at first paint.

## Machine profile

Confirmed on the machine, 2026-08-11:

- `MacBook5,2`. RAM 1712MB usable, no swap.
- `/boot/initrd.img-6.8.0-31-generic` is 61,399,280 bytes. `vmlinuz` is 14,928,264. About 76MB read before the kernel starts.
- `fw_platform_size` = 64.
- `efibootmgr`: `BootCurrent: 0000`, `BootOrder: 0000,0080`. `Boot0000* PurpleOS` points at `\EFI\purple\shimx64.efi` on the internal disk. `Boot0080` is Apple's `boot.efi`, `BootFFFF` the live USB's `\EFI\BOOT\BOOTX64.EFI`. Our NVRAM entry is the one in use.

From `dmesg`:

- NVIDIA MCP79/MCP7A, nouveau NVAC, 256MB stolen system memory. Alacritty took the hardware GL path (core profile 3.3).
- forcedeth nForce ethernet, b43 wifi, FireWire OHCI, appletouch Geyser trackpad, applesmc, Apple IR receiver.
- FUJITSU MHZ2160BH, 160GB, SATA 1.5Gbps, UDMA/100. MATSHITA DVD-R UJ867A.
- TSC 2122 MHz, marked unstable, switched to hpet. Normal for this era.
- This is a MacBook5,x (late 2008 / 2009), not the 2007 Core Duo it was reported as. It has 64-bit EFI, which is why the x64 shim/GRUB chain runs at all.
- RTC is wrong: "System time before build time, advancing clock", and journald rotates on "Realtime clock jumped backwards" every boot. Likely a dead PRAM battery, and with no network sync the clock stays wrong. Cosmetic, but it makes journal timestamps untrustworthy across boots.
