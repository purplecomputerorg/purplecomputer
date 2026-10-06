"""purple-printer-setup's driver ladder: best guesses in order for a printer's IEEE 1284 ID."""
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
