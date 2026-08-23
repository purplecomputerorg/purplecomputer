# Hardware Coverage Plan: 32-bit EFI, T2 Macs, and 32-bit CPUs

Findings and plan (August 2026) for booting Purple on three hardware classes the current ISO can't reach, plus the ISO size work that makes room for them. Companion to `t2-mac-support.md`, `secure-boot.md`, and `usb-boot-reference.md`.

**Status (August 2026): built, on branch `expanded-laptops`.** The plan below is kept as the rationale; the "As built" section at the end records where each piece landed and where the build deviated from the plan.

## The three classes

"32-bit" hides two different problems, and T2 is a third. Ranked by devices unlocked per week of work:

| Class | Examples | What breaks today | Fix | Effort | Ongoing cost |
|---|---|---|---|---|---|
| 32-bit UEFI, 64-bit CPU | 2006-2008 Core 2 Duo MacBooks (MacBook2,1 to 4,1), Bay Trail tablets | No `BOOTIA32.EFI`, firmware can't run our 64-bit loader, USB never appears as bootable | Add an ia32 GRUB next to the signed chain | 1-2 days | None, same build |
| T2 Macs | 2018-2020 MacBook Air and Pro, Mac mini 2018 | Keyboard, trackpad, audio need the `apple-bce` driver; stock kernel lacks it | Ship a second, t2linux kernel; GRUB picks it by SMBIOS model | 1-2 weeks | Pinned third-party kernel, revisit per image |
| 32-bit CPU | Core Duo/Solo Macs (2006), Pentium M, Atom N270/N280 netbooks | Everything: no 64-bit mode at all | Separate Debian i386 payload, install-only | ~2 weeks | Second distro, second test matrix |

Out of scope, unchanged: Chromebooks (`chromebook-support.md`), Apple Silicon (`apple-silicon-support.md`), 4GB-SSD netbooks (below the 16GB install minimum in `install.sh`).

T2 likely unlocks more real machines than true 32-bit: a 2019 Air in a drawer is far more common than a 2008 Eee PC, and a much better Purple machine.

## Architecture: two axes, one grub.cfg

The firmware decides which GRUB binary it can execute. The hardware decides which payload that GRUB boots. Every entry point reads the same config.

```
FIRMWARE AXIS (entry point)
  /EFI/BOOT/BOOTX64.EFI    signed shim -> GRUB        64-bit UEFI, Secure Boot intact   exists
  /EFI/BOOT/BOOTIA32.EFI   unsigned i386-efi GRUB     32-bit UEFI                       new
  MBR + El Torito          i386-pc GRUB               legacy BIOS                       exists
                                   |
                             one grub.cfg
                                   |
HARDWARE AXIS (the router)
  no long mode   ->  i386 kernel + installer initrd  ->  installs Debian i386 image   new
  T2 model       ->  t2 kernel + t2 initrd           ->  same squashfs                new
  otherwise      ->  stock signed kernel             ->  same squashfs                exists
```

### The router

Replaces the apology in `prepend_longmode_guard()` (`build-scripts/01-remaster-iso.sh`) with a decision. Verified in QEMU with GRUB 2.12 against faked SMBIOS:

```
insmod cpuid
insmod smbios
insmod regexp
set product=unknown
set purple_boot=stock
if cpuid -l ; then
    smbios --type 1 --get-string 0x05 --set product
    if regexp '^(MacBookPro1[56]|MacBookAir[89]|Macmini8|iMacPro1|iMac20|MacPro7),' "$product" ; then
        set purple_boot=t2
    fi
else
    set purple_boot=i386-installer
fi
```

| QEMU | Decision |
|---|---|
| `-cpu pentium3` (no long mode) | `i386-installer` |
| `MacBookAir9,1`, `MacBookPro16,1`, `Macmini8,1`, `iMac20,2` | `t2` |
| `MacBookPro14,1` (2017, T1), `MacBookPro11,3` (2013) | `stock` |
| ThinkPad `20AMS3RH00` | `stock` |

QEMU needs commas in the product string doubled: `-smbios type=1,product=MacBookAir9,,1`.

