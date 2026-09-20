# Chromebooks: Purple in a Third Boot Slot on ChromeOS

> Handoff from a research session on 2026-09-19. The reasoning is LLM-generated; the inventory
> section was read off a real Chromebook. Firmware and vboot claims marked **unverified** were not
> tested. This supersedes the Chromebook ordering in `mac-and-chromebook-plan.md` (which ranks
> RW_LEGACY first) and `chromebook-support.md` (which assumes MrChromebox firmware).

**This is research, not a compatibility promise.** Nothing here ships, and Purple does not claim
Chromebook support anywhere. One machine has been probed.

**Status: probe passed on one Braswell Chromebook** (display, audio, speech, keyboard; four runs
logged under "Where things stand"). The app adapters and both install stages are written but have
not run on a device yet (see "Implementation"). Still owed: the same probe unchanged on a
different board.

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

Why the other routes considered were set aside:

| Route | Why not |
|---|---|
| MrChromebox Full ROM | Needs write protect off: battery unplug, screw, or SuzyQ cable. Screws. |
| RW_LEGACY + our ISO | EOL for Skylake and older, none on ARM, and mainline-kernel audio on Chromebooks is the expensive part. Still shows the dev-mode screen. |
| Depthcharge with a mainline kernel | x86 vboot images have no initrd slot, so a custom kernel build per arch, and the same hardware problem. |
| Purple Web (Pyodide) | Needs a rewrite of the render path, no piper, and only lockable via Admin-console kiosk enrollment. |
| Purple in Crostini | Runs the real app, but needs a Google account, one VM download, and is escapable. Fallback idea, not the plan. |

The hypothesis behind the third-slot route: it reuses Google's own kernel, firmware blobs and
audio stack on the exact board, so audio, touchpad, display and sleep should need no per-board
work, on x86 and ARM, including auto-update-expired boards. Tested on one x86 board so far; ARM
is untested. Slots A and B and the firmware are never written, so a failed install should fall
back to stock ChromeOS (**unverified**).

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
- **Portability rule:** depend only on interfaces expected to be the same on every Chromebook (kernel
  KMS, evdev, CRAS, upstart, `cgpt`/`futility`). Anything tied to a board's userland (minigbm,
  Mesa, UCM layout, DSP topology) is off limits. An `if board ==` anywhere means the premise failed.
- **Display:** pygame renders offscreen (`SDL_VIDEODRIVER=dummy`) and a small libdrm layer copies
  each frame into a KMS dumb buffer. No GBM, EGL or Mesa. SDL's KMSDRM backend is dropped: it
  reported "kmsdrm not available" on the reks (see probe run 1). Chrome never starts: an upstart
  `.override` file containing `manual` for the `ui` job. Purple runs as its own upstart job with
  `respawn`.
