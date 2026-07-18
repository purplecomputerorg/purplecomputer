"""Regex-level checks that the golden-image build script includes the
audio pipeline setup and its verification block. Doesn't run the actual
build; just asserts the source ships the right pieces so a future edit
can't accidentally drop the pulseaudio user-enable or the module-
switch-on-connect drop-in without failing tests.
"""

import functools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "build-scripts" / "00-build-golden-image.sh"


@functools.lru_cache(maxsize=1)
def _build_source() -> str:
    return BUILD_SCRIPT.read_text()


def test_pulseaudio_is_in_apt_list():
    src = _build_source()
    # The big apt-get install block should contain pulseaudio as a package.
    assert re.search(r"\bpulseaudio\b", src), "pulseaudio not in apt install list"


def test_pulseaudio_systemd_units_are_disabled():
    """Pulse must come up via client-side autospawn only, not systemd socket
    activation or eager service start. If pulseaudio.socket is enabled at
    boot it binds /run/user/1000/pulse/native, and Pulse's stock default.pa
    (module-native-protocol-unix) then fails to bind the same path, crash-
    looping until start-limit-hit. Regression guard for that whole saga."""
    src = _build_source()
    assert re.search(
        r'rm\s+-f\s+"\$MOUNT_DIR/etc/systemd/user/sockets\.target\.wants/pulseaudio\.socket"',
        src,
    ), "build does not remove the pulseaudio.socket enable symlink"
    assert re.search(
        r'rm\s+-f\s+"\$MOUNT_DIR/etc/systemd/user/default\.target\.wants/pulseaudio\.service"',
        src,
    ), "build does not remove the pulseaudio.service enable symlink"
    assert not re.search(
        r"systemctl\s+--global\s+enable[^\n]*pulseaudio",
        src,
    ), "build is re-enabling pulseaudio via systemctl --global; must stay autospawn-only"


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
    """The verification block must check pulseaudio is installed, guard
    against the duplicate-load drop-in, guard against either systemd unit
    being enabled, and exit 1 on failure."""
    src = _build_source()
    assert re.search(r"AUDIO_MISSING", src), "audio verification block not found"
    assert re.search(r'command -v pulseaudio', src), "pulseaudio command check missing"
    assert re.search(r"stale-10-purple\.pa-dropin-present", src), \
        "verification does not guard against the duplicate-load drop-in regression"
    assert re.search(r"pulseaudio\.socket-still-enabled", src), \
        "verification does not guard against pulseaudio.socket being enabled"
    assert re.search(r"pulseaudio\.service-still-enabled", src), \
        "verification does not guard against pulseaudio.service being enabled"
    assert re.search(r"AUDIO_MISSING.*\n.*exit 1", src, re.DOTALL), \
        "audio verification does not exit on failure"


def test_grub_and_efibootmgr_verification_still_present():
    """Don't let this refactor accidentally drop the grub/efibootmgr check
    from the prior audio-adjacent work on hybrid boot."""
    src = _build_source()
    assert re.search(r"grub-install.*efibootmgr|efibootmgr.*grub-install", src, re.DOTALL), \
        "boot tooling verification block missing"


def test_sof_firmware_and_ucm_in_apt_list():
    """Recommends-only packages --no-install-recommends would silently drop.
    Without intel/sof, DMIC laptops probe no sound card (HP 15-dy2xxx bug)."""
    src = _build_source()
    for pkg in ("firmware-sof-signed", "alsa-ucm-conf", "alsa-topology-conf"):
        assert re.search(rf"\b{pkg}\b", src), f"{pkg} not in apt install list"
    assert re.search(r"usr/share/alsa/ucm2", src), \
        "audio verification does not check UCM profiles landed"


def test_firmware_prune_keeps_and_guards_audio_gpu_dirs():
    """The keep list and the post-prune guard must share FIRMWARE_KEEP_DIRS,
    so a keep-list edit that drops a dir fails the build instead of shipping
    an ISO without it. radeon covers pre-2016 AMD GPUs/APUs on the radeon
    driver; intel/sof is the DSP audio firmware."""
    src = _build_source()
    m = re.search(r'FIRMWARE_KEEP_DIRS="([^"]+)"', src)
    assert m, "FIRMWARE_KEEP_DIRS not defined"
    kept = m.group(1).split()
    for dir_ in ("i915", "amdgpu", "nvidia", "radeon", "intel", "cirrus", "realtek"):
        assert dir_ in kept, f"{dir_} not in FIRMWARE_KEEP_DIRS"
    assert re.search(r"for dir in \$FIRMWARE_KEEP_DIRS intel/sof; do", src), \
        "post-prune guard does not iterate FIRMWARE_KEEP_DIRS plus intel/sof"
    assert "missing after prune" in src, "no post-prune firmware existence guard"
