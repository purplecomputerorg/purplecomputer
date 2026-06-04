# Intel Display Tuning: PSR/FBC and the Checkerboard Artifact

Why the live boot passes `i915.enable_psr=0 i915.enable_fbc=0`, what it fixes, why it's safe, and why it costs Purple almost no battery.

Part of the boot display story: see `boot-display-sequence.md` for the full power-on to TUI sequence and the GPU readiness wait.

---

## The Symptom

On pre-2016 Intel MacBooks (the 10-plus-year-old MacBook Pro class of target hardware), changing a single cell's background color flashes a brief checkerboard in the transition. The clearest repro is the music room: press a letter and the keycap cell cycles color, and for one frame a small checkerboard appears where the color changes. It only shows on partial redraws of a few cells, not on full-screen repaints.

## What It Is (and Is Not)

It is **not** transparency. That distinction matters because the obvious first guess is wrong, and we already fixed a real transparency bug elsewhere that is easy to confuse with this one:

- Commit `8fe4ca5` removed a genuine 60% alpha from Textual's `ModalScreen` (`background: $background 60%`) by forcing `PurpleModal` opaque. That was a real transparency artifact, and it was modal-only.
- The music grid has zero transparency. `MusicGrid.render_line()` writes an explicit opaque `bgcolor` into every cell, and there is no `NN%` alpha background anywhere in the room. So the modal fix never applied here, which is why the checkerboard kept showing in music mode after modals were fixed.

Once transparency is ruled out, a checkerboard that appears only on small partial redraws on an old Intel panel is the textbook signature of the display engine's compression features:

- **FBC (Framebuffer Compression)** compresses the scanout buffer. On a partial update it can scan out stale compressed blocks for a frame, which reads as a blocky checkerboard. This is the prime suspect for a checkerboard specifically.
- **PSR (Panel Self Refresh)** lets the panel hold a frame from its own memory while the display engine idles. Its partial-update glitches usually read as flicker or trails more than a checkerboard, but it is the runner-up.

Both are Haswell/Broadwell-era Intel features that are notoriously buggy on exactly this hardware. The corruption happens at scanout, after the terminal has already drawn the frame correctly, which is why forcing software rendering (`LIBGL_ALWAYS_SOFTWARE=1`) would not fix it: that changes how Alacritty rasterizes, not how the panel refreshes.

## The Fix

Disable both on the kernel command line, on every `boot=casper` line in `build-scripts/01-remaster-iso.sh` (normal ISO, debug menu entries, rescue):

```
i915.enable_psr=0 i915.enable_fbc=0
```

These are Intel-only (`i915`) params. On AMD or NVIDIA hardware the module is not loaded and the params are ignored, so they are a safe no-op on every other target device.

## Why Disabling Is Safe (and Not a Repeat of a Past Mistake)

There is a precedent worth knowing: commit `2b9dc89` ("Add GPU readiness") **removed** `i915.enable_dpcd_backlight=1`, which had caused black screens on older hardware including the MacBook 2014 and some ThinkPads. The same hardware class we target here.

The two changes point in opposite risk directions, which is the whole reason this one is safe:

- `i915.enable_dpcd_backlight=1` **forced a capability on**. Forcing DPCD backlight control onto a panel that does not support it kills the backlight: black screen. Genuinely dangerous, correctly removed.
- `i915.enable_psr=0 i915.enable_fbc=0` **turn optional power features off**. No panel breaks because PSR or FBC is disabled; the worst case is marginally higher idle power. The kernel already disables PSR via quirks on many known-buggy panels, so this just makes that explicit.

These params also do not touch the two mechanisms that fixed the original black screen: the DRM-node readiness wait (`scripts/purple-wait-display.sh`) and the removal of the forced backlight param. Different subsystem, no regression.

## Battery: Does Purple Actually Benefit from PSR/FBC?

Generically, PSR can save on the order of a watt on a static screen, and FBC saves some scanout memory bandwidth. The standard advice is "don't disable them, you lose battery." For Purple specifically, that advice mostly does not apply, because **PSR and FBC only save power while the screen holds a single unchanged frame, and Purple almost never does.**

What keeps the screen moving:

- **Art** runs an explicit blinking cursor (`_start_blink` / `_toggle_blink` on a timer), repainting roughly twice a second the whole time it is open.
- **Play** (the default room) uses a Textual `Input` whose cursor blinks by default, same continuous repaint.
- **Active use** of any room, music included, is a repaint per keystroke. Constant input is the entire point of the app.
- **The idle state does not go static either.** The sleep screen (the walked-away state) runs timers at 1.0s and 0.25s and deliberately keeps animating the face, and there is intentionally no DPMS screen-off. So the one moment PSR normally earns its keep, a quiet idle screen, is animated by design.

PSR and FBC bail out the instant anything changes and re-arm only after the frame is still again. A 0.5s cursor blink alone is enough to keep kicking them out, so on Purple they would churn in and out rather than stay resident. The savings they would collect here round to near zero, so disabling them is effectively free for this software.

The honest caveat: near zero, not exactly zero. There may be brief sub-second windows between blinks where they would have engaged. But that is a rounding error next to the real battery lever, an actual screen-off idle state, which is a product decision already made the other way (animated sleep face, no DPMS).

