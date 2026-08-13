# MacBook5,2: five minutes to first paint, and what it turned out to be

> **Status: root-caused; fixes 1 and 2 implemented, awaiting a build and the hardware matrix.** Three independent costs, all in the pre-kernel phase, all measured by isolation on the machine. Linux was never slow. Fix 3 (ESP staging) is deliberately held back until 1 and 2 have been validated on hardware, so a boot regression stays attributable. A separate set of bugs found along the way is listed at the end; three of them are already fixed and shipped.

## Symptom

An Apple MacBook5,2 (NVIDIA MCP79/9400M, 2009) took about five minutes from power-on to Purple appearing, on both warm and cold restarts. The screen sat on `EFI stub: Loaded initrd ...` for the whole wait. The live USB boot and the install itself were normal. Reported originally as a 2007 Core Duo, which mattered: a real Core Duo is 32-bit and would not have booted at all.

## Machine profile

- `MacBook5,2`. Core 2 Duo, TSC 2122 MHz (marked unstable, switched to hpet, normal for the era). 1712MB usable RAM, no swap.
- NVIDIA MCP79/MCP7A on nouveau (`NVAC`), 256MB stolen system memory. Alacritty took the hardware GL path, core profile 3.3.
- forcedeth nForce ethernet, b43 wifi, FireWire OHCI, appletouch Geyser trackpad, applesmc, Apple IR receiver.
- FUJITSU MHZ2160BH, 160GB, SATA 1.5Gbps, UDMA/100. **MATSHITA DVD-R UJ867A optical drive, empty.** That drive matters; see cost 2.
- 64-bit EFI, which is why the x64 shim and GRUB chain runs at all. `BootCurrent: 0000`, `Boot0000* PurpleOS -> \EFI\purple\shimx64.efi`, so the firmware uses our NVRAM entry directly.
- RTC is wrong and jumps ("System time before build time, advancing clock", journald rotating on "Realtime clock jumped backwards" every boot). Likely a dead PRAM battery. Cosmetic, but it makes cross-boot timestamps untrustworthy, which shaped how we measured.

## How to measure this (the method that finally worked)

The trap is that every log the machine keeps starts *after* the slow part. `systemd-analyze`, `dmesg`, and `/var/log/purple/boot.log` all agreed the boot took under 35 seconds while the user waited five minutes. Nothing in Linux can see the pre-kernel window.

What works:

- **Wall clock minus `/proc/uptime`.** Note the phone time when GRUB hands off (or when you press Enter at the menu), note it again at first paint, then read `/proc/uptime`. Pre-kernel seconds = elapsed minus uptime. This is the only measurement that spans the invisible window.
- **`systemd-analyze`** for the Linux half, so you know what to subtract. It stayed at 28 to 33 seconds through every experiment.
- **`purple-boot-timing`** (shipped on the image, `scripts/purple-boot-timing.sh`) for payload sizes, extent counts, disk throughput, seek latency, and SMART in one shot, plus `--menu on` to make the installed GRUB menu visible without hand-editing `grub.cfg`.
- **A visible GRUB menu splits firmware from GRUB.** If the menu appears promptly, the firmware's own device scan is not the problem.
- **Test menuentries with `console=tty2` omitted** make the initramfs messages visible, which is how we learned where the console handoff happens.

## Experiment log

Linux held at 28 to 33 seconds throughout. All times are GRUB to UI unless stated.

| # | Change | Result | Conclusion |
|---|---|---|---|
| 1 | Baseline, installed system | ~180s (originally ~5 min with the fatter pre-reinstall initrd) | Linux is 28s of it; the rest is pre-kernel |
| 2 | `purple-boot-timing` disk tests | 60.8 MB/s sequential, 21.4 ms random 4K, SMART all zeros | Drive is healthy. Not a dying disk |
| 3 | `filefrag` on kernel and initrd | 1 extent and 2 extents | Files are contiguous. Not fragmentation |
| 4 | `dd bs=4k count=20000 iflag=direct` | 20 MB/s | Drive serves small reads fine. The firmware path is ~50x slower than the hardware |
| 5 | `MODULES=dep`, rebuild initrd | 61MB to 55MB, boot roughly unchanged | Modules are not what is big. Only 516K of the initrd is modules |
| 6 | Unpack the initrd and measure it | 44MB is `/usr/lib/firmware/nvidia` in the uncompressed early cpio | Found the payload |
| 7 | Move `firmware/nvidia` aside, rebuild | initrd 55MB to 14MB, **155s** | Worth ~25s. Also broke the linear model: 59% fewer bytes bought 14% less time |
| 8 | Menuentry with `set root=(hd0,gpt2)`, no `search` | **108s** | `search` alone costs ~47s |
| 9 | Same entry, files read from the FAT ESP | **66s** | GRUB reads ext4 at 0.36 MB/s and FAT at 0.76 MB/s here |

