# Admin menu: recording performance and pulling logs

Type `admin` (or `tavi`) while the Parent Menu is open. It ships on every ISO and is invisible until typed.

- **Record Performance** closes the menus and starts recording, for 10 minutes or until **Stop Recording**:
  - `/tmp/purple-perf/frames.jsonl`: a header (screen size, bit depth, KMS or SDL driver, pygame and SDL versions), then
    one line per frame: `room` (`blocks:part` is a patch, not a full repaint), `draw`, `present` and `gap` (ms since the
    frame before reached the screen: choppiness), plus whatever the room noted. Blocks notes `blocks`, `view`
    (turn, tilt, fit), `look_dt` (the step its easing took), and `phases`: ms per part of the frame, from
    `perf_trace.laps()`. A moving view's phases are `shape camera guide floor sun behind drop_marks front hover_marks
    arrow_keys chrome`; at rest, `layers cursor chrome`.
  - `log-performance`'s once a second samples beside it: CPU per core and process, frequency, temperature, pressure stalls.
- **Copy Logs to USB** writes `Purple Logs/<date time>/` on any FAT, exFAT or NTFS drive (the Purple Key's `PURPLEUSB`
  works): every `/tmp/purple-*.log`, `xinitrc.log`, the recording, `/var/log/purple`, the `log-performance` report,
  dmesg, the journal, lspci, xrandr, glxinfo, cpufreq, thermals, ps, and `app.json`. It works without recording too.

To time another room, call `perf_trace.laps()` at the top of its draw and `lap("name")` after each part; off, both cost nothing.
