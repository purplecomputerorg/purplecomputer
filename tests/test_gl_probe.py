"""purple-gl-probe safety contract: stdout is exactly "0" or "1", exit code is
always 0, and every failure mode lands on "1" (software GL, the pre-probe
behavior on all shipped machines). Build-script wiring for the probe lives in
tests/test_build_verifications.py."""
import os
import re
import subprocess
import time
import pytest
from pathlib import Path

REPO = Path(__file__).parent.parent
SCRIPT = REPO / "scripts" / "purple-gl-probe.sh"
XINITRC = REPO / "config" / "xinit" / "xinitrc"

HARDWARE_GLXINFO = """\
name of display: :0
display: :0  screen: 0
direct rendering: Yes
OpenGL vendor string: Intel
OpenGL renderer string: Mesa Intel(R) HD Graphics 620 (KBL GT2)
OpenGL core profile version string: 4.6 (Core Profile) Mesa 23.2.1
OpenGL version string: 4.6 (Compatibility Profile) Mesa 23.2.1
OpenGL ES profile version string: OpenGL ES 3.2 Mesa 23.2.1
"""


def hardware_variant(old, new):
    assert old in HARDWARE_GLXINFO
    return HARDWARE_GLXINFO.replace(old, new)


def stub_glxinfo(tmp_path, output=None, body=None):
    stub = tmp_path / "glxinfo"
    if body is None:
        body = f"cat << 'EOF'\n{output}EOF\n"
    stub.write_text("#!/usr/bin/env bash\n" + body)
    stub.chmod(0o755)
    return stub


def run_probe(tmp_path, glxinfo, timeout="5"):
    env = dict(
        os.environ,
        PURPLE_GL_PROBE_LOG=str(tmp_path / "probe.log"),
        PURPLE_GL_PROBE_CACHE=str(tmp_path / "gl-mode"),
        PURPLE_GL_FORCE_SOFTWARE_FLAG=str(tmp_path / "force-software-gl"),
        PURPLE_GL_PROBE_GLXINFO=str(glxinfo),
        PURPLE_GL_PROBE_TIMEOUT=timeout,
    )
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True,
                          text=True, env=env, timeout=30)


def assert_decision(result, tmp_path, mode, reason_fragment):
    assert result.returncode == 0
    assert result.stdout == mode + "\n"
    log = (tmp_path / "probe.log").read_text()
    assert reason_fragment in log.splitlines()[-1]
    assert (tmp_path / "gl-mode").read_text().strip() == mode


def test_hardware_gl_accepted(tmp_path):
    stub = stub_glxinfo(tmp_path, HARDWARE_GLXINFO)
    result = run_probe(tmp_path, stub)
    assert_decision(result, tmp_path, "0", "HD Graphics 620")


def test_llvmpipe_stays_software(tmp_path):
    output = hardware_variant("Mesa Intel(R) HD Graphics 620 (KBL GT2)",
                              "llvmpipe (LLVM 15.0.7, 256 bits)")
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, output))
    assert_decision(result, tmp_path, "1", "software anyway")


@pytest.mark.parametrize("renderer", [
    "virgl",
    "SVGA3D; build: RELEASE;  LLVM;",
    "VMware SVGA II Adapter",
    "VirtualBox Graphics Adapter",
    "Parallels Display Adapter",
])
def test_vm_renderers_stay_software(tmp_path, renderer):
    """Accelerated VMs pass direct rendering and GL version checks but must
    keep the shipped llvmpipe path (virgl and friends are flaky under real
    rendering, and the docs promise VMs are a no-op)."""
    output = hardware_variant("Mesa Intel(R) HD Graphics 620 (KBL GT2)", renderer)
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, output))
    assert_decision(result, tmp_path, "1", "VM renderer")


def test_glxinfo_missing(tmp_path):
    result = run_probe(tmp_path, tmp_path / "no-such-binary")
    assert_decision(result, tmp_path, "1", "not installed")


def test_glxinfo_crashes(tmp_path):
    stub = stub_glxinfo(tmp_path, body="echo 'Error: unable to open display' >&2\nexit 1\n")
    result = run_probe(tmp_path, stub)
    assert_decision(result, tmp_path, "1", "failed")


def test_glxinfo_term_immune_hang_abandoned(tmp_path):
    """A glxinfo wedged in a driver call can ignore SIGTERM; the probe must
    abandon it and answer software instead of hanging the session."""
    stub = stub_glxinfo(tmp_path, body="trap '' TERM\nsleep 20\n")
    start = time.monotonic()
    result = run_probe(tmp_path, stub, timeout="1")
    assert time.monotonic() - start < 10
    assert_decision(result, tmp_path, "1", "hung")


