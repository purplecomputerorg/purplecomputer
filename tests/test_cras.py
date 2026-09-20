"""CRAS glue: node choice and volume mapping. Dump lines are from a real ChromeOS 96 device."""

from purple_tui import cras

SPEAKER = "    (72a57953)    9:0       75 0.000000     yes                no    1789917063            INTERNAL_SPEAKER     2 Speaker"
HEADPHONE = "    (9e934263)    9:1      100 0.000000      {plugged}                no             0            HEADPHONE     2 Headphone"
MIC = "    (11111111)    10:0      100 0.000000     yes                no    1789917063            INTERNAL_MIC     2*Internal Mic"


def dump(plugged):
    return "\n".join(["Output Nodes:", SPEAKER, HEADPHONE.format(plugged=plugged), "Input Nodes:", MIC])


def test_speaker_when_headphones_unplugged():
    assert cras.pick_output(dump("no")) == "9:0"


def test_plugged_headphones_win():
    assert cras.pick_output(dump("yes")) == "9:1"


def test_no_nodes():
    assert cras.pick_output("") is None


def test_volume_follows_the_pactl_cubic_curve_in_half_db_steps():
    volume = lambda level: int(cras.volume_argv(level)[-1][-1])
    assert [volume(v) for v in (0, 15, 53, 100)] == [0, 1, 67, 100]
    assert cras.volume_argv(0)[0][-1] == "1" and cras.volume_argv(53)[0][-1] == "0"
