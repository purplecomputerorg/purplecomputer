"""Support info's Sound check page: a plain verdict a parent can read, the readings support wants."""

from purple_tui import sound_check
from purple_tui.rooms.support_info import sound_check_report


def test_report_names_the_first_boot_volume():
    hot = sound_check.SoundCheck(heard=True, tone_db=(-5.0,) * 3, snr_db=40, sink_pct=58, sink_db=-12.0, source_pct=50, source_db=-12.0)
    text = sound_check_report(hot, ["  take one"])
    assert text.startswith("The microphone heard the chime.")
    assert "starts at Medium" in text
    assert "loop gain" in text and text.endswith("  take one")


def test_report_explains_a_check_that_could_not_run():
    assert sound_check_report(sound_check.SoundCheck(note="no microphone"), []) == "Couldn't run the check: no microphone."


def test_report_keeps_the_default_when_nothing_was_heard():
    quiet_mic = sound_check.SoundCheck(heard=False, floor_db=-90.0, tone_db=(-80.0,) * 3, snr_db=2)
    assert "did not hear the chime" in sound_check_report(quiet_mic, [])
    assert "starts at Loud" in sound_check_report(quiet_mic, [])