Fitting experiments 1 and 7 gives roughly 1.6 MB/s marginal plus a ~104s fixed cost, which is what pointed at `search` as a byte-independent cost. Experiment 8 confirmed it.

## The three costs

1. **44MB of modules and firmware for hardware Purple can never use, in an uncompressed early cpio.** (Corrected 2026-08-13 after ISO forensics; the first diagnosis of this cost was wrong, see the postmortem below.) The shipped initrd's weight is `.ko.zst` modules for the `MODULES=most` set plus their firmware, dominated by network hardware: Mellanox switch firmware, NetXen 10GbE, and friends, exactly the classes the rootfs prune already removes from the image. Because these files are individually zstd-compressed, initramfs-tools stores them in an *uncompressed* cpio segment, so slow pre-kernel loaders read every byte. Every machine pays this on every boot.
2. **`search --no-floppy --label PURPLE_ROOT --set=root` costs about 47 seconds.** It enumerates and probes every block device, and the empty MATSHITA optical drive is very slow to answer under EFI. Independent of payload size, which is why it looked like a mysterious constant. It also explains the shape people notice: the menu appears fast, then a long wait after Enter, because probing starts when the entry runs.
3. **GRUB reads ext4 at 0.36 MB/s and FAT at 0.76 MB/s on this firmware.** Same bytes, same entry, same kernel arguments; only the source filesystem differed. Apple's EFI SATA path is the underlying limit (the drive itself does 20 to 60 MB/s under Linux), and the filesystem driver changes how much of that limit you eat.

Remaining floor after all three: the 14.9MB kernel costs about 20s from the ESP, plus 28s of Linux. The initrd still carries a 12MB `hwdb.bin` that is worth a few more seconds. There is no path to a 20-second boot on this hardware.

## What was ruled out, and by what

- **Dying drive**: 60.8 MB/s sequential, 20 MB/s in 4K reads, SMART PASSED with zero reallocated, pending, offline-uncorrectable, seek error, spin retry.
- **Fragmentation and seek thrash**: 1 and 2 extents.
- **Entropy starvation**: `random: crng init done` at 2.66s.
- **ATA or optical link timeouts during Linux boot**: both SATA links up at 1.92s, no resets, no `SRST failed`. (The optical drive is still implicated, but under EFI, not Linux.)
- **Apple firmware boot-device scan**: the GRUB menu appears promptly, and `BootCurrent` shows the firmware going straight to our NVRAM entry.
- **A blind framebuffer**: `fbcon: Taking over console` at 7.388s and `purple-splash.service` finished at 7.407s. The splash does paint once Linux runs.
- **Swap or memory pressure**: no swap configured, boot completes in 28s.
- **Any Purple service**: slowest is `purple-audio-dump.service` at 13.764s, which is its deliberate `sleep 12`, and it does not block `graphical.target`.
- **Initrd size as the whole story**: experiment 7 cut 59% of the bytes and saved 14% of the time.

## Two false leads worth remembering

**The garbled screen was not a rendering bug.** Horizontal stripes and leftover text appeared for minutes and looked like a GPU fault (there is even a real `nouveau ... trapped read ... PAGE_NOT_PRESENT` in the log at 24.8s). It was the pre-kernel wait wearing a different mask: the same window that used to show frozen `EFI stub` text, now showing whatever the console left behind. Its length tracked the pre-kernel time exactly.

**Forcing software GL made everything worse.** `touch /opt/purple/force-software-gl` turned a brief garble flash into minutes on screen, because llvmpipe on a 2.1GHz Core 2 Duo takes that long to paint the first frame. Removing the flag did not immediately restore a fast boot, which sent us chasing a phantom "intermittent" behavior; that was actually one boot's timing measured from a different starting point. Useful side finding: **the GL probe's choice of hardware GL is correct on this machine**, and software GL is not a safe fallback on hardware this old.

