"""install.sh's probe and carry-over, extracted from the real script and run against a
fake root partition: what it finds on the laptop, and what each choice copies.
Every permutation: guides/updating-purple.md."""

import subprocess

import pytest

from tests.test_install_swap import INSTALL_SH, _extract_function


def _save(tmp_path, label="PURPLE_ROOT", mount_ok=True, home_name="Sam's Computer", probe=False,
          work=("timeline/art.jsonl",), config=True, version="v1.2\n", stale=False, disk=True):
    root = tmp_path / "oldroot"
    cfg = root / "home/purple/.config/purple"
    if config:
        (cfg / "timeline").mkdir(parents=True, exist_ok=True)
        (cfg / "settings.json").write_text("{}")
    for path in work:
        (cfg / path).parent.mkdir(parents=True, exist_ok=True)
        (cfg / path).write_text('{"s": {}}\n')
    if version:
        (root / "etc").mkdir(parents=True)
        (root / "etc/purple-version").write_text(version)
    (root / "opt/purple").mkdir(parents=True)
    (root / "opt/purple/computer_name.txt").write_text("Sam's Purple")
    (root / "home/purple/.purple/packs/dinos").mkdir(parents=True)
    (root / "home/purple/.purple/packs/dinos/manifest.json").write_text("{}")
    if home_name:
        (root / "home/purple/.purple/computer_name.txt").write_text(home_name)
    (root / "home/purple/.purple/cache/tts").mkdir(parents=True)
    (root / "home/purple/.purple/cache/tts/a.wav").write_text("x")
    keep = tmp_path / "keep"
    if stale:  # left by an earlier probe
        (keep / "config/saves/art").mkdir(parents=True)
        (keep / "config/saves/art/stale.json").write_text("{}")
    script = f"""
{_extract_function(INSTALL_SH, 'save_old_purple').replace('/run/purple-old-root', str(tmp_path / 'mnt'))}
{_extract_function(INSTALL_SH, 'probe')}
find_target() {{ {'echo fake' if disk else 'return 1'}; }}; part_prefix() {{ echo /dev/fake; }}
KEEP_DIR="{keep}"
blkid() {{ echo "{label}"; }}
mount() {{ {'cp -a "' + str(root) + '/." "$4"' if mount_ok else 'return 32'}; }}
umount() {{ :; }}
set -o pipefail
{'(probe)' if probe else f'save_old_purple /dev/fake2 "{keep}" "{tmp_path / 'mnt'}"'}
"""
    result = subprocess.run(["bash", "-c", script], capture_output=probe, text=True)
    return (result.stdout if probe else result.returncode), keep


def test_saves_settings_history_and_name(tmp_path):
    rc, keep = _save(tmp_path)
    assert rc == 0
    assert (keep / "config/timeline/art.jsonl").read_text() == '{"s": {}}\n'
    assert (keep / "config/settings.json").exists()
    assert (keep / "computer_name.txt").read_text() == "Sam's Purple"


def test_saves_packs_and_renamed_name_but_not_the_tts_cache(tmp_path):
    rc, keep = _save(tmp_path)
    assert rc == 0
    assert (keep / ".purple/packs/dinos/manifest.json").exists()
    assert (keep / ".purple/computer_name.txt").read_text() == "Sam's Computer"
    assert not (keep / ".purple/cache").exists()


def test_probe_names_the_old_install_once(tmp_path):
    assert _save(tmp_path, probe=True)[0] == "[PURPLE-FOUND] Sam's Computer\n"


@pytest.mark.parametrize("work,tag", [
    (["timeline/art.jsonl"], "FOUND"),
    (["saves/art/1-a.json"], "FOUND"),
    (["kids/leo/timeline/art.jsonl"], "FOUND"),    # only a second kid played
    (["kids/leo/saves/art/1-a.json"], "FOUND"),
    ([], "EMPTY"),                                 # Purple that was set up but never played
    (["display.json", "saves/art/notes.txt"], "EMPTY"),
])
def test_probe_says_whether_the_laptop_has_the_kids_work(tmp_path, work, tag):
    assert _save(tmp_path, probe=True, work=work)[0] == f"[PURPLE-{tag}] Sam's Computer\n"


def test_probe_finds_a_v1_laptop_with_only_settings_or_none_at_all(tmp_path):
    assert _save(tmp_path / "a", probe=True, work=["settings.json"])[0] == "[PURPLE-EMPTY] Sam's Computer\n"
    assert _save(tmp_path / "b", probe=True, work=[], config=False)[0] == "[PURPLE-EMPTY] Sam's Computer\n"


