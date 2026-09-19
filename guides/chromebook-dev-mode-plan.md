# Chromebooks: Purple in a Third Boot Slot on ChromeOS

> Handoff from a research session on 2026-09-19. The reasoning is LLM-generated; the inventory
> section was read off a real Chromebook. Firmware and vboot claims marked **unverified** were not
> tested. This supersedes the Chromebook ordering in `mac-and-chromebook-plan.md` (which ranks
> RW_LEGACY first) and `chromebook-support.md` (which assumes MrChromebox firmware).

**Status: probe in progress.** Inventory done on one Braswell Chromebook, stick bundle downloaded,
probe script not yet written. Pick up at "Where things stand".

---

## Goals (the user's, in priority order)

1. Run Purple on Chromebooks as easily as possible for parents. Key combos beat screws.
2. Broad, uniform compatibility beats a confusing per-model matrix.
3. Ubuntu/Debian are not required. The product is the Python UI in `purple_tui/`.
4. Lock the machine down: nothing else reachable.
5. A live-boot and a permanent-install story would be nice; willing to give up live boot.

## The decision

Run Purple on Google's kernel, in Developer Mode, from the unused third kernel/root slot
(KERN-C / ROOT-C). ChromeOS in slots A and B stays untouched and Google-signed. No firmware
flashing, no write-protect change, no case opening.

Why this beats everything else considered:

| Route | Why not |
|---|---|
| MrChromebox Full ROM | Needs write protect off: battery unplug, screw, or SuzyQ cable. Screws. |
| RW_LEGACY + our ISO | EOL for Skylake and older, none on ARM, and mainline-kernel audio on Chromebooks is the expensive part. Still shows the dev-mode screen. |
| Depthcharge with a mainline kernel | x86 vboot images have no initrd slot, so a custom kernel build per arch, and the same hardware problem. |
| Purple Web (Pyodide) | Needs a rewrite of the render path, no piper, and only lockable via Admin-console kiosk enrollment. |
| Purple in Crostini | Runs the real app, but needs a Google account, one VM download, and is escapable. Fallback idea, not the plan. |

What the third-slot route gives: Google's own kernel, firmware blobs and ALSA UCM profiles on the
exact board, so audio, touchpad, display and sleep work everywhere without per-board work; x86 and
ARM Chromebooks alike; auto-update-expired boards included; zero brick risk.

What it costs: the Developer Mode warning screen at every cold boot (see below), no universal
live stick (the kernel is per-board), and no Ubuntu on Chromebooks.

## Design

- **Install medium:** the existing Purple USB stick carries a `chromebook/` folder. PCs boot the
  stick; Chromebooks read the folder from ChromeOS, which auto-mounts USB at `/media/removable/`.
- **Userland:** a copy of Google's own rootfs (ROOT-A) placed in ROOT-C, plus a Purple tarball
  (python-build-standalone, pygame, numpy, piper-tts + voice, fonts, `purple_tui`). One tarball
  per arch (x86_64, arm64). Purple lives inside ROOT-C, not `/usr/local`, so stateful wipes never
  touch it.
- **Kernel:** the device's own KERN-A, dumped and repacked with `futility vbutil_kernel --repack`
  and a command line pointing root at ROOT-C, written to KERN-C, priority set highest with `cgpt`.
  ChromeOS kernels have no initramfs and boot `root=` directly, so no initramfs work.
- **Space:** shrink the stateful partition with `cgpt` to grow ROOT-C (the chrx trick). Either our
  script formats the new stateful or ChromeOS rebuilds it on next boot (a second ~5 min wait).
- **Display:** pygame on SDL2's KMSDRM backend, no X11. ChromeOS ships Mesa (EGL, GLESv2), libdrm
  and minigbm. Chrome never starts: an upstart `.override` file containing `manual` for the `ui`
  job. Purple runs as its own upstart job with `respawn`.