def test_garbage_output(tmp_path):
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, "not gl output at all\n"))
    assert_decision(result, tmp_path, "1", "no direct rendering")


def test_indirect_rendering_rejected(tmp_path):
    output = hardware_variant("direct rendering: Yes", "direct rendering: No")
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, output))
    assert_decision(result, tmp_path, "1", "no direct rendering")


def test_old_gl_version_rejected(tmp_path):
    output = hardware_variant("core profile version string: 4.6 (Core Profile)",
                              "core profile version string: 3.0 (Core Profile)")
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, output))
    assert_decision(result, tmp_path, "1", "below 3.3")


def test_gl_3_3_exactly_accepted(tmp_path):
    output = hardware_variant("core profile version string: 4.6 (Core Profile)",
                              "core profile version string: 3.3 (Core Profile)")
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, output))
    assert_decision(result, tmp_path, "0", "core profile 3.3")


def test_missing_core_profile_line_rejected(tmp_path):
    output = "\n".join(line for line in HARDWARE_GLXINFO.splitlines()
                       if "core profile" not in line) + "\n"
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, output))
    assert_decision(result, tmp_path, "1", "below 3.3")


def test_force_flag_wins_over_working_gl(tmp_path):
    (tmp_path / "force-software-gl").touch()
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, HARDWARE_GLXINFO))
    assert_decision(result, tmp_path, "1", "forced by")


def test_cached_decision_skips_reprobe(tmp_path):
    """Purple restarts re-exec xinitrc; the second probe must reuse the cached
    answer without consulting glxinfo (and without truncating the log)."""
    run_probe(tmp_path, stub_glxinfo(tmp_path, HARDWARE_GLXINFO))
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, body="exit 1\n"))
    assert result.stdout == "0\n"
    log = (tmp_path / "probe.log").read_text()
    assert "cached from earlier this boot" in log.splitlines()[-1]
    assert "HD Graphics 620" in log


def test_poisoned_cache_forces_software(tmp_path):
    """xinitrc writes 1 into the cache when Alacritty dies under hardware GL;
    the next probe must honor it over a passing glxinfo."""
    (tmp_path / "gl-mode").write_text("1\n")
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, HARDWARE_GLXINFO))
    assert result.stdout == "1\n"


def test_garbage_cache_ignored(tmp_path):
    (tmp_path / "gl-mode").write_text("banana\n")
    result = run_probe(tmp_path, stub_glxinfo(tmp_path, HARDWARE_GLXINFO))
    assert_decision(result, tmp_path, "0", "HD Graphics 620")


def test_xinitrc_wiring():
    """xinitrc must keep the session default on software, hard-validate the
    probe output, scope the probed mode to Alacritty, and poison the cache
    when Alacritty dies under hardware GL."""
    xinitrc = XINITRC.read_text()
    assert "export LIBGL_ALWAYS_SOFTWARE=1" in xinitrc
    assert re.search(r'GL_MODE=\$\(purple-gl-probe', xinitrc)
    assert 'case "$GL_MODE" in 0|1) ;; *) GL_MODE=1 ;; esac' in xinitrc
    assert re.search(r'LIBGL_ALWAYS_SOFTWARE="\$GL_MODE" alacritty', xinitrc)
    assert re.search(r'"\$ALACRITTY_EXIT" -ne 0[^\n]*\n\s*echo 1 > /tmp/purple-gl-mode', xinitrc)


def test_probe_log_path_consistent_across_consumers():
    """The log path is defined in three files; drift would point developers
    at a file that does not exist."""
    probe_default = re.search(r'PURPLE_GL_PROBE_LOG:-(\S+)}', SCRIPT.read_text()).group(1)
    assert probe_default == "/tmp/purple-gl-probe.log"
    assert probe_default in XINITRC.read_text()
    perf = (REPO / "scripts" / "on-device" / "log-performance.py").read_text()
    assert f'GL_PROBE_LOG = "{probe_default}"' in perf


def test_cache_path_consistent_across_consumers():
    probe_default = re.search(r'PURPLE_GL_PROBE_CACHE:-(\S+)}', SCRIPT.read_text()).group(1)
    assert probe_default == "/tmp/purple-gl-mode"
    assert f"echo 1 > {probe_default}" in XINITRC.read_text()
