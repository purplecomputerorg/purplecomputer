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
    assert re.search(r"\bpulseaudio-utils\b", src), "pulseaudio-utils not in apt install list"
    assert re.search(r'command -v pactl >/dev/null" \|\| AUDIO_MISSING=', src), \
        "pactl (the runtime volume backend) is not verified"
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


def test_x11_failure_screen_is_an_onfailure_unit():
    """As an ExecStopPost the failure screen was killed by TimeoutStopSec=10
    while it waited for Enter, so 'press Enter to show details' did nothing.
    OnFailure= fires once, after the restart burst, with no stop timeout."""
    unit = (ROOT / "config" / "systemd" / "purple-x11.service").read_text()
    assert re.search(r"^OnFailure=purple-x11-failed\.service$", unit.split("[Service]", 1)[0], re.M), \
        "purple-x11.service does not trigger purple-x11-failed.service on failure"
    assert "ExecStopPost=" not in unit, "failure screen is still an ExecStopPost"
    failed = (ROOT / "config" / "systemd" / "purple-x11-failed.service").read_text()
    assert re.search(r"^ExecStart=/usr/local/bin/purple-x11-failed$", failed, re.M)
    assert re.search(r"^TTYPath=/dev/tty1$", failed, re.M), "failure screen does not own tty1"
    assert re.search(r'cp /purple-src/config/systemd/purple-x11-failed\.service ', _build_source()), \
        "purple-x11-failed.service not copied into the image"
    script = (ROOT / "scripts" / "purple-x11-failed.sh").read_text()
    assert "SERVICE_RESULT" not in script and "FAIL_COUNT_FILE" not in script, \
        "failure script still carries ExecStopPost bookkeeping"


def test_runtime_deps_ubuntu_carries_implicitly_are_explicit():
    """Debian only Recommends a system bus and the login PAM module; Ubuntu's
    base set installs them. The i386 image shipped without either, so rootless
    X had no logind session and 'open /dev/dri/card0: Permission denied'.
    Each must be both installed and verified at build time."""
    src = _build_source()
    for pkg in ("dbus", "libpam-systemd", "procps"):
        assert re.search(rf"^\s+[\w\- ]*\b{pkg}\b[\w\- ]*\\$", src, re.M), f"{pkg} not in apt install list"
    check = re.search(r'for cmd in (.*?); do\n\s+chroot "\$MOUNT_DIR" bash -c "command -v \$cmd', src, re.DOTALL)
    assert check, "runtime tooling verification loop missing"
    for cmd in ("dbus-daemon", "pgrep", "startx", "xset", "xrandr", "pactl", "lsblk", "udevadm"):
        assert re.search(rf"\b{cmd}\b", check.group(1)), f"{cmd} not verified at build time"
    assert "pam_systemd.so" in src and "dbus.socket" in src, \
        "logind PAM module and dbus socket unit not verified at build time"


def test_i386_image_disables_glamor():
    """Intel 945 (the Atom netbook GPU) reports 64 shader instructions, glamor
    needs 128, and modesetting fails X outright rather than falling back."""
    src = _build_source()
    m = re.search(r'\[ "\$PURPLE_ARCH" = "amd64" \] \|\| sed -i \'(.*?)\'', src)
    assert m, "i386 AccelMethod override missing"
    assert 'Option     "AccelMethod" "none"' in m.group(1)
    conf = (ROOT / "config" / "xorg" / "10-modesetting.conf").read_text()
    assert "AccelMethod" not in conf, "amd64 keeps glamor for picom's glx backend"


def test_compositor_skips_the_32bit_image():
    """Without glamor there is no hardware GL, so picom on the Atom would be
    llvmpipe compositing every frame for nothing."""
    launcher = (ROOT / "scripts" / "purple-start-compositor.sh").read_text()
    assert re.search(r'case "\$\(uname -m\)" in i\?86\).*exit 0', launcher)


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


