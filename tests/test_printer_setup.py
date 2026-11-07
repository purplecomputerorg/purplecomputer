"""purple-printer-setup's driver ladder: best guesses in order for a printer's IEEE 1284 ID."""
import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "purple-printer-setup.sh"
BROTHER = ("MFG:Brother;CMD:PJL,HBP,URF;MDL:HL-L2420DW;CLS:PRINTER;CID:Brother Laser Type1;"
           "URF:W8,CP1,IS4-1,MT1-3-4-5-8,OB10,PQ3-4-5,RS300-600-1200,V1.5,DM1;")


def drivers_for(device_id, tmp_path, cups_matches=""):
    """Run the script's drivers_for with lpinfo stubbed to print cups_matches."""
    stub = tmp_path / "lpinfo"
    stub.write_text(f"#!/bin/sh\nprintf '{cups_matches}'\n")
    stub.chmod(0o755)
    func = subprocess.run(["sed", "-n", "/^drivers_for()/,/^}/p", str(SCRIPT)], capture_output=True, text=True).stdout
    out = subprocess.run(["bash", "-c", f'{func}\ndrivers_for "$1"', "_", device_id], capture_output=True, text=True,
                         env={"PATH": f"{tmp_path}:/usr/bin:/bin:/run/current-system/sw/bin"})
    return out.stdout.split()


def test_a_brother_laser_cups_doesnt_name_gets_brlaser(tmp_path):
    assert drivers_for(BROTHER, tmp_path) == ["drv:///brlaser.drv/brl2300d.ppd"]


def test_cups_own_match_comes_first_and_driverless_entries_are_skipped(tmp_path):
    matches = "everywhere IPP Everywhere\\ndrv:///hpcups.drv/hp-laserjet_p2035.ppd HP LaserJet P2035\\n"
    assert drivers_for("MFG:HP;MDL:LaserJet P2035;CMD:PJL,PCL,POSTSCRIPT;", tmp_path, matches) == [
        "drv:///hpcups.drv/hp-laserjet_p2035.ppd",
        "gutenprint.5.3://pcl-g_5e/expert",
        "gutenprint.5.3://ps2/expert",
    ]


def test_an_unknown_printer_falls_back_on_the_languages_it_speaks(tmp_path):
    assert drivers_for("MFG:Acme;COMMAND SET:PJL,PCLXL,PWGRaster;MDL:Laser 9;", tmp_path) == [
        "gutenprint.5.3://pcl-g_6/expert",
        "gutenprint.5.3://pcl-g_5e/expert",
        "drv:///cupsfilters.drv/pwgrast.ppd",
    ]


def test_a_printer_speaking_nothing_known_gets_no_guess(tmp_path):
    assert drivers_for("MFG:Acme;CMD:ESCPL2;MDL:Thing;", tmp_path) == []


# The whole script, against a fake /run, /sys and /etc with every system command stubbed

STUBS = {
    # systemctl also records what the app could read from the state file at that moment
    "systemctl": 'echo "systemctl $* | $(cat "$PURPLE_PRINTER_ROOT/run/purple-printer.json" 2>/dev/null)" >> "$CALLS"',
    "ipptool": 'echo "ipptool $*" >> "$CALLS"; case "$*" in *:60000/*) '
               'echo "  printer-make-and-model (textWithoutLanguage) = Brother HL-L2420DW";; esac',
    "lpinfo": 'case "$*" in *"-l -v"*) printf "Device: uri = usb://Acme/Laser?serial=1\\n'
              '        device-id = MFG:Acme;CMD:PCLXL;MDL:Laser;\\n        make-and-model = Acme Laser\\n";; esac',
    "pgrep": "exit 1",
}
LOGGED = ("lpadmin", "cupsenable", "cupsaccept", "udevadm", "modprobe")


def setup_run(tmp_path, ipp_usb=True, printer=True, ready=True, heal=False):
    """Run purple-printer-setup once; returns (calls it made, the state file it left or None)."""
    root, bin_dir = tmp_path / "root", tmp_path / "bin"
    for d in ("run", "tmp", "etc/cups", "sys/bus/usb/devices"):
        (root / d).mkdir(parents=True)
    bin_dir.mkdir()
    for name, body in {**STUBS, **{n: f'echo "{n} $*" >> "$CALLS"' for n in LOGGED}}.items():
        (bin_dir / name).write_text(f"#!/usr/bin/env bash\n{body}\n")
        (bin_dir / name).chmod(0o755)
    if printer:
        iface = root / "sys/bus/usb/devices/1-1:1.0"
        iface.mkdir()
        (iface / "bInterfaceClass").write_text("07\n")
        (iface / "bInterfaceProtocol").write_text("04\n" if ipp_usb else "02\n")
    (root / "etc/cups/printers.conf").write_text("<Printer purple>\n</Printer>\n")
    state = root / "run/purple-printer.json"
    if ready:
        state.write_text('{"ready": true, "model": "Old", "via": "ipp-usb", "uri": "ipp://localhost:60000/ipp/print"}\n')
    if heal:
        (root / "run/purple-printer.heal").touch()
    calls = tmp_path / "calls"
    calls.touch()
    subprocess.run(["bash", str(SCRIPT)], timeout=60, env={
        "PATH": f"{bin_dir}:/usr/bin:/bin:/run/current-system/sw/bin",
        "PURPLE_PRINTER_ROOT": str(root), "CALLS": str(calls)})
    assert not (root / "run/purple-printer.heal").exists()
    return calls.read_text().splitlines(), json.loads(state.read_text()) if state.exists() else None


def index(calls, start):
    return next(i for i, call in enumerate(calls) if call.startswith(start))


def test_another_usb_device_leaves_a_ready_printer_alone(tmp_path):
    calls, state = setup_run(tmp_path)
    assert calls == [] and state["model"] == "Old"


def test_a_heal_restarts_cups_and_ipp_usb_then_rebuilds_the_queue(tmp_path):
    calls, state = setup_run(tmp_path, heal=True)
    cups = index(calls, "systemctl restart cups.service")
    assert '"via": "setting up"' in calls[cups]  # the card says Starting Up, not No Printer
    assert cups < index(calls, "lpadmin -x purple") < index(calls, "systemctl restart ipp-usb.service")
    assert state == {"ready": True, "model": "Brother HL-L2420DW", "via": "ipp-usb",
                     "uri": "ipp://localhost:60000/ipp/print", "id": ""}


def test_a_heal_after_the_printer_was_unplugged_leaves_no_printer(tmp_path):
    calls, state = setup_run(tmp_path, printer=False, heal=True)
    assert state is None


def test_the_usb_driver_route_records_its_device_address(tmp_path):
    calls, state = setup_run(tmp_path, ipp_usb=False, ready=False)
    assert not any("restart" in call for call in calls)
    assert state["ready"] and state["uri"] == "usb://Acme/Laser?serial=1"
    assert state["via"] == "gutenprint.5.3://pcl-g_6/expert"
    assert state["id"] == "MFG:Acme;CMD:PCLXL;MDL:Laser;"  # Printer check shows it to support
