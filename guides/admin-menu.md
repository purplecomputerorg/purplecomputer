# Admin menu: performance, display switches and logs

Type `admin` (or `tavi`) while the Parent Menu is open. It ships on every ISO and is invisible until typed.

- **Record Performance** closes the menus and records for 10 minutes or until **Stop Recording**:
  - `/tmp/purple-perf/frames.jsonl`: a header (screen size, bit depth, KMS or SDL driver, compositor, this start's
    switches, pygame and SDL versions, CPU ticks per second), then one line per frame: `room` (`blocks:part` is a
    patch, not a full repaint), `draw`, `present` and `gap` (ms since the frame before reached the screen:
    choppiness), plus whatever the room noted. Blocks notes `blocks`, `view` (turn, tilt, fit), `look_dt` (the step
    its easing took) and `phases`: ms per part of the frame, from `perf_trace.laps()`. A moving view's phases are
    `shape camera guide floor sun behind drop_marks front hover_marks arrow_keys chrome`; at rest, `layers cursor chrome`.
  - Once a second while frames are drawn, a `threads` line: each of Purple's threads as `name#tid`, its CPU ticks so
    far (difference two lines for its share), and its innermost three Python frames.
  - `log-performance`'s once a second samples beside it: CPU per core and process, frequency, temperature, pressure stalls.
- **Screen Speed Test** freezes the screen for several seconds while it times 60 one-pixel updates and 60 full ones,
  inside Purple and again in a process of its own (`purplecomputer/screen_test.py`). Both slow: X or the GPU. Only
  inside slow: Purple's own threads. Results show on screen and append to `/tmp/purple-perf/screen-tests.jsonl`.
- **Compositor** stops picom or starts it again (`purple-start-compositor`), right away, until the next start.
- **Next Start: GPU Acceleration** puts `AccelMethod none` in Xorg's config (no glamor) for the next start only.
  The switch is kept in `/var/log/purple/admin-next-start`, so it needs a Purple Key whose `/var/log` is its writable
  partition, or an installed system. `scripts/purple-admin-boot.sh` takes it before X starts and undoes it on the start
  after, so a switch that stops X starting is gone after one more restart. Add a switch to `SWITCHES` in
  `purplecomputer/rooms/admin_menu.py` and give it a line in that script.
- **Copy Logs to USB** writes `Purple Logs/<date time>/` on any FAT, exFAT or NTFS drive (the Purple Key's `PURPLEUSB`
  works): every `/tmp/purple-*.log`, `xinitrc.log`, Xorg's log and config, the recording and screen tests,
  `/var/log/purple`, the `log-performance` report, every thread's stack, dmesg, the journal, lspci, xrandr, cpufreq,
  thermals, ps with threads, and `app.json`. It works without recording too.

To time another room, call `perf_trace.laps()` at the top of its draw and `lap("name")` after each part; off, both cost nothing.
