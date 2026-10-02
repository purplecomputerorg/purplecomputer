# Raspberry Pi Plan

Plan (September 2026) for running Purple on Raspberry Pi 4, Pi 400, Pi 5 and Pi 500/500+. Companion to `hardware-coverage-plan.md` (the i386 precedent this reuses) and `apple-silicon-support.md` (general ARM64 notes).

**Status: built on main (`just build-pi`), awaiting first boot on a Pi 400.** Ships on `release/1.x` too, so both UIs must run on a Pi and the build and shared-script changes need picking there (the golden-image script has diverged on 1.x, so expect adaptation, see `release-pick-adaptations.md`).

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Artifact | Separate `purple-pi-<date>.img.xz`, same pipeline and commit as the ISOs | Pi firmware boots a FAT partition with `config.txt`; none of shim, GRUB, casper or the ISO applies. The SD card is the computer, so there is no live session and no install flow. |
| Distro | Debian trixie arm64 plus `archive.raspberrypi.com` for kernel and firmware (Raspberry Pi OS's recipe, as pi-gen does it) | The i386 image already builds trixie through the same script, and the app already runs on trixie's Python 3.13. Raspberry Pi's kernel, firmware and Mesa are the best tested on these boards; its kernel hook handles chroots without `flash-kernel` workarounds. |
| Models | Pi 4 (4GB+), Pi 400, Pi 5, Pi 500/500+ from one image | Firmware picks `kernel8.img` (Pi 4 family) or `kernel_2712.img` (Pi 5 family) itself. |
| Media | SD card by default; the same image also boots from USB (default EEPROM boot order is SD, then USB) | |
| Partitions | MBR: p1 FAT boot (`/boot/firmware`), p2 ext4 system, p3 ext4 data | MBR boots on every Pi 4 EEPROM version. |
| System | Read-only: Debian's `overlayroot` package, `overlayroot=tmpfs:recurse=0` on the command line (recurse=0 keeps the data partition writable), `/boot/firmware` mounted `ro` | A Pi has no battery; the power cord is the off switch. System writes land in RAM, so a power cut can never damage the system. |
| Saved data | All of `/home/purple` and `/var/log/purple` live on p3 (`nofail`) | "Anything under home persists" is already the laptop rule, so settings, volume, PIN, time travel and future features need no Pi code. A damaged p3 still boots with defaults. |
| Clock | Nothing | No RTC and no network, so the clock restarts near the build date each boot. Time travel orders by position, not time, so only log timestamps are affected. |
| Display | X11 + modesetting, same session as the ISOs | Reuses `purple-x11.service`, xinitrc and the compositor script unchanged. |
| Power off | Pi 4 and 400 never halt; Pi 5 and 500 keep today's behavior | A halted Pi 4 stays dark until replugged, and no key wakes it. See Power below. |
| Updates | Re-flash | Same as laptops. |
| Distribution | Parents download `.img.xz` and flash with Raspberry Pi Imager ("Use custom") | Secondary section on the downloads page; the laptop instructions stay first. |

## Power

Whether a model can power back on decides everything; detect it from `/proc/device-tree/model` (Pi 5, 500, 500+, CM5 can; Pi 4, 400 can't) in `power_manager.py` so both UIs share it.

- **Can't power back on (Pi 4, 400):** idle goes to the sleep screen and then turns the display off; it never runs shutdown, so any key wakes it. Parent menu Shut Down shows "You can unplug Purple now" instead of halting. Unplugging is always safe.
- **Can (Pi 5, 500):** unchanged. The Pi 5 board button and Pi 500 power key are `gpio-keys` devices sending KEY_POWER with few keys, so `PowerButtonReader` already treats them as dedicated power buttons. Pi 500+ has an open kernel bug where the key sends no events (raspberrypi/linux#7185); the parent menu still covers it.
- No keyboard power gesture: Esc hold is taken by the parent menu, and a long hold on any key gets triggered by leaning kids.

The sleep-screen and bye-screen UI exists in both UIs, so that part is two commits (TUI first).

## Build (as built)

`just build-pi` (`--fast` for quick compression) runs `build-in-docker.sh --pi`, which runs `PURPLE_ARCH=arm64 00-build-golden-image.sh` and writes `purple-pi-<date>.img.xz` plus `.version` to `/opt/purple-installer/output/` and symlinks it into `~/isos` (`link-iso.sh`) for scp or Cyberduck.

1. **Per-image switches.** The profile block at the top of `00-build-golden-image.sh` sets `BOOT` (efi or pi), `GLAMOR`, `PIPER`, `MODULES_EXTRA`, `MODULE_CHECKS`, `SOUND_MODULE_DIR` and the boot tooling to install and verify; the body reads those instead of `PURPLE_ARCH`. GRUB/shim setup is `setup_efi_boot`, the firmware prune `prune_firmware` and the squashfs `build_live_squashfs`, moved verbatim so the amd64 and i386 paths are unchanged.
2. **Pi path.** Debootstrap trixie arm64, install the pinned `raspberrypi-archive-keyring` deb, add `archive.raspberrypi.com`, install `raspi-firmware linux-image-rpi-v8 linux-image-rpi-2712` with p1 mounted at `/boot/firmware` (the packages' hooks copy kernels, initramfs, dtbs and overlays there). `setup_pi_boot` writes `config.txt` and `cmdline.txt`, then fails the build if any file a supported board needs is missing. `populate_pi_data` seeds p3 from `/home/purple`; `publish_pi_image` xz-compresses the card.
3. **One kernel command line.** `PURPLE_CMDLINE` feeds both GRUB's `purple-cmdline.cfg` and the Pi's `cmdline.txt`, where `ro` becomes `rw` plus `rootwait overlayroot=tmpfs:recurse=0`. With `ro`, overlayroot remounts its overlay read-only for systemd to flip back, kernel 6.18 refuses ("No changes allowed in reconfigure"), and logind dies on a read-only `/var/lib`, so X gets no GPU (first Pi 400 boot). The SD card's system partition stays read-only underneath either way.
4. **`config/pi/config.txt`:** `arm_64bit=1`, `auto_initramfs=1`, `dtoverlay=vc4-kms-v3d`, `disable_splash=1`, `dtparam=audio=on` (Pi 4 jack), `dtoverlay=disable-wifi`, `dtoverlay=disable-bt`.
5. **numpy.** Marker is `platform_machine == "x86_64"`; the Pi installs `python3-numpy` from apt as i386 does. The `<2` pin exists only for old x86 CPUs (`numpy-pin.md`), and 1.x has no cp313 aarch64 wheels.
6. **Emulation.** The build container has `qemu-user-static`; `build-all.sh` registers aarch64 binfmt with the F flag (kernel-wide until the host reboots, as pi-gen does) and fails with a clear message if an existing registration lacks F. No host setup.
7. **Not yet:** release upload of the `.img.xz`, and `just flash` for SD cards (flash with Raspberry Pi Imager "Use custom" or `dd`).
8. **Debugging on a Pi.** `savelog` (Ctrl+Alt+F2) writes `purple-diag-collect`'s report to `PURPLE-DEBUG.TXT` on the boot partition, readable on any Mac or PC.

## Runtime changes

1. **`scripts/purple-wait-display.sh`:** `card_kind` treats every non-PCI card as the firmware framebuffer, and Pi GPUs are platform devices, so every Pi boot would wait the full 15s. Detect the firmware framebuffer by driver (`simple-framebuffer`, simpledrm) instead.
2. **Pi 5 GPU pick:** card0 is v3d (render only), card1 is vc4 (display), and X can grab card0 ("no screens found"). Ship Raspberry Pi OS's `99-v3d.conf` (`OutputClass`, `MatchDriver "vc4"`, `PrimaryGPU`); it matches nothing on PCs.
3. **Diagnostics:** fall back to `/proc/device-tree/model` where `/sys/class/dmi` is absent.
4. **Power:** as above.
5. **Already fine:** `is_live_boot()` is False (no `boot=casper`), so the parent menu shows "Installed on this computer" with no Install option; `purple-start-compositor` falls back glx, xrender, none (v3d exposes GL 3.1, so expect xrender).

## Risks to check on the bench

Assumed fast enough, so no spike; these are the things to watch during bench testing.

- **Drawing speed on Pi 4 at 1080p.** The canvas draws in software. Fallback: force 720p with `video=` on the command line.
- **Textual UI.** Alacritty needs GL; v3d offers GLES 3.1, which Alacritty's GLES2 renderer should accept.
- **Piper on Pi 4.** Reported at a second or two per sentence with a medium voice (Pi 5 is ~5x real time). The TTS cache helps; flite is the fallback.
- **HDMI audio.** vc4-hdmi only accepts IEC958 frames; alsa-lib's card config normally makes PulseAudio's hdmi-stereo work, but it needs hardware confirmation. HDMI audio only appears if a display is connected at boot; Pi 5/400/500 have no headphone jack (USB speakers work).

## Order

1. Profile refactor (Build 1), verified by diff.
2. arm64 image (Build 2 to 7).
3. Runtime changes.
4. Bench: every model from SD and USB; 50 random power cuts with settings and time travel intact; HDMI audio with and without speakers, USB speaker; idle and Shut Down on each model.
5. Downloads page (`~/landing`): a short Raspberry Pi section below the laptop instructions: download `.img.xz`, flash with Raspberry Pi Imager "Use custom", insert, plug in.
