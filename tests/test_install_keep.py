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


def _carry(tmp_path, keep: bool):
    live = tmp_path / "live"
    (live / "saves/art").mkdir(parents=True)
    (live / "saves/art/1-a.json").write_text("{}")
    (live / "timeline").mkdir()
    (live / "timeline/art.jsonl").write_text("live\n")
    old = tmp_path / "keep/config"
    (old / "saves/art").mkdir(parents=True)
    (old / "saves/art/0-b.json").write_text("{}")
    (old / "timeline").mkdir()
    (old / "timeline/art.jsonl").write_text("old\n")
    root = tmp_path / "root"
    body = INSTALL_SH.read_text().split("if [ -n \"$PURPLE_KEEP_DIR\" ] && [ -d \"$PURPLE_KEEP_DIR/config\" ]; then", 1)[1]
    body = "if [ -n \"$PURPLE_KEEP_DIR\" ] && [ -d \"$PURPLE_KEEP_DIR/config\" ]; then" + body.split("\n            fi\n", 1)[0] + "\nfi\n"
    script = f"""
{_extract_function(INSTALL_SH, 'carry_over').replace('/mnt/root', str(root))}
log() {{ :; }}; warn() {{ echo "$@" >&2; }}; chown() {{ :; }}
PURPLE_LIVE_CONFIG="{live}"
PURPLE_KEEP_DIR="{tmp_path / 'keep' if keep else ''}"
{body}
"""
    subprocess.run(["bash", "-c", script], check=True)
    return root / "home/purple/.config/purple"


def test_keep_merges_saves_from_the_stick_but_keeps_the_laptops_history(tmp_path):
    cfg = _carry(tmp_path, keep=True)
    assert sorted(p.name for p in (cfg / "saves/art").iterdir()) == ["0-b.json", "1-a.json"]
    assert (cfg / "timeline/art.jsonl").read_text() == "old\n"


def test_fresh_install_brings_the_whole_live_session(tmp_path):
    cfg = _carry(tmp_path, keep=False)
    assert [p.name for p in (cfg / "saves/art").iterdir()] == ["1-a.json"]
    assert (cfg / "timeline/art.jsonl").read_text() == "live\n"
