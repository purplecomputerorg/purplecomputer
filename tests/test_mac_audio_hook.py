"""purple-mac-audio: the patched speaker module loads only on the listed Macs,
and every other case (other machines, missing build, failed load) gets stock."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "purple-mac-audio.sh"
VARIANTS = ROOT / "config" / "grub" / "purple-variants.cfg"
CIRRUS, CS8409 = "snd_hda_codec_cirrus", "snd_hda_codec_cs8409"


@pytest.fixture
def run(tmp_path):
    bin_dir, mods, log = tmp_path / "bin", tmp_path / "mods", tmp_path / "calls"
    bin_dir.mkdir()
    mods.mkdir()
    for tool in ("modprobe", "insmod"):
        stub = bin_dir / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >> {log}\n[ "$INSMOD_FAILS" != 1 ] || [ {tool} != insmod ]\n')
        stub.chmod(0o755)
    (bin_dir / "modinfo").write_text("#!/bin/sh\necho snd-hda-codec,snd-hda-codec-generic\n")
    (bin_dir / "modinfo").chmod(0o755)

    def _run(*args, product="MacBook10,1", built=(CIRRUS, CS8409), taint=None, insmod_fails=False):
        for m in built:
            (mods / f"{m}.ko").write_text("")
        (tmp_path / "product").write_text(product + "\n")
        sysmod = tmp_path / "sys"
        if taint is not None:
            (sysmod / CIRRUS).mkdir(parents=True, exist_ok=True)
            (sysmod / CIRRUS / "taint").write_text(taint + "\n")
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "PURPLE_VARIANTS": str(VARIANTS),
               "PURPLE_MAC_MODULES": str(mods), "PURPLE_PRODUCT_FILE": str(tmp_path / "product"),
               "PURPLE_SYS_MODULE": str(sysmod), "INSMOD_FAILS": "1" if insmod_fails else "0"}
        out = subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=10)
        calls = log.read_text().splitlines() if log.exists() else []
        log.unlink(missing_ok=True)
        return out, calls, mods

    return _run


def _stock(module):
    return f"modprobe --ignore-install {module}"


@pytest.mark.parametrize("product,module", [("MacBook10,1", CIRRUS), ("MacBook9,1", CIRRUS),
                                            ("MacBookPro13,3", CS8409), ("MacBookPro14,1", CS8409)])
def test_listed_mac_loads_patched_module_after_its_deps(run, product, module):
    out, calls, mods = run("load", module, product=product)
    assert out.returncode == 0
    assert calls == ["modprobe snd-hda-codec", "modprobe snd-hda-codec-generic", f"insmod {mods}/{module}.ko"]


@pytest.mark.parametrize("product,module", [
    ("MacBookAir7,2", CIRRUS),      # 2015 Air: same CS4208, working speakers
    ("MacBook8,1", CIRRUS),         # 2015 12": the driver does not support it
    ("MacBook10,1", CS8409),        # right Mac, wrong module
    ("Inspiron 3511", CS8409),      # Dells use CS8409 too, with Secure Boot on
    ("MacBookPro15,1", CS8409),     # T2: different audio path
    ("MacBookPro13,3", CIRRUS),
])
def test_everything_else_gets_the_stock_module(run, product, module):
    out, calls, _ = run("load", module, product=product)
    assert calls == [_stock(module)]


def test_missing_patched_build_falls_back_to_stock(run):
    _, calls, _ = run("load", CIRRUS, built=())
    assert calls == [_stock(CIRRUS)]


def test_failed_patched_load_falls_back_to_stock(run):
    _, calls, _ = run("load", CIRRUS, insmod_fails=True)
    assert calls[-1] == _stock(CIRRUS)


def test_softvol_only_for_the_cs4208_card_on_the_patched_driver(run, tmp_path, monkeypatch):
    for card, chip in ((0, "Cirrus Logic CS4208"), (1, "USB Audio")):
        (tmp_path / "asound" / f"card{card}").mkdir(parents=True)
        (tmp_path / "asound" / f"card{card}" / "codec#0").write_text(f"Codec: {chip}\n")
    monkeypatch.setenv("PURPLE_ASOUND", str(tmp_path / "asound"))
    assert run("softvol", "0", taint="OE")[0].stdout.strip() == "PURPLE_SOFTVOL=1"
    assert run("softvol", "1", taint="OE")[0].stdout.strip() == "", "a USB headset keeps its own volume"
    assert run("softvol", "0", taint="")[0].stdout.strip() == ""
    assert run("softvol", "0")[0].stdout.strip() == ""


def test_hook_is_wired_for_both_modules_and_reads_the_shared_model_lists():
    conf = (ROOT / "config" / "modprobe" / "purple-mac-audio.conf").read_text()
    for module in (CIRRUS, CS8409):
        assert f"install {module} /usr/local/sbin/purple-mac-audio load {module}" in conf
    variants = VARIANTS.read_text()
    cs4208 = re.search(r"set purple_cs4208mac_models='(.*)'", variants).group(1)
    cs8409 = re.search(r"set purple_cs8409mac_models='(.*)'", variants).group(1)
    assert [m for m in ("MacBook8,1", "MacBook9,1", "MacBook10,1", "MacBook10,11") if re.search(cs4208, m)] \
        == ["MacBook9,1", "MacBook10,1"]
    pros = [f"MacBookPro{a},{b}" for a in (12, 13, 14, 15) for b in (1, 2, 3, 4)]
    assert [m for m in pros if re.search(cs8409, m)] == \
        [f"MacBookPro{a},{b}" for a in (13, 14) for b in (1, 2, 3)]


def test_udev_rule_switches_pulse_to_software_volume():
    rule = (ROOT / "config" / "udev" / "91-purple-mac-audio.rules").read_text()
    assert 'IMPORT{program}="/usr/local/sbin/purple-mac-audio softvol %n"' in rule
    for line in rule.splitlines():
        if line and not line.startswith("#"):
            assert 'ACTION=="change", KERNEL=="card*"' in line, "remove and other events must not rerun amixer"
    assert "Master 100" not in rule, "full headphone gain"
    assert 'ENV{PULSE_PROFILE_SET}="purple-softvol.conf"' in rule
    profile = (ROOT / "config" / "pulse" / "purple-softvol.conf").read_text()
    assert "[Mapping analog-stereo]" in profile
    assert "paths-output" not in profile and "element-" not in profile, "a mixer path brings back hardware volume"
