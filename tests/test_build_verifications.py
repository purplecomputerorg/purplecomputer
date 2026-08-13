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


def test_gl_probe_ships_and_glxinfo_is_verified():
    """The GL probe needs glxinfo (mesa-utils) in the image; if either quietly
    vanishes, every machine silently falls back to software rendering. The
    build must install both and keep glxinfo in the fail-loudly verify loop
    (a comment mentioning glxinfo must not satisfy this)."""
    src = _build_source()
    assert re.search(r"^\s*mesa-utils \\$", src, re.M), \
        "mesa-utils not in apt install list"
    assert re.search(r'cp /purple-src/scripts/purple-gl-probe\.sh\b', src), \
        "purple-gl-probe.sh not copied into the image"
    assert re.search(r'chmod \+x "\$MOUNT_DIR/usr/local/bin/purple-gl-probe"', src), \
        "purple-gl-probe not made executable"
    assert re.search(r"for cmd in [^\n]*\bglxinfo\b", src), \
        "glxinfo not in the fail-loudly tooling verification loop"


def test_x11_service_start_limit_keys_are_in_unit_section():
    """StartLimitIntervalSec/StartLimitBurst are [Unit] keys. Under [Service]
    systemd logs 'Unknown key name ... ignoring' and the restart rate limit is
    inert, so X restarts forever instead of reaching purple-x11-failed."""
    unit = (ROOT / "config" / "systemd" / "purple-x11.service").read_text()
    before_service = unit.split("[Service]", 1)[0]
    for key in ("StartLimitIntervalSec", "StartLimitBurst"):
        assert re.search(rf"^{key}=", before_service, re.M), f"{key} not in [Unit]"
        assert not re.search(rf"^{key}=", unit.split("[Service]", 1)[1], re.M), \
            f"{key} still under [Service]"


def test_boot_timing_tool_ships():
    """The pre-kernel boot investigation depends on this being on the image;
    it is the only way to measure seek latency and file fragmentation on a
    customer machine. See docs/PLAN-macbook5-slow-boot.md."""
    src = _build_source()
    assert re.search(r'cp /purple-src/scripts/purple-boot-timing\.sh\b', src), \
        "purple-boot-timing.sh not copied into the image"
    assert re.search(r'chmod \+x "\$MOUNT_DIR/usr/local/bin/purple-boot-timing"', src), \
        "purple-boot-timing not made executable"
    assert re.search(r"^\s*smartmontools \\$", src, re.M), \
        "smartmontools not in apt install list (SMART check silently skips)"


def _installed_grub_cfg_block() -> str:
    """The heredoc that becomes the installed system's /boot/grub/grub.cfg."""
    src = _build_source()
    m = re.search(
        r'cat > "\$MOUNT_DIR/boot/grub/grub\.cfg" <<\'EOF\'\n(.*?)\nEOF\n',
        src, re.DOTALL)
    assert m, "installed grub.cfg heredoc not found"
    return m.group(1)


def test_initrd_excludes_nouveau_and_nvidia_firmware():
    """The nvidia GSP blobs are 44MB of *uncompressed* early-cpio payload that
    slow pre-kernel loaders read on every boot (90+ seconds on Apple EFI SATA).
    The lean-gpu hook must remove the nouveau module TOGETHER with the firmware,
    so no NVIDIA card ever probes firmware-less from the initrd: nouveau loads
    post-pivot from the real filesystem instead. See PLAN-macbook5-slow-boot."""
    src = _build_source()
    hook = re.search(
        r'cat > "\$MOUNT_DIR/etc/initramfs-tools/hooks/zzz-purple-lean-gpu" <<\'LEANGPU\'\n(.*?)\nLEANGPU\n',
        src, re.DOTALL)
    assert hook, "lean-gpu initramfs hook not written"
    body = hook.group(1)
    assert re.search(r"find .*modules.* -name 'nouveau\.ko\*' -delete", body), \
        "hook does not remove the nouveau module (firmware-less probe risk on NVIDIA)"
    assert re.search(r'rm -rf "\$DESTDIR/usr/lib/firmware/nvidia"', body), \
        "hook does not remove nvidia firmware"
    assert "depmod -b" in body, "hook does not refresh module deps"
    assert re.search(r'chmod \+x "\$MOUNT_DIR/etc/initramfs-tools/hooks/zzz-purple-lean-gpu"', src), \
        "lean-gpu hook not made executable"
    # Hook must exist before the initrd rebuild, and the rebuild must be verified.
    assert src.index("zzz-purple-lean-gpu") < src.index('update-initramfs -u -k "$KVER"'), \
        "hook written after the initrd rebuild it must influence"
    assert re.search(r"lsinitramfs .*\|.*grep -qE 'firmware/nvidia/\|/nouveau\\\.ko'", src), \
        "no fail-loudly check that the initrd is actually lean"


def test_installed_grub_pins_root_with_search_fallback():
    """`search --label` probes every block device; an empty optical drive under
    Apple EFI made that cost 47s per boot. The installed grub.cfg must pin
    root to the fixed layout (p2) and keep `search` ONLY as the fallback for
    wrong hd numbering: a pin without fallback is an unbootable machine, a
    fallback without pin is the 47s again."""
    cfg = _installed_grub_cfg_block()
    fn = re.search(r"function purple_set_root \{\n(.*?)\n\}", cfg, re.DOTALL)
    assert fn, "purple_set_root function missing from installed grub.cfg"
    body = fn.group(1)
    assert re.search(r"set root=\(hd0,gpt2\)", body), "root not pinned to (hd0,gpt2)"
    assert re.search(
        r"if \[ ! -f /boot/vmlinuz \]; then\s*\n\s*search --no-floppy --label PURPLE_ROOT --set=root",
        body), "fallback search missing or not guarded by the pin check"
    # Both menuentries use the function; no entry searches unconditionally.
    entries = re.findall(r'menuentry [^\n]*\{\n(.*?)\n\}', cfg, re.DOTALL)
    assert len(entries) == 2, f"expected 2 menuentries, found {len(entries)}"
    for entry in entries:
        assert "purple_set_root" in entry, "menuentry does not call purple_set_root"
        assert "search --no-floppy" not in entry, \
            "menuentry still searches unconditionally"
    assert cfg.count("search --no-floppy --label PURPLE_ROOT") == 1, \
        "search should appear exactly once: as the fallback inside purple_set_root"