Properties that matter:

- **Fails safe.** If `smbios` is unavailable or refused, `product` stays `unknown` and the signed stock kernel boots. Every failure path lands on the branch that works today.
- **The whitelist can't go stale.** T2 is a closed set of eight model families; Apple stopped making them. Apple Silicon identifiers (`MacBookAir10,1`, `MacBookPro17,1`) fall outside the regex.
- **Modules already ship.** `cpuid.mod`, `smbios.mod`, `regexp.mod` are on the current ISO in both `x86_64-efi` and `i386-pc`. Still to confirm: that Canonical's signed `grubx64.efi` permits `smbios` under Secure Boot lockdown (run `test-boot.sh` with OVMF and SB on). Either answer is safe, see above.
- **Installed systems route too.** Both amd64 kernels live in the golden image and the same snippet goes into the installed grub.cfg, so a T2 Mac keeps its kernel after install. One snippet file, sourced into both configs.
- **Regression test.** Save the QEMU matrix above as a sibling of `scripts/preview-grub-guard.sh`.

### Why two kernels, not one patched kernel

`t2-mac-support.md` suggests a single patched kernel for everyone. The driver side of that is true (`apple-bce` is a no-op without a T2). The boot chain side is not: Purple boots Canonical-signed shim, GRUB, and kernel (`secure-boot.md`). The t2linux kernel is unsigned. Make it the only kernel and every Secure Boot machine we support today (Surface, HP, Dell) stops booting.

Two kernels dissolves this, helped by a structural fact: a T2 Mac cannot boot Linux at all until Startup Security Utility is set to No Security. So the machines that need the unsigned kernel are exactly the machines where signature enforcement is already off, and the signed kernel stays the default for everyone else.

## ISO size: measured, not estimated

The three features add roughly 1.1GB. The current ISO is 5.8GB, mostly dead weight, and two cheap cleanups more than pay for all of it.

### Where 5.8GB goes (`purple-installer-20260814.iso`)

| Path | Size | Notes |
|---|---|---|
| `/purple/purple-os.img.zst` | 3.7GB | 8GB raw golden image, zstd -19 |
| `/pool/` | 1.5GB | Ubuntu Server's apt repo: nvidia 470/535, a 480MB linux-firmware deb, LLVM. Unreferenced; the subiquity installer that used it was replaced by our squashfs |
| `/casper/` | 1.0GB | squashfs 910MB + kernel + initrd |
| everything else | 11MB | |

### Finding 1: 2.8GB of every golden image is deleted-file residue

`filesystem.size` says the OS is 1.81GB of content and squashfs compresses it to 910MB. The golden image holds the same files yet compresses to 3.44GiB. Measured on the shipped image:

```
dumpe2fs on the root partition:
  Block count  1,965,568  (8.05GB)
  Free blocks  1,467,946  (6.01GB)
  Used                     2.04GB

zstd -19 -T0 (the build setting):
  root partition as shipped                 3.69GB
  same partition, free blocks zeroed        0.90GB   (e2image -ra, equivalent to zerofree)
```

The build creates the image from `/dev/zero`, then installs the full `linux-firmware` (~1GB), gcc, make, python3-dev, pip caches and apt archives, and prunes or purges them (`00-build-golden-image.sh`, firmware prune, `:471`, `:995`). Each removal frees blocks without clearing them; zstd faithfully compresses the garbage. Nothing in the build zeroes free space.

Why prior size work missed it: `4128444`, `6c79598`, `9d8f84a` all targeted what's installed, and the tools for that (`du`, `df`, `dpkg`) read the live filesystem, which honestly reports 2GB used. The residue is invisible from inside the filesystem and shows only as a compression ratio.

