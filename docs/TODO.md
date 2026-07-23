# Pending Work

## Performance pass validation (fixes landed 2026-07-23, commit 743a8d0)

The sluggishness fixes (fuzzy vocab precompute, audio stream idle-release, solid caret, on-demand timers) are in, with regression tests in `tests/test_performance.py`.

**Required before shipping the next ISO, on any one real laptop (~2 minutes):**
audio idle-release sanity: boot Purple, leave it untouched for ~90 seconds, listen for a click/pop when the audio stream suspends, then press a letter in Play and confirm the letter sound plays (the lazy re-warm path). If a codec pops audibly on suspend, add a codec veto (pattern: `_silence_reason` in `music_room.py`).

**Optional, when curious:**
- Re-run `log-performance` on the HP Stream: expect pulseaudio near 0% after a quiet minute (was a constant 13-14% of a core), python3 near zero at idle, visibly better typing.
- Governor A/B (`echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`) only if typing still feels sluggish after the code fixes.