def test_saves_the_laptops_version_when_it_has_one(tmp_path):
    assert (_save(tmp_path / "a")[1] / "purple-version").read_text() == "v1.2\n"
    rc, keep = _save(tmp_path / "b", version=None)
    assert rc == 0 and not (keep / "purple-version").exists()


def test_probe_falls_back_to_the_install_time_name(tmp_path):
    assert _save(tmp_path, home_name=None, probe=True)[0] == "[PURPLE-FOUND] Sam's Purple\n"


def test_other_os_is_not_purple(tmp_path):
    rc, keep = _save(tmp_path, label="Windows")
    assert rc == 1 and not keep.exists()


def test_unreadable_purple_keeps_nothing(tmp_path):
    rc, keep = _save(tmp_path, mount_ok=False)
    assert rc == 2 and not any(keep.glob("**/*"))


def _carry(tmp_path, keep: bool, live_name="New name", old_config=True):
    live = tmp_path / "live"
    (live / "saves/art").mkdir(parents=True)
    (live / "saves/art/1-a.json").write_text("{}")
    (live / "timeline").mkdir()
    (live / "timeline/art.jsonl").write_text("live\n")
    (live / "settings.json").write_text('{"parent_pin": "1111"}')
    old = tmp_path / "keep/config"
    old.mkdir(parents=True)
    (old / "settings.json").write_text('{"parent_pin": "2222"}')
    (old / "saves/art").mkdir(parents=True)
    (old / "saves/art/0-b.json").write_text("{}")
    (old / "timeline").mkdir()
    (old / "timeline/art.jsonl").write_text("old\n")
    (tmp_path / "keep/.purple/packs/dinos").mkdir(parents=True)
    (tmp_path / "keep/.purple/packs/dinos/manifest.json").write_text("{}")
    (tmp_path / "keep/.purple/computer_name.txt").write_text("Old name")
    (old / "computer_name.txt").write_text("Older name")
    (old / "kids/leo/timeline").mkdir(parents=True)
    (old / "kids/leo/timeline/art.jsonl").write_text("leo\n")
    (live / "kids/mia/saves/art").mkdir(parents=True)
    (live / "kids/mia/saves/art/2-c.json").write_text("{}")
    if not old_config:
        subprocess.run(["rm", "-rf", str(old)], check=True)
    if live_name:
        (live / "computer_name.txt").write_text(live_name)
    root = tmp_path / "root"
    body = INSTALL_SH.read_text().split("if [ -n \"$PURPLE_KEEP_DIR\" ] && [ -d \"$PURPLE_KEEP_DIR/config\" ]; then", 1)[1]
    body = "if [ -n \"$PURPLE_KEEP_DIR\" ] && [ -d \"$PURPLE_KEEP_DIR/config\" ]; then" + body.split("\n            fi\n", 1)[0] + "\nfi\n"
    script = f"""
{_extract_function(INSTALL_SH, 'carry_over').replace('/mnt/root', str(root))}
log() {{ :; }}; warn() {{ echo "$@" >&2; }}; chown() {{ :; }}
PURPLE_LIVE_CONFIG="{live}"
PURPLE_KEEP_DIR="{tmp_path / 'keep' if keep else ''}"
{body.replace('/mnt/root', str(root))}
"""
    subprocess.run(["bash", "-c", script], check=True)
    return root / "home/purple"


def test_keep_merges_saves_from_the_stick_but_keeps_the_laptops_history(tmp_path):
    cfg = _carry(tmp_path, keep=True) / ".config/purple"
    assert sorted(p.name for p in (cfg / "saves/art").iterdir()) == ["0-b.json", "1-a.json"]
    assert (cfg / "timeline/art.jsonl").read_text() == "old\n"


def test_keep_keeps_the_laptops_settings_and_pin(tmp_path):
    assert (_carry(tmp_path, keep=True) / ".config/purple/settings.json").read_text() == '{"parent_pin": "2222"}'


def test_fresh_install_brings_the_whole_live_session(tmp_path):
    cfg = _carry(tmp_path, keep=False) / ".config/purple"
    assert [p.name for p in (cfg / "saves/art").iterdir()] == ["1-a.json"]
    assert (cfg / "timeline/art.jsonl").read_text() == "live\n"
    assert (cfg / "settings.json").read_text() == '{"parent_pin": "1111"}'
    assert (cfg / "computer_name.txt").read_text() == "New name"