## Proposed fixes

Independent, listed by risk. Recommendation: do 1 and 2 first (180s to 108s with no layout change), then 3 on its own with its own test pass, so a boot regression is attributable.

1. **Prune the initrd of modules and firmware nothing in it can use** (IMPLEMENTED, second version: `zzz-purple-lean-initrd` initramfs hook in `00-build-golden-image.sh`). Three prunes, mirroring the rootfs prune: net-class module directories (net, bluetooth, nfc, isdn; initrds here never network-boot), `drivers/gpu` plus `firmware/nvidia` (protection for on-machine `MODULES=dep` regens, which pull in the local GPU driver and every generation's GSP blobs; removing module and firmware *together* means no card ever probes firmware-less from the initrd, and display init happens post-pivot, which `purple-wait-display` exists to absorb), and finally every firmware file that no surviving module references via `modinfo -F firmware` (firmware without its module is unloadable from the initrd by construction). Verified end-to-end against the real squashfs in the build container before shipping: **61,399,877 → 27,714,661 bytes**, artifact grep clean. There is one initrd for both boot paths (`01-remaster-iso.sh:255` copies it into `/casper/initrd`); the live path keeps working because casper's own machinery lives in the compressed main segment, untouched.

   **Postmortem: the first version of this fix shipped as a silent no-op.** It stripped nouveau and nvidia firmware, with an `lsinitramfs` verification, and the build passed, because the golden initrd never contained either (no plymouth, so no DRM modules in the initrd at all). The famous "44MB of nvidia in the early cpio" measured on the MacBook was an artifact of our own `MODULES=dep` experiment on that machine: dep-mode added the local GPU driver, which dragged the blobs in. The no-op was caught by comparing artifact sizes across builds (61,399,280 pre-fix vs 61,399,877 post-fix) and dissecting the shipped initrd with `unmkinitramfs` in the build container. Two lessons, both now enforced: verification must check for content that is *actually there when the mechanism fails* (the new check greps for net/gpu/mellanox markers, which the fat initrd demonstrably contains), and a claimed fix needs an artifact-level before/after, not a passing build.
2. **Stop searching for the root label** (IMPLEMENTED: `purple_set_root` function in the installed `grub.cfg`). Pins `set root=(hd0,gpt2)`, which is knowable at build time because the partition layout is fixed (p1 ESP, p2 root), then verifies with `[ -f /boot/vmlinuz ]` and falls back to the original `search` when the pin is wrong (extra disks can shift hd numbering). Wrong pin costs one file-existence check and behaves exactly like today; right pin skips the probe. Note there is a *second* `search` in the ESP-side `/EFI/ubuntu/grub.cfg` that finds `/boot/grub/grub.cfg` itself; it is left alone because the measured 47s came from the menuentry search, and the ESP config cannot be safely pinned at build time.
3. **Stage the kernel and initrd on the ESP at install time**, with the ext4 entry kept as a fallback menuentry. Roughly halves the remaining read time on read-bound machines. Touches boot layout, so it needs the fallback and testing on non-Mac hardware before it goes near `release/1.x`. Note Purple never updates kernels in place (new ISO, re-flash), so ESP copies going stale is not a concern here, but any install-time initrd regeneration must copy *after* it runs.

Not pursued: a unified kernel image loaded directly by firmware. It might beat 0.76 MB/s, but it reworks the signed boot chain and the ESP result already captures most of the available win.

Open question worth one test: **do other spinning-disk machines show this?** Costs 1 and 2 are not Apple-specific. If any customer machine has an HDD rather than an SSD, it is paying some version of this today.

## Hardware validation checklist for fixes 1 and 2

Status 2026-08-13, second ISO (fix 1 v2 + fix 2): **steady-state validated on the MacBook5,2 at 2:56 power-to-UI** against a ~2:50 prediction (from ~5:00 originally, 3:40 with fix 2 alone). Initrd on disk 37.2MB (vs 27.7MB in the pre-build container test; delta is module-set drift from the fresh debootstrap), lean-marker grep clean, firmware on disk intact, `purple_set_root` present, Linux 32s.

Open observation: the **first boot immediately after install took over 6 minutes**, all pre-kernel (the user journal shows sessions starting at monotonic 15.5s), with the USB stick removed. Second boot: 2:56. Same shape appeared on the previous install (3:55 then 3:40). Candidates: Apple firmware re-evaluating its boot catalog after the disk and NVRAM were rewritten, or the same unexplained boot-to-boot read-rate variance seen during the experiments (one boot measured ~3x faster than its neighbors with identical configuration). One-time and self-healing; not worth chasing unless customer-visible on other Macs. If a parent-facing mitigation is ever wanted, the install success screen could set expectations ("the first start takes a few minutes").

Per machine, on the next ISO:

1. Install, boot, time GRUB to UI. Expected on the MacBook5,2: payload drops 61.4MB to 27.7MB, so roughly 2:20 from 3:40 (with ESP staging later, roughly 1:25). SSD machines unchanged.
2. `ls -lL /boot/initrd.img` must be ~27.7MB, and `lsinitramfs /boot/initrd.img | grep -cE 'kernel/drivers/net/|kernel/drivers/gpu/|firmware/nvidia/|firmware/mellanox/'` must print 0. `ls /usr/lib/firmware/nvidia` must NOT be empty (firmware stays on disk).
3. On any NVIDIA machine: display comes up, `dmesg | grep nouveau` shows a clean post-pivot init, `/tmp/purple-gl-probe.log` unchanged from prior builds.
4. Live-boot the same stick on an NVIDIA machine (the initrd is shared with casper): display must come up the same way. Also confirm wired ethernet still works *after* boot on some machine, proving net modules load fine from the rootfs. (The image prunes net modules from the rootfs anyway, so this mostly proves nothing regressed for the devices that survive that prune.)
5. Plug in a USB stick and boot: the pin may miss (hd numbering shift), and the fallback `search` must still land in Purple. This is the fallback's regression test.
6. QEMU: `test-boot.sh --mode install` still boots the installed disk image (exercises pin + fallback on standard firmware, and the lean initrd's storage drivers on virtio/AHCI).

## Side findings (bugs found while investigating)

Fixed and shipped in `daec105`:

- **The parent menu's terminal was invisible.** `stderr_guard.hide_native_stderr()` points fd 2 at `/tmp/purple-stderr.log`, and the child shell inherits it. bash writes its prompt and readline's echo to stderr, so the shell ran fine but showed no prompt and no typing, while command output still appeared. A regression from `0a3b4d2` (2026-07-31), so any ISO built after that date has it. Fixed by handing the child the guard's dup of the real terminal.
- **Ctrl+Alt+F2 spawned a second shell on tty2.** `openvt -s -f -c 2 -- login -f purple` forced a second login onto a VT that already had an autologin agetty, so two processes read one input stream and each got a fraction of the keystrokes. Now `chvt 2`, using the shell already there.
- **`StartLimitIntervalSec` and `StartLimitBurst` were in the service section** of `purple-x11.service`, where systemd ignores them ("Unknown key name ... ignoring"). The X restart rate limit had never been in effect. Moved to the unit section.

Not fixed:

- **`purple-audio-dump.service` tops `systemd-analyze blame`** at 13.764s because of its deliberate `sleep 12`. Harmless to boot, but it misleads anyone debugging a slow boot. Worth debug-gating.
- **The installed `grub.cfg` lacks `i915.enable_psr=0 i915.enable_fbc=0`**, which every live cmdline carries. Irrelevant on this nouveau machine, but an unintended live-versus-installed asymmetry.
- **The RTC on this machine is dead**, so journal timestamps jump every boot. Nothing to fix in the image; worth knowing when reading logs from old hardware.

## Reproducing this on another slow machine

1. `sudo purple-boot-timing` for payload sizes, extents, disk throughput, seek latency, SMART.
2. `systemd-analyze` for the Linux half.
3. Wall clock minus `/proc/uptime` at first paint for the pre-kernel half.
4. `sudo purple-boot-timing --menu on`, reboot, and see whether the wait is before or after the menu appears.
5. If after: add a test menuentry with `set root=(hd0,gptN)` and no `search`, and another reading from the ESP. Those two entries separate the fixed cost from the read-rate cost.
6. `unmkinitramfs /boot/initrd.img /tmp/i && du -sh /tmp/i/*` to see what the payload actually is. The early cpio is uncompressed, so what lands there costs full size.
