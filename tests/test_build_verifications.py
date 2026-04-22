"""Regex-level checks that the golden-image build script includes the
audio pipeline setup and its verification block. Doesn't run the actual
build; just asserts the source ships the right pieces so a future edit
can't accidentally drop the pulseaudio user-enable or the module-
switch-on-connect drop-in without failing tests.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "build-scripts" / "00-build-golden-image.sh"


def _build_source() -> str:
    return BUILD_SCRIPT.read_text()


def test_pulseaudio_is_in_apt_list():
    src = _build_source()
    # The big apt-get install block should contain pulseaudio as a package.
    assert re.search(r"\bpulseaudio\b", src), "pulseaudio not in apt install list"


def test_pulseaudio_user_socket_enabled_globally():
    src = _build_source()
    assert re.search(
        r"systemctl\s+--global\s+enable[^\n]*pulseaudio\.socket",
        src,
    ), "pulseaudio.socket not enabled via systemctl --global"


def test_module_switch_on_connect_dropin_present():
    src = _build_source()
    assert "/etc/pulse/default.pa.d" in src, "pulse drop-in dir not created"
    assert "module-switch-on-connect" in src, "module-switch-on-connect drop-in missing"


def test_audio_pipeline_verification_block():
    """The verification block must check pulseaudio and the drop-in, and
    must exit 1 on failure so the build fails loudly."""
    src = _build_source()
    # Look for the verification block that checks for missing audio pieces.
    assert re.search(r"AUDIO_MISSING", src), "audio verification block not found"
    assert re.search(r'command -v pulseaudio', src), "pulseaudio command check missing"
    assert re.search(r"10-purple\.pa", src), "drop-in path not verified"
    # Must exit on failure (same pattern as other verification blocks).
    assert re.search(r"AUDIO_MISSING.*\n.*exit 1", src, re.DOTALL), \
        "audio verification does not exit on failure"


def test_grub_and_efibootmgr_verification_still_present():
    """Don't let this refactor accidentally drop the grub/efibootmgr check
    from the prior audio-adjacent work on hybrid boot."""
    src = _build_source()
    assert re.search(r"grub-install.*efibootmgr|efibootmgr.*grub-install", src, re.DOTALL), \
        "boot tooling verification block missing"
