#!/usr/bin/env python3
"""Tests for swap deactivation during install.

Active swap on the target disk (activated by casper's 13swap at live boot)
makes the kernel hold the old partition table, so install.sh's repartition
step fails with "Partition(s) ... are being used". Two-part fix:
- install.sh: disable_swaps_on() swapoffs the target disk's swap first
- 01-remaster-iso.sh: neuter_casper_swap() blanks 13swap in the initrd

Both bash functions are extracted from the real scripts and run against
fakes, so these tests can't drift out of sync with the shipped code.

Run with: pytest tests/test_install_swap.py -v
"""

import re
import subprocess
from pathlib import Path

BUILD_SCRIPTS = Path(__file__).parent.parent / 'build-scripts'
INSTALL_SH = BUILD_SCRIPTS / 'install.sh'
REMASTER_SH = BUILD_SCRIPTS / '01-remaster-iso.sh'

SWAPS_HEADER = 'Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n'


def _extract_function(script: Path, name: str) -> str:
    match = re.search(rf'^{name}\(\).*?^\}}', script.read_text(), re.M | re.S)
    assert match, f'{name}() not found in {script.name}'
    return match.group(0)


def _run_disable_swaps(tmp_path, swap_lines, disk, stuck=()):
    """Run the real disable_swaps_on with stubbed log/swapoff.

    Returns (exit_code, list of devices swapoff was called with).
    """
    swaps = tmp_path / 'swaps'
    swaps.write_text(SWAPS_HEADER + ''.join(f'{d} partition 1000 0 -2\n' for d in swap_lines))
    calls = tmp_path / 'calls'
    calls.touch()
    script = f"""
{_extract_function(INSTALL_SH, 'disable_swaps_on')}
log() {{ :; }}
swapoff() {{
    echo "$1" >> "{calls}"
    case " {' '.join(stuck)} " in *" $1 "*) return 1 ;; esac
}}
disable_swaps_on "{disk}" "{swaps}"
"""
    result = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True, text=True)
    return result.returncode, calls.read_text().split()


def test_deactivates_swap_on_target_only(tmp_path):
    rc, calls = _run_disable_swaps(tmp_path, ['/dev/sda5', '/dev/sdb1'], '/dev/sda')
    assert rc == 0
    assert calls == ['/dev/sda5']


def test_whole_disk_swap_deactivated(tmp_path):
    rc, calls = _run_disable_swaps(tmp_path, ['/dev/sda'], '/dev/sda')
    assert rc == 0
    assert calls == ['/dev/sda']


def test_nvme_partition_naming(tmp_path):
    rc, calls = _run_disable_swaps(tmp_path, ['/dev/nvme0n1p5'], '/dev/nvme0n1')
    assert rc == 0
    assert calls == ['/dev/nvme0n1p5']


def test_similar_disk_name_not_matched(tmp_path):
    rc, calls = _run_disable_swaps(tmp_path, ['/dev/sdab1'], '/dev/sda')
    assert rc == 0
    assert calls == []


def test_no_swap_active(tmp_path):
    rc, calls = _run_disable_swaps(tmp_path, [], '/dev/sda')
    assert rc == 0
    assert calls == []


def test_failed_swapoff_reports_failure(tmp_path):
    rc, calls = _run_disable_swaps(tmp_path, ['/dev/sda5'], '/dev/sda', stuck=['/dev/sda5'])
    assert rc != 0
    assert calls == ['/dev/sda5']


def test_install_calls_disable_swaps_before_repartition():
    src = INSTALL_SH.read_text()
    call = src.index('disable_swaps_on "/dev/$TARGET"')
    assert call < src.index('mklabel gpt'), 'swap must be off before the partition table rebuild'
    assert '|| error' in src[call:call + 120], 'a stuck swapoff must abort the install'


def _run_neuter(tmp_path, with_script):
    main_dir = tmp_path / 'main'
    swap_script = main_dir / 'scripts/casper-bottom/13swap'
    if with_script:
        swap_script.parent.mkdir(parents=True)
        swap_script.write_text('#!/bin/sh\nswapon /dev/sda5\n')
        swap_script.chmod(0o755)
    script = f"""
{_extract_function(REMASTER_SH, 'neuter_casper_swap')}
log_info() {{ :; }}
neuter_casper_swap "{main_dir}"
"""
    result = subprocess.run(['bash', '-c', script], timeout=10, capture_output=True, text=True)
    return result.returncode, swap_script


def test_neuter_blanks_13swap_keeping_it_executable(tmp_path):
    rc, swap_script = _run_neuter(tmp_path, with_script=True)
    assert rc == 0
    assert swap_script.read_text() == '#!/bin/sh\nexit 0\n'
    assert swap_script.stat().st_mode & 0o111, '13swap must stay executable (ORDER still runs it)'


def test_neuter_tolerates_missing_13swap(tmp_path):
    rc, _ = _run_neuter(tmp_path, with_script=False)
    assert rc == 0


def test_remaster_calls_neuter_before_repack():
    src = REMASTER_SH.read_text()
    assert src.index('neuter_casper_swap "$MAIN_DIR"') < src.index('Repacking initramfs')