## Second Lever: TearFree (the present path)

Disabling PSR/FBC removes the scanout-compression source, but the artifact also depends on *partial* updates reaching the panel. The display only scans out a half-updated frame because the present path hands it one. `Option "TearFree" "true"` on the modesetting driver (`config/xorg/10-modesetting.conf`) forces every update through a fully composed back buffer and a single page flip, so the panel always scans out a complete, consistent frame. It is KMS-level and driver-agnostic (safe no-op risk on AMD/NVIDIA-KMS too), costs a little VRAM/bandwidth, negligible here.

This is the right lever precisely because the checkerboard is **not** a per-widget or per-screen bug: opaque content (the music grid) flashes, and a single keystroke is a partial redraw you cannot full-repaint away without wrecking performance. TearFree fixes the whole class at the layer they share, every room, the parent menu, the power screen, boot transitions, in one config line. Chasing transparency per-screen is the wrong layer and a whack-a-mole.

PSR/FBC off and TearFree are complementary: the first removes the corruption source, the second removes the partial-present that exposes it. Ship both; if you ever need to know which did the work, toggle one at a time on-device.

## Diagnosing On-Device (when the shipped fixes don't seem to work)

The artifact is at the scanout layer, so screenshots can't catch it and the screen alone won't tell you whether a mitigation actually took. `scripts/on-device/debug-display.sh` (ships to `/opt/purple/scripts/` on every ISO, run it from the parent-menu terminal) closes that gap:

- **No args**: full state dump with a per-mitigation verdict. It cross-checks the kernel cmdline against the live `/sys/module/i915/parameters/*` values (so you catch the case where `i915.enable_psr=0` is on the cmdline but never reached the module), reads the FBC/PSR debugfs status, reads the panel bit-depth/dither state, and confirms TearFree from the running X server's output property (not the config file, which can be present yet not engaged).
- **`repro`**: drives partial redraws of a few cells (the music-grid keystroke pattern) through the same Alacritty to X to scanout path, so you can trigger the artifact on demand instead of hunting for it.
- **`toggle fbc|psr|tearfree on|off`**: flips each knob at runtime (sysfs/debugfs for FBC/PSR, the xrandr `TearFree` output property for TearFree). This collapses the multi-hour ISO-rebuild loop: toggle one knob, re-run `repro`, see which one actually changes the artifact.

## A Different Suspect on Skylake (MacBookPro13,2): Panel Dither

The guide above is written around pre-2016 Haswell/Broadwell. **MacBookPro13,2 is a 2016 Skylake machine**, and on these the likelier cause of "a brief checkerboard when a few cells change color" is **6-bit panel + dithering (FRC)**: the pipe outputs 8bpp into a 6bpc panel, i915 dithers the difference, and on a partial color change the dither pattern is recomputed for those cells, which reads as a one-frame checkerboard. PSR, FBC, and TearFree do not touch dither, which is exactly why it can survive all three. The `debug-display.sh` dump prints the pipe bpp / panel bpc / dither state for this reason. If that's the cause, the lever is the panel bit depth (force 8bpc / `max bpc`, or the i915 dither control), not the compression features.

## If the Checkerboard Persists, or Battery Matters More Later

- **FBC-only.** Since a checkerboard is more characteristic of FBC than PSR, `i915.enable_fbc=0` alone may be enough. Costs an on-device round trip to confirm, which is why the shipped fix disables both in one shot.
- **Confirm the params took.** On the debug ISO, `sudo cat /sys/kernel/debug/dri/0/i915_fbc_status` and `.../i915_edp_psr_status`. If FBC still reads enabled, the cmdline isn't reaching i915 on that unit, which is the bug to chase, not a new artifact.
- **Scope by hardware.** A small systemd unit could detect Apple/old-Intel via DMI and toggle PSR/FBC off only there (sysfs/debugfs at runtime), so newer devices keep both. More moving parts; only worth it if the global battery cost ever proves real, which per the analysis above it does not for this software.
- **GL-layer render compression is already ruled out.** `xinitrc` sets `LIBGL_ALWAYS_SOFTWARE=1`, so rendering goes through Mesa's software path (llvmpipe), not the Intel hardware driver. There is no hardware render/framebuffer compression (CCS) to disable: that knob is effectively already pulled. The artifact surviving software rendering is itself the proof that it lives in the display engine, not the renderer.

## Scope Note

This covers the live-boot paths, which is the primary distribution model (pre-made USBs, live boot). Installed systems inherit Ubuntu's default kernel cmdline and have no single insertion point in the build, so they are not patched here. Add it to the golden image's `/etc/default/grub` if installed-disk units ever show the same artifact.

## Key Files and References

- `build-scripts/01-remaster-iso.sh` (kernel cmdline, all `boot=casper` lines)
- `scripts/purple-wait-display.sh` (DRM-node readiness wait, the other half of old-Intel display robustness)
- `guides/boot-display-sequence.md` (full boot sequence, GPU readiness stage)
- Commit `8fe4ca5` (the unrelated modal transparency fix, easy to confuse with this)
- Commit `2b9dc89` (removed the forced `i915.enable_dpcd_backlight=1`, the cautionary precedent)
