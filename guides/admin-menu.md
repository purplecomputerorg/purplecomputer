# Admin menu: performance, display switches and logs

Type `admin` (or `tavi`) while the Parent Menu is open. It ships on every ISO and is invisible until typed.

- **Run All Tests** does the rest of this list with no one at the keys, in about two minutes, then copies the logs. It
  times the screen with the compositor on, then off (and puts it back), then records Blocks turning a quarter four
  times, looking around with Tab and left held for 4 seconds, and tilting up and down, at 100, 400 and 850 blocks
  (`BUILDS` and `MOVES` in `purplecomputer/rooms/admin_autorun.py`). Each build is a copy of the room swapped in and
  out, so the kid's build and its Time Travel never see it; every recorded frame carries the move as `step`. One line
  per build (frames a second per move, median draw and present) and the speed tests show on screen and land in
  `/tmp/purple-perf/autorun.txt`. Escape stops it; what it got is still copied.
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
  inside Purple and again in a process of its own (`purplecomputer/screen_test.py`, `ALONE` in `admin_menu.py`): SDL's
  own way (X shared memory), then through the GPU's OpenGL and OpenGL ES (the session's GL is software:
  `LIBGL_ALWAYS_SOFTWARE`), then `X alone`, the X server filling rectangles with no SDL, plus a bare round trip
  (`sync`). Both slow: X or the GPU. Only inside slow: Purple's own threads. A GL way much faster than `Alone`: Purple
  could present that way. `X alone` fills slow but `sync` quick: X's own drawing (glamor) is slow. `cpu` far under
  the time: the call waits on X. Results show on screen and append to `/tmp/purple-perf/screen-tests.jsonl`.
- **Compositor** stops picom or starts it again (`purple-start-compositor`), right away, until the next start.
- **Next Start: GPU Acceleration** puts `AccelMethod none` in Xorg's config (no glamor) for the next start only.
  That start runs without the compositor: picom's glx needs glamor, and without it freezes the screen.
  The switch is kept in `/var/log/purple/admin-next-start` and synced at once. Installed, that's the disk. On a Purple
  Key it's the `writable` partition, but each live start gets a new `install-logs-<date>.N/log` folder there, so the
  boot script mounts the partition and takes the newest earlier start's switch. The menu's top line says whether
  each switch is on or off this start; the row is what the next start gets, so it reads On again after it's taken. `switches.txt` in the
  copied logs shows whether it was taken. `scripts/purple-admin-boot.sh` takes it before X starts and undoes it on the start
  after, so a switch that stops X starting is gone after one more restart. Add a switch to `SWITCHES` in
  `purplecomputer/rooms/admin_menu.py` and give it a line in that script.
- **Copy Logs to USB** writes `Purple Logs/<date time>/` on any FAT, exFAT or NTFS drive (the Purple Key's `PURPLEUSB`
  works): every `/tmp/purple-*.log`, `xinitrc.log`, Xorg's log and config, the recording and screen tests,
  `/var/log/purple`, the `log-performance` report, every thread's stack, dmesg, the journal, lspci, xrandr, cpufreq,
  thermals, ps with threads, and `app.json`. It works without recording too.

To time another room, call `perf_trace.laps()` at the top of its draw and `lap("name")` after each part; off, both cost nothing.
