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


def test_no_duplicate_switch_on_connect_dropin():
    """The build must NOT write a module-switch-on-connect drop-in into
    /etc/pulse/default.pa.d/. Ubuntu's stock default.pa already loads it,
    and a second load causes Pulse to refuse startup ('Module should be
    loaded once at most'), wedging audio entirely. Regression guard for
    the Surface-post-install audio failure."""
    src = _build_source()
    assert "cat > \"$MOUNT_DIR/etc/pulse/default.pa.d/10-purple.pa\"" not in src, \
        "build is writing a Pulse drop-in again; stock default.pa already loads module-switch-on-connect"
    assert "load-module module-switch-on-connect" not in src, \
        "build is injecting a duplicate load of module-switch-on-connect"


def test_audio_pipeline_verification_block():
    """The verification block must check pulseaudio and the user socket,
    guard against the duplicate-load drop-in, and exit 1 on failure."""
    src = _build_source()
    assert re.search(r"AUDIO_MISSING", src), "audio verification block not found"
    assert re.search(r'command -v pulseaudio', src), "pulseaudio command check missing"
    assert re.search(r"stale-10-purple\.pa-dropin-present", src), \
        "verification does not guard against the duplicate-load drop-in regression"
    assert re.search(r"pulseaudio\.service-still-in-default\.target\.wants", src), \
        "verification does not guard against the eager pulseaudio.service regression"
    assert re.search(r"systemctl\s+--global\s+disable\s+pulseaudio\.service", src), \
        "build does not explicitly disable pulseaudio.service (undoing Ubuntu preset)"
    assert re.search(r"AUDIO_MISSING.*\n.*exit 1", src, re.DOTALL), \
        "audio verification does not exit on failure"


def test_grub_and_efibootmgr_verification_still_present():
    """Don't let this refactor accidentally drop the grub/efibootmgr check
    from the prior audio-adjacent work on hybrid boot."""
    src = _build_source()
    assert re.search(r"grub-install.*efibootmgr|efibootmgr.*grub-install", src, re.DOTALL), \
        "boot tooling verification block missing"
