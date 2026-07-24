# Pending Work

## Post-install "Press Enter to restart" freeze: root cause confirmed, fix landed, needs Surface validation

Root cause (confirmed by A/B on the Surface i5-7200U, 2026-07-24): raw `reboot(2)` while Xorg still holds a live hardware-GL context intermittently wedges the i915 driver during kernel device shutdown. Black screen, no POST, power hold needed. Evidence: 3x installs froze on hardware GL, install on software GL rebooted clean, `sync; reboot -f` from a terminal black-screened on hardware GL with no install involved (install is a red herring: its path just always ends in that raw reboot), and `pkill Xorg` before reboot produced a real POST (Surface logo). HP Stream and MacBook Air never wedge; `systemctl poweroff` works everywhere because systemd stops the X unit before powering off.

Fix (landed): `purple-reboot` now mirrors systemd's ordering. Before `reboot(2)` it finds Xorg via `/proc/*/comm`, SIGTERMs it, polls `/proc/<pid>/stat` until real process death (DRM master released; a zombie counts as dead so an unreapable parent after USB removal can't stall the poll), SIGKILL backstop at 5s, 1s settle. Bounded at ~7s worst case, then reboots regardless. If the first `reboot(2)` fails, X is killed again before the retry, since `purple-x11.service` (Restart=on-failure, RestartSec=2) can respawn it mid-chain. General fix: no Surface hardcoding, hardware GL stays on for every machine. Covered by `just test-reboot`.

Fallback lever if the Surface still wedges after teardown: kernel `reboot=` method on the cmdline (bios/acpi/pci/efi).

**Required before shipping: rebuild the ISO and validate on the Surface.** Run the full install, press Enter at "All done", confirm a real POST instead of a black screen. Repeat 2-3 times since the wedge was intermittent.

## GL probe validation (landed 2026-07-23)

Alacritty's GL mode is now decided at startup by `purple-gl-probe` (hardware GL when the driver verifiably works, software fallback otherwise). Measured A/B on real hardware: Surface i5-7200U alacritty 114.7% to 3.1% of a core, HP Stream 62-75% to 6-7%.

**Required before shipping the next ISO:**
- Boot the new ISO on one real laptop: `log-performance` should say "Alacritty uses hardware GL" and `/tmp/purple-gl-probe.log` should name the real renderer.
- Boot it in a VM (UTM or QEMU): probe log should say software, via the llvmpipe check (plain VM) or the VM-renderer check (GPU-accelerated VM with virgl), confirming the no-op path.
- Glance at boot time: the probe adds one glxinfo call (~100-300ms) before Alacritty launches, first boot only (cached per boot after that).

## Burst-typing and room-paint fixes (landed 2026-07-23, after 743a8d0)

Root causes found by profiling the real dispatch path headlessly:
1. Every keystroke forced a full-screen layout pass (autocomplete hint `Static.update()` defaults to layout=True, and Textual `Input._watch_value` sets the layout-reactive `virtual_size`). Now repaint-only; guarded by `test_typing_never_triggers_layout_pass`. This was the dominant per-key cost.
2. GC: full collections scanned ~85k startup objects; now `gc.collect()+gc.freeze()` after first paint so they're permanently exempt.
3. Audio retry poll: on machines where audio never comes up, a full cold python+pygame subprocess probe ran every 5s forever (10s timeout each), competing with the UI for both cores. Now exponential backoff, never probes while the user is active (skipped rounds don't spend the probe budget, so continuous typing can't starve recovery), gives up after 5 probes or 10 minutes (hotplug listener still covers USB speakers).
4. ACPI reads (charger online every 5s, /proc/acpi lid fallback every 5s, battery capacity every 30s) ran on the UI thread; EC-mediated reads can block 100ms+ on cheap laptops. All moved to a PowerManager background refresher thread with cached getters; the battery widget's duplicate sysfs scan is gone.
5. `MusicMode.on_mount` called `warm_mixer()` synchronously, which can block first paint for seconds behind the boot probe lock; the room sat blank. Now a daemon thread.

Backed out after review (over-engineering for costs that no longer exist):
- 150ms autocomplete debounce: the recompute measures 0.003ms mean / 0.42ms max since the vocab precompute in 743a8d0, and the debounce added a message type, split handlers in two rooms, and a stale-hint window.
- Async mixer re-warm gates: they dropped the first sound after an idle minute. The synchronous fast re-init from 743a8d0 (direct `pygame.mixer.init()`, no subprocess probe) is quick enough and plays the note.

Ruled out: pty backpressure (Textual 8 writes frames from a dedicated WriterThread, so a slow Alacritty lags the display but can't block input processing). Also: hardware GL frees a core but does not fix typing feel; the sluggishness was the UI thread blocking itself, not CPU scarcity.

Known cap, not a bug: `InputFloodGuard` drops CharacterActions above 15/s (burst 5). Heavy two-handed mashing exceeds this, so some mashed keys are dropped BY DESIGN; that reads as missed letters, not a hang. The limit was tuned when a keystroke cost a full-screen layout pass; with the fixes above it is probably too conservative. Revisit (raise rate/burst) after on-device validation.

**Required before shipping the next ISO, on a real laptop:**
- Jam ~20 keys in Play: letters should appear with no multi-second stall, including right after sitting idle for over a minute (the mixer re-warm case).
- Enter Music room right after boot and again after an idle minute: the key grid should paint immediately and the first note should sound.
- Mash keys hard for ~5s repeatedly over a few minutes: no multi-second freezes. If letters lag but keep flowing at a steady rate, that's the 15/s flood guard, not a hang: consider raising it.

## Performance pass validation (fixes landed 2026-07-23, commit 743a8d0)

The sluggishness fixes (fuzzy vocab precompute, audio stream idle-release, solid caret, on-demand timers) are in, with regression tests in `tests/test_performance.py`.

**Required before shipping the next ISO, on any one real laptop (~2 minutes):**
audio idle-release sanity: boot Purple, leave it untouched for ~90 seconds, listen for a click/pop when the audio stream suspends, then press a letter in Play and confirm the letter sound plays (the lazy re-warm path). If a codec pops audibly on suspend, add a codec veto (pattern: `_silence_reason` in `music_room.py`).

**Optional, when curious:**
- Re-run `log-performance` on the HP Stream: expect pulseaudio near 0% after a quiet minute (was a constant 13-14% of a core), python3 near zero at idle, visibly better typing.
- Governor A/B (`echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`) only if typing still feels sluggish after the code fixes.
