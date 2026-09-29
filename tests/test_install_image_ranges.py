#!/usr/bin/env python3
"""install.sh reads the compressed image range by range against its manifest.

Staging fills a RAM copy before the disk is touched; streaming feeds the same
checked ranges to the write when there is no RAM for it. The real functions are
extracted from install.sh and run against small fake images, with ranges of
the primary or backup copy damaged, missing, or failing a few reads.
"""

import hashlib
import re
import subprocess
from pathlib import Path

INSTALL_SH = Path(__file__).parent.parent / 'build-scripts' / 'install.sh'
RANGE = 4096
IMAGE = bytes(range(256)) * 50  # 12800 bytes: three full ranges and a partial one


def _extract_function(name: str) -> str:
    match = re.search(rf'^{name}\(\).*?^\}}', INSTALL_SH.read_text(), re.M | re.S)
    assert match, f'{name}() not found in install.sh'
    return match.group(0)


def _setup(tmp_path, primary=IMAGE, backup=None, staged=None):
    (tmp_path / 'primary').write_bytes(primary)
    if backup is not None:
        (tmp_path / 'backup').write_bytes(backup)
    if staged is not None:
        (tmp_path / 'staged').write_bytes(staged)
    lines = [str(RANGE)] + [f'{hashlib.sha256(IMAGE[o:o + RANGE]).hexdigest()}  -'
                            for o in range(0, len(IMAGE), RANGE)]
    (tmp_path / 'manifest').write_text('\n'.join(lines) + '\n')


def _run(tmp_path, mode, flaky_range=None, flaky_fails=0):
    """Run image_ranges; flaky_range makes dd fail on that range's first flaky_fails reads."""
    counter = tmp_path / 'dd-count'
    script = f"""
set -eo pipefail
GOLDEN_IMAGE={tmp_path}/primary
BACKUP_IMAGE={tmp_path}/backup
MANIFEST={tmp_path}/manifest
STAGED_IMAGE={tmp_path}/staged
RANGE_TMP={tmp_path}/range
STAGE_PV=15
warn() {{ echo "[WARN] $1" >&2; }}
sleep() {{ :; }}
dd() {{
    case " $* " in *" skip={flaky_range} "*)
        n=$(cat {counter} 2>/dev/null || echo 0)
        echo $((n + 1)) > {counter}
        [ "$n" -ge {flaky_fails} ] || return 1 ;;
    esac
    command dd "$@"
}}
{_extract_function('read_range')}
{_extract_function('image_ranges')}
if [ {mode} = stream ]; then image_ranges stream > {tmp_path}/out; else image_ranges stage; fi
"""
    return subprocess.run(['bash', '-c', script], timeout=30, capture_output=True, text=True)


def _damage(data: bytes, offset: int) -> bytes:
    return data[:offset] + b'X' * 64 + data[offset + 64:]


def test_stage_reads_whole_image_into_ram(tmp_path):
    _setup(tmp_path)
    r = _run(tmp_path, 'stage')
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'staged').read_bytes() == IMAGE
    assert '[PURPLE-PV] 15' in r.stderr


def test_stream_prints_checked_image(tmp_path):
    _setup(tmp_path)
    r = _run(tmp_path, 'stream')
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'out').read_bytes() == IMAGE
    assert '[PURPLE-PV]' not in r.stderr  # the write's pv reports progress when streaming


def test_damaged_range_comes_from_the_backup(tmp_path):
    _setup(tmp_path, primary=_damage(IMAGE, 5000), backup=IMAGE)
    r = _run(tmp_path, 'stage')
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'staged').read_bytes() == IMAGE
    assert '[PURPLE-RETRY] range 1 from the backup copy' in r.stderr


def test_ranges_damaged_in_different_copies_combine(tmp_path):
    _setup(tmp_path, primary=_damage(IMAGE, 100), backup=_damage(IMAGE, 9000))
    r = _run(tmp_path, 'stream')
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'out').read_bytes() == IMAGE


def test_range_bad_everywhere_fails(tmp_path):
    _setup(tmp_path, primary=_damage(IMAGE, 5000), backup=_damage(IMAGE, 5000))
    r = _run(tmp_path, 'stage')
    assert r.returncode != 0
    assert 'Image range 1 could not be read from any copy' in r.stderr


def test_stick_that_drops_out_briefly_is_retried(tmp_path):
    _setup(tmp_path)
    r = _run(tmp_path, 'stage', flaky_range=2, flaky_fails=3)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'staged').read_bytes() == IMAGE


def test_stick_that_stays_unreadable_fails(tmp_path):
    _setup(tmp_path)
    r = _run(tmp_path, 'stage', flaky_range=2, flaky_fails=100)
    assert r.returncode != 0


def test_copy_from_the_boot_is_checked_and_only_bad_ranges_reread(tmp_path):
    # "try everything" staged a copy at boot with one range wrong; the stick's
    # primary is fine for that range but damaged elsewhere, so the other
    # ranges must have come from the staged copy.
    _setup(tmp_path, primary=_damage(_damage(IMAGE, 100), 9000), staged=_damage(IMAGE, 5000))
    r = _run(tmp_path, 'stage')
    assert r.returncode == 0, r.stderr
    assert (tmp_path / 'staged').read_bytes() == IMAGE


def test_install_reads_before_wiping_the_disk():
    text = INSTALL_SH.read_text()
    main = text[text.index('main() {'):]
    assert main.index('image_ranges stage') < main.index('wipefs -a')
    assert 'Nothing on this computer was changed' in main