Fix, before the root unmount, no new dependencies (`zerofree` isn't in the build container):

```bash
# Zero freed blocks so deleted build artifacts don't ship inside the zstd image
dd if=/dev/zero of="$MOUNT_DIR/.zero-fill" bs=1M status=none 2>/dev/null || true
sync; rm -f "$MOUNT_DIR/.zero-fill"
```

Install is unchanged (dd still writes 8GB; zeros decompress trivially). Every `flash-all` stick writes 2.8GB less, and verified-flash hashing speeds up in proportion.

### Finding 2: `/pool` and `/dists` can go

Drop them in `01-remaster-iso.sh` next to the squashfs cleanup (line ~224). Casper never reads them. Verify with `test-boot.sh`.

### Budget after cleanup plus all three features

| Component | Today | After |
|---|---|---|
| amd64 golden image | 3.7GB | ~1.25GB (zeroed, plus t2 kernel) |
| casper (squashfs, 2 kernels, 2 initrds) | 1.0GB | ~1.15GB |
| `/pool` | 1.5GB | 0 |
| `BOOTIA32.EFI` | 0 | 5MB |
| 32-bit payload (i386 image + kernel + installer initrd) | 0 | ~0.75GB |
| **Standard ISO** | **5.8GB** | **~3.2GB** |
| **With-backup ISO** | **9.3GB** | **~4.5GB** |

Without the cleanup: 6.9GB / 10.6GB, which rules out 8GB sticks and squeezes 16GB. Guardrail to keep: ISO9660 files over 4GB need xorriso ISO level 3; the image sits at 3.7GB today, so the build should assert the limit.

## Per-class notes

### BOOTIA32.EFI

- Build with `grub-mkstandalone -O i386-efi` and every needed module embedded (cpuid, smbios, regexp, search, iso9660, fat, linux...). The ISO has no `/boot/grub/i386-efi/` tree and the signed ia32 chain Canonical doesn't ship can't be borrowed. Package: `grub-efi-ia32-bin` in the golden image, next to `grub-pc-bin`.
- Same binary on the installed ESP via `--target=i386-efi --removable --no-nvram` in `install.sh`, mirroring the Layer 6 `i386-pc` call.
- A 64-bit kernel booted from 32-bit firmware (`CONFIG_EFI_MIXED`, on in Ubuntu) has no 64-bit EFI runtime, so `efibootmgr` fails. Already handled: `install.sh` treats the NVRAM entry as Layer 4 bonus and these Macs boot `/EFI/BOOT/` anyway.
- The ia32 GRUB runs the router too: Core 2 Duo with 32-bit EFI takes `stock`, Core Duo takes `i386-installer`.
- Secure Boot on 32-bit UEFI (some Bay Trail tablets) has no signed chain; document "turn Secure Boot off". The 2006-2008 Macs have no Secure Boot at all.
- Test: 32-bit OVMF in QEMU, then a 2007 MacBook (about $40 used).

### T2

- **Use the prebuilt kernel, don't patch.** `t2linux/linux-t2-patches` is 24 patches: the BCE stack (2), a core ACPI early-CPU-offlining change, applesmc fan control (9), i915/amdgpu quirks, trackpad HID. Download `linux-image-<ver>-t2-noble_amd64.deb` from `t2linux/T2-Debian-and-Ubuntu-Kernel` releases at build time (111MB, noble builds published within days of upstream). Pin version and sha256 in the script, same treatment as the signed EFI blobs.
- **Pinning is a feature.** Purple ships whole images with no OTA, so the t2 kernel can't drift under a shipped stick. "Ongoing dependency" means "revisit when cutting a new image".
- **Kernel skew.** t2 kernel is 6.18 against noble's 6.8 and a 2024 `linux-firmware`. The Ice Lake Air (`MacBookAir9,1`) needs i915 DMC firmware, the 15"/16" Pros need amdgpu blobs. Newer kernels fall back through older firmware names, but verify on the bench. Firmware pruning keeps `i915/` and `amdgpu/`; the networking-module prune and `modprobe --dry-run` check must run against both kernel trees.
- **Audio needs UCM configs.** t2linux's `apple-t2-audio-config` ships ALSA UCM profiles; without them the device appears and pulseaudio has no working profile. The guide doesn't mention this.
- **Two initrds.** Casper's initrd is kernel-specific; `01-remaster-iso.sh` extracts two kernel/initrd pairs. `apple-bce` is in-tree in the t2 kernel, so udev autoloads it by modalias; no initramfs module list needed unless bench testing says otherwise.
- **4K-sector SSD.** Already handled: `install.sh` rebuilds the GPT for the real sector size, proven on 2016/2017 TouchBar Macs.
- **Esc key.** Touch Bar Pros have no physical Esc but do have grave/tilde, which keyd already maps to Escape at the kernel level.
- **Needs hardware.** QEMU can only confirm the t2 kernel boots on a generic VM. Budget one 2018-2020 MacBook Air.

### 32-bit CPU

- **Install-only, no live session.** Casper is Ubuntu-only with no i386 build, and porting the live hooks, `install-sources.yaml`, the `13swap` neutering and the reboot flow to Debian `live-boot` was most of the estimated cost. Skipping live boot removes it. The boot path is a Debian i386 kernel plus a small installer initramfs (~50-80MB): Purple-branded confirm screen, dd the image, `grub-install`, reboot into a native install. On an Atom with 1GB RAM this is a better experience than running off USB2 with a RAM overlay.
- **Payload stays on the ISO.** GRUB loads the i386 kernel and initrd off the ISO; the initrd mounts the ISO9660 filesystem (`isofs` + `usb-storage`) and reads `purple-os-i386.img.zst`. No partitioned-stick format, no changes to `flash-all`, settle tests, Etcher, or verified-flash hashing. An earlier draft of this plan wrongly assumed a stick-format change.
- **One install path.** `install.sh` reads its image from `PURPLE_PAYLOAD_DIR`, so the installer initrd carries bash, zstd, parted, e2fsprogs and runs the existing script pointed at `/cdrom/purple32/`.
- **Base: Debian 12 bookworm i386.** Same systemd, so `purple-x11.service`, the boot-log heartbeat, and the shutdown watchdog port nearly unchanged. Debian 13 dropped i386 kernels; bookworm is supported to June 2028 with no successor. Alpine keeps x86 longer but is musl plus OpenRC, and every unit file and binary wheel diverges. Not worth it.
- **Python 3.11.** bookworm ships 3.11.2; `pyproject.toml` targets py312. Run the test suite under 3.11 once before committing; any 3.12-only syntax has to go.
- **Wheels.** pygame has i686 wheels, evdev compiles, textual/rich/wcwidth are pure Python. numpy has no cp311 i686 wheel: use Debian's `python3-numpy` (1.24, inside the `<2` pin). onnxruntime has never shipped i686, so Piper is out.
- **Voice.** `tts.py` needs an espeak-ng backend. Today `_get_piper_voice()` failing means silence with no fallback, so this is also the missing amd64 fallback.
- **Screen.** `REQUIRED_TERMINAL_COLS` (146) × 37 rows fits 1024x600 at 11pt; `font_sizer.py` auto-shrinks to `MIN_FONT = 8.0` at runtime. Only `scripts/calc_font_size.py` has the 12pt floor. Legibility question, not a layout rewrite.
- **GL.** `purple-gl-probe` already falls back to software GL (6-7% of a core on an HP Stream), so GMA950-class GPUs are covered.
- **Arch branches live in the build scripts only**, plus TTS engine selection. No arch conditionals in the app.
- **Entirely QEMU-testable.** `-cpu pentium3` exercises the router, the installer, the install into a virtual disk, and the reboot into the installed system, headless.

## Sequencing

1. **Zero free blocks, drop `/pool`.** Half a day. Every later build, flash, and test gets faster; report before/after sizes.
2. **Router + BOOTIA32.** A couple of days, QEMU-verifiable. Harmless with one kernel (always picks `stock`). Unlocks 2006-2008 Macs and Bay Trail.
3. **T2.** Gated on bench hardware.
4. **32-bit payload.** No hardware dependency, can run alongside T2.

All four are features, so they land on main and ship in a new ISO rather than via `release-pick`.

## Open questions

- Does Canonical's signed GRUB allow `smbios` under Secure Boot lockdown? (Safe either way; decides whether T2 detection works on a T2 Mac that someone re-enabled Secure Boot on, which can't boot Linux anyway.)
- Which stick capacities ship today? Decides whether the with-backup variant needs the cleanup before any feature lands.
- Any support emails from the "Purple does not support this computer" screen? Real counts for the 32-bit CPU class would confirm or kill step 4.

