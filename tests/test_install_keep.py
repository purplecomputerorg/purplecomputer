"""install.sh's save_old_purple(), extracted from the real script and run
against a fake root partition, so a reinstall keeps settings and Time Travel
history only when the old Purple install could be read in full."""

import subprocess

from tests.test_install_swap import INSTALL_SH, _extract_function


def _save(tmp_path, label="PURPLE_ROOT", mount_ok=True):
    root = tmp_path / "oldroot"
    (root / "home/purple/.config/purple/timeline").mkdir(parents=True)
    (root / "home/purple/.config/purple/timeline/art.jsonl").write_text('{"s": {}}\n')
    (root / "home/purple/.config/purple/settings.json").write_text("{}")
    (root / "opt/purple").mkdir(parents=True)
    (root / "opt/purple/computer_name.txt").write_text("Sam's Purple")
    keep = tmp_path / "keep"
    script = f"""
{_extract_function(INSTALL_SH, 'save_old_purple')}
blkid() {{ echo "{label}"; }}
mount() {{ {'cp -a "' + str(root) + '/." "$4"' if mount_ok else 'return 32'}; }}
umount() {{ :; }}
save_old_purple /dev/fake2 "{keep}" "{tmp_path / 'mnt'}"
"""
    return subprocess.run(["bash", "-c", script]).returncode, keep


def test_saves_settings_history_and_name(tmp_path):
    rc, keep = _save(tmp_path)
    assert rc == 0
    assert (keep / "config/timeline/art.jsonl").read_text() == '{"s": {}}\n'
    assert (keep / "config/settings.json").exists()
    assert (keep / "computer_name.txt").read_text() == "Sam's Purple"


def test_other_os_is_not_purple(tmp_path):
    rc, keep = _save(tmp_path, label="Windows")
    assert rc == 1 and not keep.exists()


def test_unreadable_purple_keeps_nothing(tmp_path):
    rc, keep = _save(tmp_path, mount_ok=False)
    assert rc == 2 and not any(keep.glob("**/*"))