- **Audio:** keep CRAS running and play through it (SDL's ALSA `default` device). CRAS is Google's
  per-board abstraction, and on smart-amp boards it carries the speaker protection, so bypassing it
  is a hardware-safety risk. Raw ALSA + `alsaucm` works on the reks but is the per-board path.
- **Input:** evdev as root with EVIOCGRAB, exactly as today. The grab should also keep Ctrl+Alt+F2
  from reaching frecon (ChromeOS's console), so the VT2 root shell stays out of reach
  (**unverified**). keyd as a static
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
- `wheels/`: pygame-ce 2.5.8 (not pygame, see below), numpy 1.26.4, piper-tts 1.3.0, onnxruntime 1.30.0, protobuf,
  flatbuffers, packaging. All manylinux x86_64 cp312.
- `voice/`: `en_US-libritts_r-medium.onnx` + `.json` (matches `VOICE_MODEL` in the golden image).

Build it with `scripts/chromebook/build-bundle.sh [dest]` (default `~/purple-chromebook`), which
also compiles the glibc shim and packs the app, then copy the folder to a FAT32 stick. On the
Chromebook: `sudo bash`, mount the stick, `bash <stick>/purple-chromebook/probe.sh`, and press
Ctrl+Alt+Back when told. Always `sync` and `umount` before pulling the stick.

**Probe:** `scripts/chromebook/` (`probe.sh`, `probe.py`, `f128shim.c`). The original v1
design, kept for the reasoning; the run notes below say what changed and why:

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
- pygame 2.6.1's manylinux x86_64 wheel bundles SDL 2.28.4 built without KMSDRM (checked with
  `strings` on its libSDL2). pygame-ce 2.5.8 bundles SDL 2.32.10 with KMSDRM, which dlopens the
  system `libgbm.so.1` and `libdrm.so.2`. The probe installs pygame-ce (same `import pygame`);
  the Chromebook tarball would too. Pin versions in `just` recipes: `"numpy<2"` is eaten as a
  shell redirect.
- piper 1.3.0 API used by `tts.py`: `PiperVoice.load(path)`; the production path runs a worker
  subprocess reading `wav_path\ttext` lines.

**Probe run 1 (reks, 2026-09-19, probe v1 = SDL KMSDRM, raw ALSA):**

- Display failed: `kmsdrm not available` on both device indexes, instantly, before and after
  killing frecon, so not a DRM-master problem. `libgbm.so.1` (minigbm), `libdrm.so.2`, libEGL and
  libGLESv2 are all present, and `gbm_surface_create` / `gbm_surface_lock_front_buffer` exist.
  Cause unknown; v2 logs any missing symbol for the record and does not pursue it.
- `card0` is i915, `card1` is vgem. KERN-C/ROOT-C are 1-sector placeholders. Keyboard is `event3`.
- Raw ALSA: `stop cras`, `alsaucm -c chtrt5650 set _verb HiFi set _enadev Speaker` and
  `aplay -D plughw:1,0` all returned 0, but a 1 s tone took 8 s. Whether it was audible: not noted.
- pygame.mixer on ALSA `default` with CRAS stopped hung the probe (default routes to CRAS), and
  with frecon killed the machine looked dead. The forced power-off corrupted the FAT stick.
  Lessons in v2: CRAS stays up, every command has a timeout, mixer runs in a child process, a
  300 s watchdog, frecon is killed only as a last resort and then the script reboots.

**Probe run 2 (reks, 2026-09-19, probe v2):** display OK through KMS dumb buffers; audio OK
through CRAS with `ui` stopped (aplay and pygame.mixer on ALSA `default`), raw ALSA also OK, all
four tones audible; keyboard grab OK with runtime detection. Speech failed at import:
`onnxruntime_pybind11_state...so: undefined symbol: strfromf128, version GLIBC_2.26`. ChromeOS's
glibc 2.32 is built without the `_Float128` API; onnxruntime 1.30's bundled libstdc++ references
that one symbol (every other glibc symbol it needs is <= 2.28). This is a ChromeOS-wide x86_64
trait, not a reks one, and aarch64 has no f128 variants. Fix under test: a 5-line `LD_PRELOAD`
shim (`f128shim.c` in the bundle) around the piper worker process.

**Probe run 3 (reks, 2026-09-20, v2 + shim):** speech OK with the shim: piper load 5.8 s (once,
the worker keeps it loaded), synth 1.0 s for "Hello from Purple Computer." on the Celeron N3060,
played through CRAS. Full-screen 1366x768 redraw through the dumb buffer: 7.4 ms/frame including
the copy. SDL's KMSDRM refusal explained: minigbm lacks `gbm_bo_write` (SDL's cursor path), libdrm
is complete; stays dropped. CRAS with `ui` stopped still selects the internal speaker node (volume
75) by itself. `/etc/asound.conf` routes ALSA `default` to CRAS. frecon kept DRM master for the
full 30 s with no VT switch, so the probe killed it (frecon respawns with a login prompt); whether
Ctrl+Alt+Back releases master is still **unverified**, and irrelevant once Purple is the boot job.

**Probe run 4 (reks, 2026-09-20):** all stages OK, keyboard grab saw 91 presses. The piper line
in run 3 was inaudible because it played right after `stop cras; start cras`. The dumps explain
it: a CRAS that Chrome set up marks the internal speaker active (`2*Speaker`); a CRAS started
with Chrome never running lists the node but marks nothing active (`2 Speaker`), so streams play
into nothing while every command returns 0. `cras_test_client --select_output <node>` (node found
by type `INTERNAL_SPEAKER`, not by id) makes it active again. Purple boots into exactly that fresh
state, so its startup must select the output node, unmute and set volume itself, and redo it on
headphone plug events (Chrome normally does this). Confirmed by ear: speech and tones 1 to 4
heard, tone 5 (fresh CRAS, untouched) silent, tone 6 (after select_output) heard.

**Probe v2** (dumb buffers, CRAS first, runtime discovery of DRM device, connector, sound card and
keyboards) is what `scripts/chromebook/` holds now. After the reks, run it unchanged on a newer Intel
(SOF audio, 5.x kernel), an ARM board (needs the arm64 bundle) and ideally an AMD board.

## Implementation (written 2026-09-20, nothing below has run on a device yet)

Everything in this section is **unverified** until the run notes say otherwise.

**App adapters** (all no-ops off ChromeOS):