- **Audio:** either stop CRAS and drive ALSA directly after applying the board's UCM verb with
  `alsaucm` (Google's UCM files are in `/usr/share/alsa/ucm`), or keep CRAS and use its ALSA
  plugin. Decide from the probe.
- **Input:** evdev as root with EVIOCGRAB, exactly as today. The grab also keeps Ctrl+Alt+F2 from
  reaching frecon (ChromeOS's console), so the VT2 root shell stays out of reach. keyd as a static
  binary through `/dev/uinput` for the grave/RightAlt remaps.
- **Networking:** `shill` and `wpasupplicant` overridden to `manual` in ROOT-C. `update-engine`
  too, though it is moot with no network and A/B untouched.
- **Purple code touch points** (thin adapters, nothing in `canvas/`): `audio.py` volume backend
  (pactl absent on ChromeOS; the `amixer` fallback already exists), the `sudo chvt` calls in
  `input.py` (drop), the poweroff command (no systemd; `poweroff`/`shutdown` exist), cursor hiding
  without X, `audio_hotplug.py` (udevadm exists on ChromeOS). python-evdev has no wheel on PyPI
  (sdist only), so the tarball needs one built in our Docker build.
- **Sleep:** Google's `powerd` stays. Lid close = sleep should be the default power policy so cold
  boots (and the warning screen) are rare.

## The Developer Mode screen, precisely

- Shows at every cold boot. Suspend/resume skips it. Dev mode itself is permanent; only choosing
  to leave it at this screen ends it.
- Ctrl+D boots from internal disk immediately and silently. Waiting boots after ~30 s with beeps
  at roughly 20 s and 30 s (timing **unverified**). `dev_default_boot=disk` is already the default.
- The timer, the beeps and the ability to leave dev mode are GBB flags in the read-only firmware
  region, enforced by Cr50/Ti50 write protect. No `crossystem` or FWMP setting changes them.
- Leaving dev mode (Space then Enter on the old screen; "Return to secure mode" on the 2020+ menu
  UI) wipes stateful and boots whatever is Google-signed. With A/B untouched that is stock
  ChromeOS, Purple dormant. Recovery = re-enter dev mode (~5 min) and rerun the installer, or
  possibly nothing more if KERN-C's priority survives (**unverified**). No recovery stick needed.
  This is why A/B must never be re-signed with dev keys (do NOT use `make_dev_ssd.sh
  --remove_rootfs_verification` on A/B).
- Esc+Refresh+Power shows the recovery screen; harmless without a recovery stick.
- The quiet-boot tier, if ever offered: with write protect off, `set_gbb_flags.sh` on the stock
  firmware (short delay, force dev switch on, default boot disk). Smaller and safer than a full ROM.

## Parent flow (target)

1. Login screen must not say "managed by": enrolled devices are out of scope.
2. Esc+Refresh+Power (chord: hold Esc and the Refresh key, tap Power), then Ctrl+D, Enter. Wipes
   local data, ~5 min. Then Ctrl+D again at the white screen.
3. At the ChromeOS welcome screen: plug in the stick, Ctrl+Alt+Forward (top-row right-arrow key,
   F2 position), login `chronos` (no password), `sudo bash`, run one script from the stick.
4. Script checks board/arch/version, shrinks stateful, copies ROOT-A to ROOT-C with overrides and
   Purple, repacks the kernel into KERN-C, sets priority, reboots. ~10 min total, no internet.
5. Every boot afterward: white screen, Ctrl+D (or wait 30 s).

## Inventory: Lenovo "reks" (read off the device 2026-09-19)

- `CHROMEOS_RELEASE_BOARD=reks-signed-mp-v4keys`, ChromeOS 14268.67.0 (M96, 2021, past AUE so it
  will not update under us). Braswell, x86_64. Kernel `4.19.208`. glibc 2.32 (Gentoo).
- Present: `cgpt`, `futility`, `crossystem`, `alsaucm`, `amixer`, `aplay`. Absent: python, ldd.
- `/dev/dri`: `card0`, `card1`, `renderD128` (one is i915, the other likely vgem; the probe must
  try both via `SDL_KMSDRM_DEVICE_INDEX`). `/dev/uinput` exists.
- `/usr/lib64`: libEGL, libGLESv2, libasound, libdrm present. **libgbm not yet checked** (the grep
  had a typo); run `ls /usr/lib64 | grep -i gbm`.
- Audio: card 0 HDA Intel PCH (HDMI only), card 1 `chtrt5650` (devices 0 and 1, Deep-Buffer).
  `/usr/share/alsa/ucm` exists with many entries; **check** `ls /usr/share/alsa/ucm | grep -i cht`.
- Input: "AT Translated Set 2 keyboard" (i8042), Elan Touchpad, Lid Switch, Power Button,
  chtrt5650 Headset jack.
- 3.9 GB RAM. Stateful `/dev/mmcblk0p1` 11 GB, 9.6 GB free. `/usr/local` is
  `ext4 (rw,nodev,noatime,seclabel,discard)`: writable and executable, on stateful.
- Verdict: viable, and a good floor test because the kernel is old.

## Where things stand

**Done:** dev mode enabled on the reks, root shell reached, inventory above.

**Stick bundle** (~280 MB of downloads, keep it outside the repo; build it fresh on whatever
machine you are on):

- `python-x86_64.tar.gz`: python-build-standalone cpython 3.12.x, x86_64 linux-gnu,
  install_only_stripped (glibc 2.17 floor). 3.12.14+20260901 was the latest on 2026-09-19.
- `wheels/`: pygame 2.6.1, numpy 1.26.4, piper-tts 1.3.0, onnxruntime 1.30.0, protobuf,
  flatbuffers, packaging. All manylinux x86_64 cp312.
- `voice/`: `en_US-libritts_r-medium.onnx` + `.json` (matches `VOICE_MODEL` in the golden image).

Build it with (also fetch the `.onnx.json` next to the `.onnx`):

```
just python -m pip download --only-binary=:all: --platform manylinux2014_x86_64 \
  --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --python-version 3.12 \
  --implementation cp --abi cp312 --abi none -d wheels "pygame==2.6.1" "numpy<2" "piper-tts==1.3.0"
gh api repos/astral-sh/python-build-standalone/releases/latest --jq '.assets[].name' | grep 3.12 | grep x86_64-unknown-linux-gnu
curl -fsSL -o voice/en_US-libritts_r-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx
```

**Not done:** `probe.sh` and `probe.py`. Design:

- Stick is FAT/exFAT (no exec bits, no symlinks), so `probe.sh` copies the bundle to
  `/usr/local/purple-probe`, untars Python there, then
  `python3 -m pip install --no-index --find-links wheels pygame numpy piper-tts`.
- Must run as root (`sudo bash`). Log to the stick dir and to `/usr/local/purple-probe/probe.log`,
  so results survive losing the terminal. Stop at first failure.
- Steps: inventory dump (incl. gbm, ucm listing, `cgpt show`), `stop ui`, then one pygame process
  that does display + sound + speech + keyboard together, the way Purple does:
  `SDL_VIDEODRIVER=kmsdrm`, try `SDL_KMSDRM_DEVICE_INDEX` 0 then 1, `set_mode((0,0), FULLSCREEN)`,
  draw text, flip loop with ms/frame; `stop cras`, apply UCM (`alsaucm -c chtrt5650 list _verbs`,
  `set _verb HiFi set _enadev Speaker`), play a tone via `aplay` and via pygame.mixer
  (`SDL_AUDIODRIVER=alsa`, try `default` then `plughw:1,0`), log `amixer -c 1 scontrols`; piper
  synth one line to wav and play it; open the i8042 keyboard from `/proc/bus/input/devices`, raw
  `struct` reads with EVIOCGRAB (no python-evdev on the probe), log keys for 10 s.
- Finish with `start cras`, `start ui`.
- **DRM master caveat:** after `stop ui`, frecon (the console you are typing in) may hold DRM
  master and block SDL's modeset. Plan: run the probe with `setsid nohup ... &`, retry `set_mode`
  for ~30 s while the user presses Ctrl+Alt+Back (frecon should release master on its VT1). If it
  still fails, kill frecon and retry; the log on the stick is then the only output and a reboot
  brings the terminal back. Whether frecon releases master this way is **unverified**.
- pygame's manylinux wheel is believed to bundle SDL2 with KMSDRM enabled (works on Raspberry Pi
  via pip); the probe logs `pygame.display.get_driver()` and the error text if not.
- piper 1.3.0 API used by `tts.py`: `PiperVoice.load(path)`; the production path runs a worker
  subprocess reading `wav_path\ttext` lines.

**Open questions, in order:** (1) pygame on KMSDRM against this Mesa/minigbm and a 4.19 kernel;
(2) which audio path; (3) whether KERN-C priority survives leaving and re-entering dev mode;
(4) keyd static build over uinput; (5) minimum kernel version to support; (6) arm64 tarball
(pygame, numpy, python-build-standalone have aarch64 builds; piper needs checking).

## References

- ChromiumOS developer mode and `dev_default_boot`: https://www.chromium.org/chromium-os/developer-library/guides/device/developer-mode/
- vboot kernel packing (`futility vbutil_kernel`): https://www.chromium.org/chromium-os/developer-library/reference/kernel/kernel-configuration/
- chrx (stateful shrink precedent): https://github.com/reynhout/chrx
- Chromebrew (proof that `/usr/local` on stateful is a working userland in dev mode): https://github.com/chromebrew/chromebrew
- MrChromebox GBB flags and write protect (quiet-boot tier only): https://docs.mrchromebox.tech/docs/firmware/wp/
- python-build-standalone: https://github.com/astral-sh/python-build-standalone
- Prior repo thinking: `mac-and-chromebook-plan.md`, `chromebook-support.md`.
