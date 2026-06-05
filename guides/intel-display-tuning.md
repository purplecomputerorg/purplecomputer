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

Two things that matter in `config/picom/picom.conf`:

- **`unredir-if-possible = false`** is mandatory. Alacritty runs fullscreen, and picom's default is to *unredirect* fullscreen windows for performance, which hands Alacritty straight back to the tearing scanout path and undoes everything. Keep it redirected.
- **Hardware GL for the compositor only.** The session exports `LIBGL_ALWAYS_SOFTWARE=1` (Alacritty renders via llvmpipe, robust on any GPU). The launcher starts picom with `LIBGL_ALWAYS_SOFTWARE=0` so the *compositor* uses the real GPU (glx backend) for fast vsync, with an `xrender` fallback for VMs / machines where hardware GL is unavailable.

## Why PSR/FBC Stay Disabled (kept, even though they're not the fix)

Disabled on every `boot=casper` line in `build-scripts/01-remaster-iso.sh` via `i915.enable_psr=0 i915.enable_fbc=0`. Intel-only params, a safe no-op on AMD/NVIDIA. We keep them off as defense-in-depth (they are genuinely buggy partial-update sources on this hardware) and because Purple gets ~no battery benefit from them anyway:

PSR/FBC only save power while the screen holds one unchanged frame, and Purple almost never does, Art and Play blink a cursor ~2x/sec, every keystroke repaints, and even the idle sleep screen animates the face on 1.0s/0.25s timers (no DPMS screen-off, by product decision). They'd churn in and out rather than stay resident, so the saving rounds to zero. Disabling is effectively free.

Safety precedent worth knowing: commit `2b9dc89` *removed* `i915.enable_dpcd_backlight=1`, which had black-screened older MacBooks/ThinkPads by **forcing a capability on**. `enable_psr=0/enable_fbc=0` do the opposite, they **turn optional features off**, which breaks no panel. Different risk direction, which is why this is safe.

## Diagnosing On-Device

The artifact is at the scanout layer, so screenshots can't catch it (phone photos of the panel can; framebuffer grabs show the clean composed frame). `scripts/on-device/debug-display.sh` ships to `/opt/purple/scripts/` on every ISO; run it from the parent-menu terminal (Open Terminal):

- **No args**: state dump + per-mitigation **verdict**. The verdict's headline line is whether a **compositor is running**, that is the fix. It also confirms PSR/FBC from the world-readable `/sys/module/i915/parameters/*` (reliable even with no sudo) and reads the panel `max bpc`. Note: debugfs status (FBC/PSR detail) needs root, and the Purple terminal has **no passwordless sudo**, so that section is honestly skipped rather than shown as empty/absent.
- **`repro`**: drives the music-grid partial-redraw pattern through the real Alacritty to X to scanout path, to trigger the tear on demand.
- **`compositor off|on|status`**: the one runtime A/B lever that works here. picom is a plain `purple`-user process, no root, so you can stop/start it freely and re-run `repro` to see the tear appear and disappear, no ISO rebuild.

Why the PSR/FBC/TearFree *toggles* were removed: PSR/FBC are read-only kernel knobs at runtime (writes are denied even with root, they're cmdline-only), and modesetting has no TearFree property to toggle. The compositor is the only thing that's both the real fix and runtime-flippable.

## Scope Note

Covers the live-boot paths (the primary distribution model: pre-made USBs). `picom` and its config are installed into the golden image, so they apply to installed systems too, since the compositor is started from `xinitrc`, not the kernel cmdline. The PSR/FBC cmdline params are live-boot only; add them to the golden image's `/etc/default/grub` if an installed unit ever shows compression glitches.

## Key Files and References

- `config/picom/picom.conf` (the compositor config; `unredir-if-possible=false` is load-bearing)
- `scripts/purple-start-compositor.sh` (guarded launcher, shared by xinitrc and the diagnostic)
- `config/xinit/xinitrc` (starts the compositor after the WM)
- `config/xorg/10-modesetting.conf` (why modesetting, and why TearFree isn't there)
- `scripts/on-device/debug-display.sh` (verdict + repro + compositor A/B)
- `build-scripts/01-remaster-iso.sh` (PSR/FBC kernel cmdline, all `boot=casper` lines)
- Commit `8fe4ca5` (the unrelated modal transparency fix, easy to confuse with this)
- Commit `2b9dc89` (removed the forced `i915.enable_dpcd_backlight=1`, the cautionary precedent)