def test_boot_timing_timeline_is_seconds_since_boot(tmp_path):
    """On a live USB the report has to fit one photo, so the boot log's
    wall-clock stamps come out as offsets from kernel start, only the lines
    that bound a startup phase, and without the per-line prefixes."""
    import os
    import subprocess
    from datetime import datetime, timedelta
    boot = datetime.now() - timedelta(seconds=float(Path("/proc/uptime").read_text().split()[0]))
    stamp = lambda offset: (boot + timedelta(seconds=offset)).strftime("%H:%M:%S.%f")[:-3]
    log = tmp_path / "boot.log"
    log.write_text(
        f"[{stamp(9)}] [wait-display] === purple-wait-display started === kernel=6.8\n"
        f"[{stamp(9.5)}] [wait-display]   connector at start: card0-eDP-1 = connected\n"
        f"[{stamp(12)}] [xinitrc] === xinitrc started ===  debug_flag=no\n"
        f"[{stamp(13)}] [xinitrc] Caching squashfs for USB safety...\n"
        f"[{stamp(14)}] [launcher] exec python3 -m purple_tui\n"
        f"[{stamp(14.2)}] [+ 0.010s] [python] watchdog armed\n"
        f"[{stamp(95)}] [+80.810s] [python] PurpleApp.__init__ begin\n"
        f"[{stamp(100)}] [+85.810s] [python] first render reached; watchdog disarmed\n"
    )
    out = subprocess.run(["bash", str(ROOT / "scripts" / "purple-boot-timing.sh"), "--timeline"],
                         env={**os.environ, "PURPLE_BOOT_LOG": str(log)},
                         capture_output=True, text=True, check=True).stdout
    lines = out.splitlines()
    assert "connector at start" not in out
    offsets = [float(re.match(r"\s*(-?\d+\.\d)s  ", line).group(1)) for line in lines]
    for got, want in zip(offsets, [9, 12, 13, 14, 14.2, 95, 100], strict=True):
        assert abs(got - want) <= 2, (got, want, out)
    assert lines[-1].endswith("s  [python] first render reached; watchdog disarmed")


def test_audio_probe_tool_ships():
    """purple-audio-probe is the hands-on loudness diagnostic (mic loopback at
    three steps, speech-model timing); it only helps if it is on the image."""
    src = _build_source()
    assert re.search(r'cp /purple-src/scripts/purple-audio-probe\.sh\b', src), \
        "purple-audio-probe.sh not copied into the image"
    assert re.search(r'chmod \+x "\$MOUNT_DIR/usr/local/bin/purple-audio-probe"', src), \
        "purple-audio-probe not made executable"


def _installed_grub_cfg_block() -> str:
    """The heredoc that becomes the installed system's /boot/grub/grub.cfg."""
    src = _build_source()
    m = re.search(
        r'cat > "\$MOUNT_DIR/boot/grub/grub\.cfg" <<\'EOF\'\n(.*?)\nEOF\n',
        src, re.DOTALL)
    assert m, "installed grub.cfg heredoc not found"
    return m.group(1)


def test_initrd_lean_hook_prunes_modules_and_firmware():
    """The shipped initrd carried 44MB of .ko.zst modules and firmware for
    hardware classes the rootfs prune already removes (Mellanox switch fw,
    NetXen 10GbE...), in an UNCOMPRESSED early cpio that slow pre-kernel
    loaders read at ~0.5MB/s. The first version of this hook targeted nvidia
    firmware the golden initrd never contained and shipped as a silent no-op,
    so these assertions pin the mechanism, not just the file's existence:
    net-class + gpu module pruning, unreferenced-firmware pruning, and a
    fail-loudly artifact check. See docs/PLAN-macbook5-slow-boot.md."""
    src = _build_source()
    hook = re.search(
        r'cat > "\$MOUNT_DIR/etc/initramfs-tools/hooks/zzz-purple-lean-initrd" <<\'LEANINITRD\'\n(.*?)\nLEANINITRD\n',
        src, re.DOTALL)
    assert hook, "lean-initrd initramfs hook not written"
    body = hook.group(1)
    for d in ("kernel/drivers/net", "kernel/drivers/bluetooth", "kernel/net/wireless",
              "kernel/drivers/gpu", "kernel/drivers/infiniband"):
        assert d in body, f"hook no longer prunes {d} from the initrd"
    assert re.search(r'rm -rf "\$DESTDIR/usr/lib/firmware/nvidia"', body), \
        "hook does not remove nvidia firmware (MODULES=dep regen trap)"
    assert "modinfo -F firmware" in body and "grep -qxF" in body, \
        "hook lost the unreferenced-firmware prune (firmware without its module)"
    assert "depmod -b" in body, "hook does not refresh module deps"
    assert re.search(r'chmod \+x "\$MOUNT_DIR/etc/initramfs-tools/hooks/zzz-purple-lean-initrd"', src), \
        "lean-initrd hook not made executable"
    assert src.index("zzz-purple-lean-initrd") < src.index('update-initramfs -u -k "$KVER"'), \
        "hook written after the initrd rebuild it must influence"
    assert re.search(
        r"lsinitramfs .*grep -qE 'kernel/drivers/net/\|kernel/drivers/gpu/\|firmware/nvidia/\|firmware/mellanox/'",
        src, re.DOTALL), \
        "no fail-loudly artifact check that the initrd is actually lean"


