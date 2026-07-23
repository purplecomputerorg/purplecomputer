# Intel Display Tuning: the Checkerboard Artifact

The "checkerboard" is a **present-path tear**, not a transparency or compression bug. The fix is a **vsync compositor (picom)**. This guide is the full story, including two earlier theories that turned out wrong, so nobody re-walks them.

Part of the boot display story: see `boot-display-sequence.md` for the full power-on to TUI sequence and the GPU readiness wait.

---

## TL;DR (the resolution)

On old Intel MacBooks, transitions flash a brief checkerboard. We tried, in order:

1. `i915.enable_psr=0 i915.enable_fbc=0` on the kernel cmdline. **Correct to keep, but not the fix** (disabling compression can't fix a tear). Verified live: both read disabled.
2. `Option "TearFree" "true"` on the modesetting driver. **A no-op: the modesetting driver has no TearFree option** (only the `intel`/`amdgpu`/`ati` DDX drivers do). It silently logged `Option "TearFree" is not used` and did nothing, on every machine.
3. Forcing all backgrounds opaque. Correct (a real, separate modal bug), but unrelated to this.

The actual cause: with `modesetting`, partial-damage updates are blitted straight to the scanout buffer, so during a transition the panel scans out a frame that is part old-content, part new-content. That mixed frame, with compression-block residue at the boundaries, is the checkerboard. The fix is **whole-frame, vsync'd presentation**, which `modesetting` only gets from a compositor. We ship `picom` (`config/picom/picom.conf`, launched by `scripts/purple-start-compositor.sh` from `xinitrc`).

## The Symptom

Changing a few cells' colors, or swapping screens, flashes a brief 2-color checkerboard during the transition, then settles to a correct frame. Clearest repros: pressing left/right in the music room (the per-column "wavefront" key-shift animation), and the power-button confirm screen appearing over a room (you momentarily see *both* screens at once). The two checker colors are always the old frame's color and the new frame's color.

That last detail is the tell. A checker that mixes the **old and new frame** along a moving boundary is a torn present, not a static panel effect.

## What It Is, and Three Things It Is Not

**Not transparency.** Easy to confuse, because there was a real, separate alpha bug: commit `8fe4ca5` removed a genuine 60% alpha from Textual's `ModalScreen` and `tests/test_no_alpha_backgrounds.py` keeps backgrounds opaque. But the music grid and the shutdown screen both render fully opaque (`MusicGrid.render_line()` writes solid `bgcolor`; `ShutdownConfirmScreen` has `background: $background`, pushed with no transition animation). So a *composed* frame can never contain both screens, yet the panel shows both. And it **settles** after the flicker, content can't settle; only a panel re-scan can. Both facts place it after rendering, at scanout.

**Not panel dither.** A plausible Skylake theory was a 6-bit panel dithering 8bpp content (FRC), recomputed per color change. Ruled out on the actual hardware: the diagnostic reported `max bpc: 12`, not a forced-6-bit panel. And dither is computed per static color, it would never blend the previous frame's color with the new one along a moving wipe.

**Not FBC/PSR alone.** FBC (framebuffer compression) and PSR (panel self-refresh) are real partial-update glitch sources on this Haswell-through-Skylake hardware, and we keep them disabled. But they are not *the* cause here: the artifact persisted with both verified off, because the underlying problem is the torn present, not the compression. The compression-block grid only shapes *how* the tear looks (blocky vs smooth).

It survives `LIBGL_ALWAYS_SOFTWARE=1` because that only changes how Alacritty rasterizes, not how the X server presents to the panel.

## The Fix: a vsync compositor

`modesetting` is the right driver for Purple (chosen to avoid legacy-DDX I/O-port problems, see `config/xorg/10-modesetting.conf`), but it has no TearFree. It page-flips full-window updates via the Present extension, but a TUI sends *partial* damage (a few changed cells), which `modesetting` blits directly to the scanout buffer with no vsync, hence the tear.

A compositor fixes the whole class at the layer it shares. `picom` redirects every window into an offscreen buffer and presents the composited result on the vblank, so the panel only ever scans out a complete, consistent frame. It is driver-agnostic (helps any future tearing on AMD/PC targets too) and degrades safely (`scripts/purple-start-compositor.sh` is guarded: if `picom` can't start, the session continues uncomposited, never a black screen).

**Boot cost, and why the launch waits for the UI.** `picom`'s glx context init is its slowest step. On the oldest Intel target (a 2-core Skylake, the only machine slow enough to notice) that init contends with the Python/Textual/pygame import + first-paint crunch (the "Loading..." phase, printed before `App().run()`) and the squashfs->tmpfs copy, stretching time-to-interactive by up to ~1s. It's a one-time boot cost, not a steady-state slowdown (composited present adds one vblank, invisible for a TUI).

The fix is to start picom *after* that crunch, but a fixed `sleep` would just be guessing where the crunch ends, and it ends at different times on different hardware. Instead the app touches `UI_READY_MARKER` (`/tmp/purple-ui-ready`) from `call_after_refresh` in `on_mount`, i.e. once the first frame has painted, and `xinitrc` waits for that marker (backgrounded, bounded ~15s with a fallback start so a missing marker never strands us uncomposited) before launching. The marker tracks the real end of the crunch on any machine. The tear only ever shows on user-driven transitions, which can't happen that early, so waiting is free. Trade-off: starting after the TUI has settled means picom's one-time window-redirect repaint is a brief visible flash on the home screen instead of being hidden in the boot churn.

`purple-start-compositor` is idempotent (it exits early if a picom is already running): a Purple restart re-execs `xinitrc`, but picom is reparented and survives, so the restart finds it up and leaves it alone, no needless relaunch or flash. To force a restart (debug A/B), `pkill -x picom` first.

We start everywhere rather than hardware-gating: waiting for the UI makes the cost ~free on fast machines, and gating would add DMI/i915 detection without helping the one machine that's actually slow. This is identical on live-boot and installed systems: both run the same `.xinitrc` and the same golden-image picom/launcher/config.

Two things that matter in `config/picom/picom.conf`:

- **`unredir-if-possible = false`** is mandatory. Alacritty runs fullscreen, and picom's default is to *unredirect* fullscreen windows for performance, which hands Alacritty straight back to the tearing scanout path and undoes everything. Keep it redirected.
- **Hardware GL for the compositor, independent of the session.** The launcher starts picom with `LIBGL_ALWAYS_SOFTWARE=0` so the *compositor* uses the real GPU (glx backend) for fast vsync, with an `xrender` fallback for VMs / machines where hardware GL is unavailable. Alacritty's GL mode is decided separately by `purple-gl-probe` (next section).

## Software GL for Alacritty: History and Revisit Criteria

The session decides Alacritty's GL mode at startup via `purple-gl-probe` (`scripts/purple-gl-probe.sh`): hardware GL when a real GPU driver verifiably works, `LIBGL_ALWAYS_SOFTWARE=1` (llvmpipe) otherwise. picom composites with hardware GL independently (above). How we got here:

- **Dec 2025 (`7671ac6`):** modesetting + glamor, hardware GL everywhere.
- **Mar 14, 2026 (`0a540cc`):** switched Alacritty to software GL, dropping the glamor option in the same commit. Rationale: works on any GPU, no driver/firmware dependencies, and the assumption that for a TUI the cost is invisible. That assumption was never measured.
- **Mar 15, 2026 (`4128444`):** the context. Aggressive firmware pruning (~400MB) and a minimal X stack meant Alacritty startup could not depend on whatever GPU support survived, on unknown parent hardware or in GPU-less QEMU/UTM VMs.
- **Jun 2026 (`bfd7593`):** picom deliberately gets hardware GL with a guarded fallback (glx, then xrender, then uncomposited). Every real machine has exercised hardware GL since, without incident.
- **Jul 2026 (`c5ea550`):** radeon firmware shipped back into the image, so the pruning fear was legitimate at least once.
- **Jul 23, 2026:** measurement finally happened, on both ends of the hardware spectrum. HP Stream 11 (Celeron N3060): alacritty 62-75% of a core with software GL, 6-7% with hardware. Surface Laptop (i5-7200U, fanless): 114.7% avg vs 3.1%, and the llvmpipe load kept package power maxed so the firmware power-capped the clocks (1783 MHz avg vs 2190 after), compounding everything. The pre-agreed probe-with-fallback landed the same day.

### How the probe decides

`purple-gl-probe` prints exactly `0` (use hardware) or `1` (keep software) and always exits 0; xinitrc validates the output and treats anything else as `1`. Hardware requires ALL of: `glxinfo -B` succeeds within 5s with `LIBGL_ALWAYS_SOFTWARE=0`, direct rendering, a renderer that is neither Mesa software (llvmpipe/softpipe/SWR) nor a VM paravirtual renderer (virgl, SVGA3D, VMware, VirtualBox, Parallels, QXL; accelerated VMs pass every other check but virgl-class GL is too flaky to trust), and OpenGL 3.3 core (Alacritty's renderer needs it; pre-gen6 Intel keeps software rather than trusting the less exercised GLES fallback). Every failure mode, including glxinfo missing from the image, lands on software: the exact pre-probe behavior. glxinfo runs detached and is abandoned if it outlives the timeout, so even a driver wedged in an uninterruptible ioctl (unkillable D state) cannot stall the session.

Three more safety layers in xinitrc: the probe output is hard-validated to `0`/`1`; the session default export stays `LIBGL_ALWAYS_SOFTWARE=1` and only Alacritty's environment gets the probed mode, so no other GL consumer is affected; and the decision is cached per boot in `/tmp/purple-gl-mode`. If Alacritty exits nonzero under hardware GL (a driver that fools glxinfo but crashes the real renderer), xinitrc writes `1` into that cache before its restart loop, so the machine falls back to software for the rest of the boot instead of crash-looping.

Escape hatches: touch `/opt/purple/force-software-gl` (baked into an ISO, or via the overlay at runtime) to force software; for a runtime A/B either way, set `GL_MODE=0` (or `1`) after the probe block in `/home/purple/.xinitrc`, delete `/tmp/purple-gl-mode`, and restart. The decision and full glxinfo output are in `/tmp/purple-gl-probe.log`, and the boot log gets a one-line summary; `log-performance` points there when it sees software GL as a bottleneck. Contract locked by `tests/test_gl_probe.py`; build wiring by `tests/test_build_verifications.py`.

## Why PSR/FBC Stay Disabled (kept, even though they're not the fix)

Disabled on every `boot=casper` line in `build-scripts/01-remaster-iso.sh` via `i915.enable_psr=0 i915.enable_fbc=0`. Intel-only params, a safe no-op on AMD/NVIDIA. We keep them off as defense-in-depth (they are genuinely buggy partial-update sources on this hardware) and because Purple gets ~no battery benefit from them anyway:

PSR/FBC only save power while the screen holds one unchanged frame, and Purple almost never does, Art and Play blink a cursor ~2x/sec, every keystroke repaints, and even the idle sleep screen animates the face on 1.0s/0.25s timers (no DPMS screen-off, by product decision). They'd churn in and out rather than stay resident, so the saving rounds to zero. Disabling is effectively free.

Safety precedent worth knowing: commit `2b9dc89` *removed* `i915.enable_dpcd_backlight=1`, which had black-screened older MacBooks/ThinkPads by **forcing a capability on**. `enable_psr=0/enable_fbc=0` do the opposite, they **turn optional features off**, which breaks no panel. Different risk direction, which is why this is safe.

## Diagnosing On-Device

The artifact is at the scanout layer, so screenshots can't catch it (phone photos of the panel can; framebuffer grabs show the clean composed frame). `scripts/on-device/debug-display.sh` ships to `/opt/purple/scripts/` on every ISO; run it from the parent-menu terminal (Open Terminal):

- **No args**: state dump + per-mitigation **verdict**. The verdict's headline line is whether a **compositor is running**, that is the fix. It also confirms PSR/FBC from the world-readable `/sys/module/i915/parameters/*` (reliable even with no sudo) and reads the panel `max bpc`. Note: debugfs status (FBC/PSR detail) needs root. The script probes for passwordless sudo (`sudo -n true`) and uses it when available; without it, that section is honestly skipped rather than shown as empty/absent. The verdict does not rely on it either way.
- **`repro`**: drives the music-grid partial-redraw pattern through the real Alacritty to X to scanout path, to trigger the tear on demand.
- **`compositor off|on|status`**: the one runtime A/B lever that works here. picom is a plain `purple`-user process, no root, so you can stop/start it freely and re-run `repro` to see the tear appear and disappear, no ISO rebuild.

Why the PSR/FBC/TearFree *toggles* were removed: PSR/FBC are read-only kernel knobs at runtime (writes are denied even with root, they're cmdline-only), and modesetting has no TearFree property to toggle. The compositor is the only thing that's both the real fix and runtime-flippable.

## Scope Note

Covers the live-boot paths (the primary distribution model: pre-made USBs). `picom` and its config are installed into the golden image, so they apply to installed systems too, since the compositor is started from `xinitrc`, not the kernel cmdline. The PSR/FBC cmdline params are live-boot only; add them to the golden image's `/etc/default/grub` if an installed unit ever shows compression glitches.

## Key Files and References

- `config/picom/picom.conf` (the compositor config; `unredir-if-possible=false` is load-bearing)
- `scripts/purple-start-compositor.sh` (guarded launcher, shared by xinitrc and the diagnostic)
- `scripts/purple-gl-probe.sh` (Alacritty GL mode decision; contract in `tests/test_gl_probe.py`)
- `config/xinit/xinitrc` (starts the compositor after the WM, consumes the GL probe)
- `config/xorg/10-modesetting.conf` (why modesetting, and why TearFree isn't there)
- `scripts/on-device/debug-display.sh` (verdict + repro + compositor A/B)
- `build-scripts/01-remaster-iso.sh` (PSR/FBC kernel cmdline, all `boot=casper` lines)
- Commit `8fe4ca5` (the unrelated modal transparency fix, easy to confuse with this)
- Commit `2b9dc89` (removed the forced `i915.enable_dpcd_backlight=1`, the cautionary precedent)