## As built

One variable does the routing. `config/grub/purple-router.cfg` sets `purple_variant` to `""`, `-t2` or `-i386` (plus `purple_args`, the T2 kernel parameters `pm_async=off intel_iommu=on iommu=pt`), and every menuentry on the ISO boots `/casper/vmlinuz$purple_variant` with `/casper/initrd$purple_variant`. The installed grub.cfg sources the same file and boots `/boot/vmlinuz$purple_variant`. The installed grub.cfg falls back to the stock kernel when the routed file is missing (the i386 image has no `vmlinuz-i386`; installed kernels are always the right arch). `scripts/test-grub-router.sh` runs the QEMU matrix above; `scripts/preview-grub-guard.sh` still renders the "too old" screen, which now only appears when the i386 payload is missing (fast builds skip it).

GRUB script gotcha: `if insmod cpuid && ! cpuid -l` routed every 64-bit machine to `-i386` in QEMU. Nested `if`s behave; keep them.

| Piece | Where |
|---|---|
| Zero free blocks | `00-build-golden-image.sh`, after the squashfs, before unmount |
| Drop `/pool`, `/dists` | `01-remaster-iso.sh`, step 4 |
| BOOTIA32.EFI | `grub-mkimage -O i386-efi -p /EFI/ubuntu` in `00-build-golden-image.sh`, on both the golden ESP and (via `signed-efi/`) the ISO's EFI image. Same prefix as Canonical's signed GRUB, so it reads the same `/EFI/ubuntu/grub.cfg`. Every needed module is built in: once that config points `$prefix` at a device with no `i386-efi/` tree, nothing else can load, and a failed `insmod cpuid` would route a 32-bit CPU to the amd64 kernel |
| T2 kernel | `install_pinned_deb` in `00-build-golden-image.sh`: `linux-image-6.18.45-1-t2-noble` and `apple-t2-audio-config` 0.5.2, sha256-pinned. dpkg's postinst builds the initrd through the lean hook; the remaster extracts both kernel pairs from the squashfs and patches both initrds |
| i386 image | `PURPLE_ARCH=i386 ./00-build-golden-image.sh` (run by `build-all.sh` after the amd64 image, skipped on fast builds). Same script, Debian trixie i386 (bookworm has no alacritty) with bookworm's `linux-image-686` pinned in (trixie has no i386 kernel). `requirements.txt` skips numpy and Piper on i686 via PEP 508 markers; Debian's `python3-numpy` (2.x, built for the i686 baseline, so the SSE4.2 problem behind `numpy-pin.md` doesn't apply) fills in. No casper. Output under `build/i386/` |
| i386 installer | No custom initrd: initramfs-tools boot script `build-scripts/initramfs/purple-install` (`boot=purple-install`) mounts the stick by label, asks for YES, runs the ISO's own `install.sh` with `PURPLE_PAYLOAD_DIR=/cdrom/purple32`, reboots. The hook next to it adds bash, zstd, pv, parted, util-linux, e2fsprogs and `grub-install` with `i386-pc`, only when `PURPLE_INSTALLER_INITRD=1` |
| Voice on i386 | `tts.py` falls back to `espeak-ng` when Piper is absent (also the missing amd64 fallback) |

Two traps found in QEMU, both in the installer initrd: the busybox hook runs before ours and `copy_exec` skips files that exist, so busybox's `dd`/`blkid`/`wc` applets shadowed the real ones (busybox `wc -c` wraps at 32 bits, which turned the 8GB write into `WRITE_SIZE=0` and an instant SHA mismatch). The hook now removes the applet links first.

Still open: bench-test the T2 kernel on a 2018-2020 Air (display firmware, audio profile, `apple-bce` autoload), BOOTIA32 on a 2006-2008 MacBook, and the i386 installer on an Atom netbook. All three paths are QEMU-verified only as far as QEMU can go.