def test_installed_grub_derives_root_from_the_boot_device():
    """`search` probes every block device; an empty optical drive under Apple
    EFI made that cost 47s per boot, and a fixed (hd0,gpt2) pin missed on 13"
    MacBook Airs, where a media-less SD reader takes hd0 (the miss printed an
    error and paused GRUB 10s). The config must derive the root partition from
    the device GRUB itself was loaded from and keep `search` ONLY as the
    fallback, with no error-printing test in a menuentry."""
    cfg = _installed_grub_cfg_block()
    head = cfg.split("menuentry", 1)[0]
    assert re.search(r'regexp --set=1:purple_disk \'\^\(\[\^,\]\+\)\' "\$root"', head), \
        "root disk not derived from $root"
    assert "set root=($purple_disk,gpt2)" in head, "root not set to gpt2 of the boot disk"
    assert re.search(
        r"if \[ ! -f /boot/vmlinuz \]; then\s*\n\s*search --no-floppy --file /boot/vmlinuz --set=root",
        head), "fallback search missing or unguarded"
    assert "--label" not in cfg and "fs-uuid" not in cfg, "config still searches by label/uuid"
    assert "source /boot/grub/purple-cmdline.cfg" in head and "source /boot/grub/purple-router.cfg" in head
    entries = re.findall(r'menuentry [^\n]*\{\n(.*?)\n\}', cfg, re.DOTALL)
    assert len(entries) == 2, f"expected 2 menuentries, found {len(entries)}"
    for entry in entries:
        assert "search" not in entry and "[ " not in entry, \
            "menuentry runs a command that can print an error (10s pause before boot)"
        assert "$purple_root_arg" in entry, "menuentry does not use the shared root= argument"
    assert "echo \"Starting Purple Computer...\"" in entries[0], "no on-screen sign of life before the slow reads"
    assert "$purple_cmdline" in entries[0]


def test_grub_config_is_one_file_for_esp_and_bios():
    """UEFI reads /EFI/ubuntu/grub.cfg (signed GRUB's prefix), BIOS reads
    /boot/grub/grub.cfg. They must be byte-identical copies of one heredoc:
    a second hand-written ESP config is how the label search survived."""
    src = _build_source()
    assert re.search(r'cp "\$MOUNT_DIR/boot/grub/grub\.cfg" "\$MOUNT_DIR/boot/efi/EFI/ubuntu/grub\.cfg"', src), \
        "ESP grub.cfg is not a copy of the root one"
    assert src.count('cat > "$MOUNT_DIR/boot/efi/EFI/ubuntu/grub.cfg"') == 0, \
        "a separate ESP grub.cfg heredoc is back"
    cmdline = re.search(
        r'cat > "\$MOUNT_DIR/boot/grub/purple-cmdline\.cfg" <<\'EOF\'\n(.*?)\nEOF\n', src, re.DOTALL)
    assert cmdline, "purple-cmdline.cfg heredoc missing"
    body = cmdline.group(1)
    assert 'set purple_root_arg="root=LABEL=PURPLE_ROOT"' in body
    assert re.search(r'^set purple_cmdline="ro loglevel=3 .*console=tty2 .*vt\.default_blu=', body, re.M), \
        "kernel command line lost its console/colour settings"
    assert re.search(r"cp /purple-src/config/grub/purple-router\.cfg /purple-src/config/grub/purple-variants\.cfg", src), \
        "router or variants file not copied into /boot/grub"


def _install_source() -> str:
    return (ROOT / "build-scripts" / "install.sh").read_text()


