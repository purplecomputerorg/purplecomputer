"""The Audio info kernel-log filter must surface DSP firmware load failures
(the root cause behind machines that probe no sound card) without drowning
the capped window in unrelated lines."""

from purple_tui.diagnostics import AUDIO_DMESG_PAT


def test_pattern_catches_sof_firmware_failure():
    line = ("sof-audio-pci-intel-tgl 0000:00:1f.3: Direct firmware load "
            "for intel/sof/sof-tgl.ri failed with error -2")
    assert AUDIO_DMESG_PAT.search(line)


def test_pattern_catches_legacy_hda_lines():
    assert AUDIO_DMESG_PAT.search("snd_hda_codec_realtek hdaudioC0D0: autoconfig for ALC256")


def test_pattern_ignores_unrelated_firmware_chatter():
    assert not AUDIO_DMESG_PAT.search("usb 1-2: new high-speed USB device number 3")
    assert not AUDIO_DMESG_PAT.search("i915 0000:00:02.0: firmware i915/tgl_guc_70.bin loaded")