def test_keep_uses_the_name_typed_at_install(tmp_path):
    home = _carry(tmp_path, keep=True)
    assert (home / ".config/purple/computer_name.txt").read_text() == "New name"
    assert not (home / ".purple/computer_name.txt").exists()


def test_keep_with_the_name_left_blank_drops_the_old_one(tmp_path):
    home = _carry(tmp_path, keep=True, live_name=None)
    assert not (home / ".config/purple/computer_name.txt").exists()
    assert not (home / ".purple/computer_name.txt").exists()


def test_keep_brings_back_the_laptops_packs(tmp_path):
    assert (_carry(tmp_path, keep=True) / ".purple/packs/dinos/manifest.json").exists()


def test_fresh_install_has_no_old_packs(tmp_path):
    assert not (_carry(tmp_path, keep=False) / ".purple").exists()


def test_probe_prefers_the_name_kept_with_the_settings(tmp_path):
    (tmp_path / "oldroot/home/purple/.config/purple").mkdir(parents=True)
    (tmp_path / "oldroot/home/purple/.config/purple/computer_name.txt").write_text("Ari's Computer")
    assert _save(tmp_path, probe=True)[0] == "[PURPLE-FOUND] Ari's Computer\n"


@pytest.mark.parametrize("label,mount_ok,out", [("Windows", True, ""), ("PURPLE_ROOT", False, "[PURPLE-FOUND-UNREADABLE]\n")])
def test_probe_leaves_nothing_from_an_earlier_probe(tmp_path, label, mount_ok, out):
    stdout, keep = _save(tmp_path, label=label, mount_ok=mount_ok, probe=True, stale=True)
    assert stdout == out and not (keep / "config/saves/art/stale.json").exists()


def test_probe_of_a_laptop_with_no_work_ignores_an_earlier_probes_saves(tmp_path):
    stdout, keep = _save(tmp_path, probe=True, work=[], stale=True)
    assert stdout == "[PURPLE-EMPTY] Sam's Computer\n" and not (keep / "config/saves/art/stale.json").exists()


@pytest.mark.parametrize("live_name,shown", [("New name", "New name"), (None, None)])
def test_installed_purple_shows_the_name_typed_at_install_not_the_laptops_old_one(tmp_path, monkeypatch, live_name, shown):
    from purplecomputer import kids, settings
    from purplecomputer.rooms.parent_menu import DEFAULT_COMPUTER_NAME
    home = _carry(tmp_path, keep=True, live_name=live_name)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(settings, "SETTINGS_FILE", home / ".config/purple/settings.json")
    monkeypatch.setattr(kids, "_read", lambda p: "" if str(p).startswith("/opt/") else p.read_text().strip() if p.exists() else "")
    assert kids.computer_name("") == (shown or DEFAULT_COMPUTER_NAME)


def test_probe_with_no_internal_disk_says_nothing_and_keeps_nothing(tmp_path):
    stdout, keep = _save(tmp_path, probe=True, stale=True, disk=False)
    assert stdout == "" and not keep.exists()


@pytest.mark.parametrize("name", ["Sam's 🦄 Computer", "  Ari  ", "Mo\n"])
def test_any_name_the_parent_typed_survives_the_probe(tmp_path, monkeypatch, name):
    from purplecomputer import old_install
    out, _ = _save(tmp_path, probe=True, home_name=name)
    monkeypatch.setattr(old_install, "PAYLOAD_PATH", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert old_install._run() == ("found", name.strip())


def test_keep_without_the_laptops_settings_brings_the_whole_live_session(tmp_path):
    cfg = _carry(tmp_path, keep=True, old_config=False) / ".config/purple"
    assert (cfg / "timeline/art.jsonl").read_text() == "live\n"
    assert (cfg / "settings.json").read_text() == '{"parent_pin": "1111"}'


def test_keep_brings_the_laptops_other_kids(tmp_path):
    cfg = _carry(tmp_path, keep=True) / ".config/purple"
    assert (cfg / "kids/leo/timeline/art.jsonl").read_text() == "leo\n"


def test_keep_leaves_the_keys_other_kids_behind(tmp_path):
    """The known gap in guides/updating-purple.md: only the first kid's saves come from the Key."""
    assert not (_carry(tmp_path, keep=True) / ".config/purple/kids/mia").exists()


def test_fresh_brings_the_keys_other_kids_and_none_of_the_laptops(tmp_path):
    cfg = _carry(tmp_path, keep=False) / ".config/purple"
    assert (cfg / "kids/mia/saves/art/2-c.json").exists() and not (cfg / "kids/leo").exists()