def test_install_rewrites_root_arg_in_the_shared_cmdline_file():
    """Layer 5 used to sed two grub.cfg copies for two patterns each; the
    root= argument now has exactly one home, sourced by both copies and read
    by the UKI build."""
    src = _install_source()
    assert re.search(r'sed -i "s\|root=LABEL=PURPLE_ROOT\|\$\(root_arg\)\|" /mnt/root/boot/grub/purple-cmdline\.cfg', src), \
        "root= rewrite does not target purple-cmdline.cfg"
    assert "search --no-floppy --label" not in src, "install.sh still rewrites a label search"
    assert "root=LABEL=PURPLE_ROOT|root=UUID" not in src, "old grub.cfg sed is back"


def test_install_builds_a_uki_for_macs_with_grub_as_fallback():
    """Macs boot a unified kernel image the firmware loads itself (Layer 7):
    Apple EFI reads files through GRUB at well under 1 MB/s on 2009-2010
    models. Gated on Apple + 64-bit UEFI + Secure Boot off, built from the same
    kernel choice and command line as GRUB, and shim stays the next NVRAM entry."""
    src = _install_source()
    gate = re.search(r"uki_wanted\(\) \{\n(.*?)\n\}", src, re.DOTALL)
    assert gate, "uki_wanted missing"
    g = gate.group(1)
    assert "/sys/class/dmi/id/sys_vendor" in g and "'^Apple'" in g
    assert "fw_platform_size" in g and '"64"' in g
    assert "SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c" in g
    build = re.search(r"build_uki\(\) \{\n(.*?)\n\}", src, re.DOTALL)
    assert build, "build_uki missing"
    b = build.group(1)
    assert "/boot/grub/purple-variants.cfg" in b and "/boot/grub/purple-cmdline.cfg" in b, \
        "UKI does not share the router data and command line"
    assert "=~ $purple_t2_models" in b and 'args="$purple_t2_args"' in b
    assert re.search(r'--cmdline "\$\{args:\+\$args \}\$\(root_arg\) \$purple_cmdline"', b)
    assert "linuxx64.efi.stub" in b
    assert "build_uki /mnt/efi/EFI/purple/purple.efi" in src
    assert re.search(r"nvram_entry \"PurpleOS\" \"\$UKI_LOADER\"", src), "UKI is not the primary NVRAM entry"
    assert re.search(r"nvram_entry \"\$GRUB_LABEL\" '\\EFI\\purple\\shimx64\.efi'", src), \
        "shim entry no longer created"
    build_src = _build_source()
    assert re.search(r'ARCH_PKGS="casper systemd-hwe-hwdb systemd-ukify systemd-boot-efi"', build_src), \
        "ukify and the systemd-boot stub are not in the image"
    assert "UKI_CMDS=ukify" in build_src and "linuxx64.efi.stub" in build_src, \
        "build does not verify ukify and the stub landed"


def test_variants_file_is_the_single_source_for_router_and_installer():
    variants = (ROOT / "config" / "grub" / "purple-variants.cfg").read_text()
    for line in variants.splitlines():
        if line and not line.startswith("#"):
            assert re.match(r"^set purple_[a-z0-9_]+=", line), f"not eval-safe for bash: {line}"
    assert "set purple_t2_models=" in variants and "set purple_t2_args=" in variants
    router = (ROOT / "config" / "grub" / "purple-router.cfg").read_text()
    assert "source /boot/grub/purple-variants.cfg" in router
    assert 'regexp "$purple_t2_models" "$product"' in router
    assert 'set purple_args="$purple_t2_args"' in router
    assert "MacBookPro1[56]" not in router, "T2 model list duplicated in the router"
    for path in ("scripts/test-grub-router.sh", "build-scripts/01-remaster-iso.sh"):
        assert "purple-variants.cfg" in (ROOT / path).read_text(), f"{path} does not ship the variants file"


def test_i386_kernel_reports_lid_open_at_boot():
    """The Atom netbooks' firmware can report the lid closed until it is moved,
    which starts the 10 min lid shutdown right after boot."""
    cfg = (ROOT / "config" / "grub" / "purple-router.cfg").read_text()
    i386_branch = re.search(r"set purple_variant=-i386\n(.*?)\n\s*fi", cfg, re.DOTALL)
    assert i386_branch, "i386 branch missing"
    assert 'set purple_args="$purple_i386_args"' in i386_branch.group(1)
    variants = (ROOT / "config" / "grub" / "purple-variants.cfg").read_text()
    assert 'set purple_i386_args="button.lid_init_state=open"' in variants
