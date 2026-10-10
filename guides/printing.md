# Printing

Plug a printer into a USB port and it prints. There is no setup screen and no
setting. The Esc menu's Print card always says where things stand: No Printer,
Starting Up, Can't Print (pressing it says why), or Print. A toast says so too
when a printer is plugged in, gets ready, turns out not to work, or is unplugged,
and Support info names the printer and the technical reason.

## How a printer gets set up

1. `config/udev/70-purple-printer.rules` sees a USB device with a printer
   interface (class 07) and restarts `purple-printer.service`. Every USB removal
   restarts it too, since a removed device's interfaces are already gone.
2. `scripts/purple-printer-setup.sh` (root) rebuilds the one queue, `purple`:
   - It waits for udev to settle first: the plug event fires before the
     kernel lists the printer's interfaces, and a Brother HL-L2420DW read that
     early looked like a plain USB printer while ipp-usb took it.
   - **Driverless first.** A printer with an IPP-over-USB interface (07/01/04),
     or one `ipp-usb` already holds, is served on loopback by `ipp-usb`
     (started by its own udev rule), and CUPS builds the queue from what the
     printer reports (`lpadmin -m everywhere`): paper size, color, margins.
     The first query can come back empty, so it retries for 20 s.
   - **Then a driver ladder.** `ipp-usb` is stopped (while it runs it holds the
     printer and the USB backend waits forever) and so is `usblp`, then
     `drivers_for` lists guesses for the printer's IEEE 1284 ID, best first,
     and the first one `lpadmin` accepts wins: CUPS's own ranking
     (`lpinfo --device-id ID -m`; lpinfo acts on `-m` and `-v` the moment it
     reads them, so filters go first), brlaser's HL-L2300D driver for Brother
     lasers it doesn't name (one protocol for the family), then Gutenprint's
     generic PCL 6, PCL 5e and PostScript drivers and cups-filters' PWG raster,
     each only when the ID lists that language.
3. It writes `/run/purple-printer.json` (`{"ready", "model", "via"}`), with
   `via` "setting up" while it works. The app stats that file every 2 s, so
   watching for a printer costs no process.

When some other USB device comes or goes, a ready queue is left alone so a
printing job survives.

## Offline

Nothing runs until a printer is plugged in: CUPS starts on its socket, `ipp-usb`
from udev. `ipp-usb` listens on loopback with DNS-SD off
(`config/ipp-usb/ipp-usb.conf`) and avahi is masked, so no mDNS ever leaves the
machine. WiFi and network printers are out of scope on purpose.

## Drivers in the image

`cups` plus `ipp-usb`, hpcups (HP), Gutenprint (older Canon and Epson inkjets),
brlaser (Brother lasers), escpr (Epson inkjets), splix, foo2zjs, c2esp and pxljr.
Not openprinting-ppds: cups-driverd rejects thousands of its files on every
lookup, which floods the log and slows matching. About 170 MB installed (2026-10 measurement against the golden
image); most of it is Ghostscript and the Perl that HP's SNMP library pulls in.
Known gap: newer Canon PIXMAs without IPP-over-USB need Canon's proprietary
driver, which Ubuntu doesn't ship.

## The page

`purple_tui/canvas/paper.py` composes a US Letter page at 150 dpi; the driver
fits it to A4 as well. A room that prints has `paper(g, size)` and `LANDSCAPE`:
Art prints its paint and letters with unpainted cells left white, Blocks prints
the build on a pale floor, Play prints the newest asks and answers that fit,
Music prints the key grid in the colors the kid gave it. A room with nothing
made yet prints nothing. The bottom corner
says "Made on" plus the computer's name (Parent Menu, Name this Computer),
adding "with Purple Computer" when the name doesn't already say Purple. The app sends a PNG
with `lp -o fit-to-page` and CUPS rasterizes it for the printer.

`purple_tui/printing.py` paces prints (one per 20 s, 20 per boot, for the ink)
and follows each job by its number until CUPS says it finished, turning
`printer-state-reasons` (no paper, a jam, no ink, a door open), a job CUPS
gave up on, and a job still waiting after a minute into one short line on
screen. A job that dies leaves no other trace, since the queue aborts it, and
one that never finishes is cancelled after three minutes so it can't block the
pages behind it. On a live
boot the print stack is read from the stick, so Print hides once it's pulled.

## Testing

- `PURPLE_FAKE_PRINTER=1 just preview art type:qwerty key:escape type:p` shows
  the card and writes the page to `print.png` next to the screenshots.
- `tests/canvas/test_printing.py` covers the card, the pages and the pacing.
- On a Linux machine with CUPS, `ippeveprinter -p 8631 -d jobs ...` stands in
  for a printer: `lpadmin -p purple -E -v ipp://localhost:8631/ipp/print -m everywhere`,
  then the same `lp` line the app runs.

## On real hardware

From the Parent Menu terminal, `printer-test` shows what Purple set up and the
last jobs; `printer-test help` lists the rest: print a test circle, rebuild the
queue on the driverless route (`ipp`) or the USB driver route (`usb`, optionally
naming one driver), list the drivers the ladder would try, and show CUPS's job
log. Logs: `/tmp/purple-printer.log` (setup), `/run/purple-printer.json`, and
the `print:` lines in `/tmp/purple-boot.log`.

Verified on hardware (Brother HL-L2420DW, 2026-10-05): the driverless route
through ipp-usb. The driver ladder is best guesses from each driver's model
list and the printer's 1284 ID and has not printed on a real printer yet;
`printer-test usb` is how to check one.