- `purple_tui/canvas/kms.py`: the probe's dumb-buffer scanout, shared with `probe.py`.
  `PURPLE_DISPLAY=kms` makes `Gfx` draw to an offscreen XRGB surface and copy it out per dirty
  frame. If DRM master is not free after 3 s it runs `stop frecon`, then `pkill -9 frecon`.
- `purple_tui/cras.py`: picks the output node (plugged headphones, else internal speaker) at
  mixer warm-up and on CRAS's `NodesChanged` D-Bus signal (through `dbus-monitor`, reusing the
  `audio_hotplug` listener). Volume backend `cras`: CRAS steps are 0.5 dB, so the pactl-style
  cubic percent maps to `100 + 120*log10(level/100)`.
- `power_manager.py`: the poweroff command list drops commands that do not exist (no systemctl
  on upstart), and activity is reported to powerd every 20 s of use, since powerd otherwise dims
  and suspends on its idle timers with Chrome gone.
- `PURPLE_DEBUG_FLAG` moves the debug flag off the read-only `/opt`. Where `chvt` is missing, the
  emergency combo (Ctrl+\ held 3 s, or Ctrl+Alt+F2) exits Purple on a debug install.
- python-evdev comes from the `evdev-binary` wheel (needs only glibc 2.2.5). The canvas UI needs
  no Textual or rich. `LD_PRELOAD` of the f128 shim is set for the whole process tree.
- Dependency audit (2026-09-20, after `rich` and `flite` each surfaced as a silent failure on the
  device): a scan of every import (lazy ones too), subprocess call, `shutil.which` and absolute
  path outside the frozen TUI files. Python: pygame, evdev, piper (numpy, onnxruntime) and `rich`
  (`play_eval` validates markup with it inside a catch-all, so without it every Play answer fell
  back to letter blocks). Data: only `purple_tui/` and `packs/`. Tools with no ChromeOS
  counterpart: `flite` plus its voice (Quick voice says nothing), `keyd`, `xrandr` and `xterm`
  (both already gated), pactl/paplay/parecord (first-boot sound check skips itself). `install.sh`
  now ends with a dependency check that logs each of these.
- Quick voice: `build-bundle.sh` builds `flite` static (through `nix-shell -p glibc.static` where
  nix exists) and ships the golden image's `cmu_us_lnh` voice; the launcher puts `bin/` on PATH.
  Synthesis checked on the build machine only.
- Not done: keyd (grave and RightAlt remaps), brightness (the parent menu uses xrandr), the
  same-screen terminal, shill off, full lockdown. onnxruntime 1.30 tries to reach a Microsoft
  telemetry host at import; moot with no network, but worth pinning down before anything ships.

**Stage 1, `install.sh` + `purple-run.sh`:** installs under `/usr/local/purple` only (Python, the
app, voice, emoji font, a debug flag). `purple-run.sh` detaches, runs `stop ui`, starts Purple, and
on any exit copies logs to `logs/` (and the stick if mounted), then `start frecon; start ui`, and
reboots if no console came back. `PURPLE_MAX_SECONDS=120` is a safety net for first runs.

**Stage 2, `install-slot.sh`:** read-only `--check` by default; `--write` does the next phase.

1. Phase 1 shrinks the STATE entry with `cgpt` and places ROOT-C (rootfs size + 1 GiB) and KERN-C
   at the end of the disk, then reboots. ChromeOS is expected to find stateful too small, wipe it
   and set itself up again (the chrx precedent). This is the one step with real risk: a bad
   partition table needs a recovery stick. Make one first.
2. Phase 2 copies the running kernel and rootfs into slot C, runs Google's own
   `make_dev_ssd.sh --remove_rootfs_verification --partitions 6` on the copy (it repacks the
   kernel, and `PARTUUID=%U/PARTNROFF=1` in the command line should make KERN-C find ROOT-C with
   no editing), grows the filesystem, installs Purple to `/opt/purple`, comments out `start on`
   in `ui.conf` and `update-engine.conf`, and adds `purple.conf` with ui's start and stop
   conditions. KERN-C gets the top priority with one try and successful=0.
3. `purple-run.sh --job` marks the slot good only once the UI has drawn, then emits
   `login-prompt-visible` (Chrome's job normally) so the rest of the boot completes. A slot that
   never reaches the UI should not be tried again, so the machine falls back to ChromeOS.
   `install-slot.sh --chromeos` sets slot C's priority to 0.

**Open questions, in order:** (1) dumb-buffer display, and whether frecon releases DRM master on
Ctrl+Alt+Back; (2) audio through CRAS with `ui` stopped; (3) whether KERN-C priority survives leaving and re-entering dev mode;
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
