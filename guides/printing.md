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
   - **Driverless first.** A printer with an IPP-over-USB interface (07/01/04) is
     served on loopback by `ipp-usb` (started by its own udev rule), and CUPS
     builds the queue from what the printer reports (`lpadmin -m everywhere`):
     paper size, color, margins.
   - **Then a driver.** Otherwise the printer's IEEE 1284 ID goes to
     `lpinfo --device-id ID -m` (lpinfo acts on `-m` and `-v` the moment it
     reads them, so filters must come first), and the best installed driver
     wins. A Brother laser brlaser doesn't list by name gets brlaser's
     HL-L2300D driver, since that family shares one protocol.
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
brlaser (Brother lasers), escpr (Epson inkjets), splix, foo2zjs, c2esp, pxljr and
openprinting-ppds. About 170 MB installed (2026-10 measurement against the golden
image); most of it is Ghostscript and the Perl that HP's SNMP library pulls in.
Known gap: newer Canon PIXMAs without IPP-over-USB need Canon's proprietary
driver, which Ubuntu doesn't ship.

## The page

`purple_tui/canvas/paper.py` composes a US Letter page at 150 dpi; the driver
fits it to A4 as well. A room that prints has `paper(g, size)` and `LANDSCAPE`:
Art prints its paint and letters with unpainted cells left white, Blocks prints
the build on a pale floor, Play prints the newest asks and answers that fit.
Music has nothing to print, so there the Print card is dimmed. The bottom corner
says "Made on" plus the computer's name (Parent Menu, Name this Computer),
adding "with Purple Computer" when the name doesn't already say Purple. The app sends a PNG
with `lp -o fit-to-page` and CUPS rasterizes it for the printer.

`purple_tui/printing.py` paces prints (one per 20 s, 20 per boot, for the ink)
and watches the queue after a page goes out, turning `printer-state-reasons`
(no paper, a jam, no ink, a door open) into one short line on screen. On a live
boot the print stack is read from the stick, so Print hides once it's pulled.

## Testing

- `PURPLE_FAKE_PRINTER=1 just preview art type:qwerty key:escape type:p` shows
  the card and writes the page to `print.png` next to the screenshots.
- `tests/canvas/test_printing.py` covers the card, the pages and the pacing.
- On a Linux machine with CUPS, `ippeveprinter -p 8631 -d jobs ...` stands in
  for a printer: `lpadmin -p purple -E -v ipp://localhost:8631/ipp/print -m everywhere`,
  then the same `lp` line the app runs.

## On real hardware

`/tmp/purple-printer.log` (setup steps), `/run/purple-printer.json`,
`lpstat -l -p purple`, and the `print:` lines in `/tmp/purple-boot.log`.
