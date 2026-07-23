# Pending Work

## GL probe validation (landed 2026-07-23)

Alacritty's GL mode is now decided at startup by `purple-gl-probe` (hardware GL when the driver verifiably works, software fallback otherwise). Measured A/B on real hardware: Surface i5-7200U alacritty 114.7% to 3.1% of a core, HP Stream 62-75% to 6-7%.

**Required before shipping the next ISO:**
- Boot the new ISO on one real laptop: `log-performance` should say "Alacritty uses hardware GL" and `/tmp/purple-gl-probe.log` should name the real renderer.
- Boot it in a VM (UTM or QEMU): probe log should say software, via the llvmpipe check (plain VM) or the VM-renderer check (GPU-accelerated VM with virgl), confirming the no-op path.
- Glance at boot time: the probe adds one glxinfo call (~100-300ms) before Alacritty launches, first boot only (cached per boot after that).

## Performance pass validation (fixes landed 2026-07-23, commit 743a8d0)

The sluggishness fixes (fuzzy vocab precompute, audio stream idle-release, solid caret, on-demand timers) are in, with regression tests in `tests/test_performance.py`.

**Required before shipping the next ISO, on any one real laptop (~2 minutes):**
audio idle-release sanity: boot Purple, leave it untouched for ~90 seconds, listen for a click/pop when the audio stream suspends, then press a letter in Play and confirm the letter sound plays (the lazy re-warm path). If a codec pops audibly on suspend, add a codec veto (pattern: `_silence_reason` in `music_room.py`).

**Optional, when curious:**
- Re-run `log-performance` on the HP Stream: expect pulseaudio near 0% after a quiet minute (was a constant 13-14% of a core), python3 near zero at idle, visibly better typing.
- Governor A/B (`echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`) only if typing still feels sluggish after the code fixes.
