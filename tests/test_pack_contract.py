"""A change to how Purple Packs are written or read is a decision, not drift: scripts/pack_contract.py."""

import json
import shutil
import subprocess
import sys

import pytest

from purple_tui.content import PACK_FORMAT
from purple_tui.pack_manager import check_pack
from scripts import compat_check, export_studio, pack_contract
from scripts.pack_contract import problems
from tests.test_packs import make_pack

LEDGER = json.loads(pack_contract.LEDGER.read_text())


def test_pack_contract_is_decided():
    assert not problems(), "\n\n".join(problems())


@pytest.fixture
def contract(tmp_path, monkeypatch):
    """The contract over a copy of two watched files, so tests can change them."""
    for rel in ("purple_tui/content.py", "studio/sdk/src/pack.ts"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(pack_contract.ROOT / rel, tmp_path / rel)
    ledger = tmp_path / "pack_formats.json"
    ledger.write_text(json.dumps({**LEDGER, "fingerprint": {}}))
    monkeypatch.setattr(pack_contract, "ROOT", tmp_path)
    monkeypatch.setattr(pack_contract, "LEDGER", ledger)
    monkeypatch.setattr(pack_contract, "CONTENT_PY", tmp_path / "purple_tui" / "content.py")
    monkeypatch.setattr(pack_contract, "WATCHED", ["purple_tui/content.py", "studio/sdk/src/pack.ts"])
    monkeypatch.setattr(export_studio, "main", lambda: None)
    pack_contract._save(pack_contract.load())
    return tmp_path


def test_a_code_change_needs_a_decision_but_a_comment_does_not(contract):
    py, ts = contract / "purple_tui" / "content.py", contract / "studio" / "sdk" / "src" / "pack.ts"
    py.write_text(py.read_text() + "\n# a note\n")
    ts.write_text(ts.read_text() + "\n// a note\n")
    assert problems() == []
    ts.write_text(ts.read_text() + "\nexport const x = 1;\n")
    assert len(problems()) == 1 and "(studio/sdk/src/pack.ts)" in problems()[0]
    pack_contract._save(pack_contract.load())
    assert problems() == []


def test_purple_and_the_ledger_must_agree_on_the_newest_format(contract):
    py = contract / "purple_tui" / "content.py"
    py.write_text(py.read_text().replace(f"PACK_FORMAT = {PACK_FORMAT}", f"PACK_FORMAT = {PACK_FORMAT + 1}"))
    pack_contract._save(pack_contract.load())
    assert any("PACK_FORMAT is" in p for p in problems())


def test_a_bump_adds_a_format_that_purple_and_studio_both_take_up(contract):
    pack_contract.bump("Stickers", ["^content/stickers/"], ["wobble"])
    ledger = pack_contract.load()
    assert ledger["formats"][-1] == {"format": PACK_FORMAT + 1, "date": ledger["formats"][-1]["date"], "added": "Stickers",
                                     "needs": {"files": ["^content/stickers/"], "calls": ["wobble"]}}
    assert pack_contract.code_format() == PACK_FORMAT + 1
    assert problems() == []


def test_a_bump_without_markers_is_refused(contract):
    with pytest.raises(SystemExit):
        pack_contract.bump("Something", [], [])


@pytest.mark.parametrize("fmt", [f["format"] for f in LEDGER["formats"]])
def test_purple_keeps_reading_every_format_in_the_ledger(fmt, tmp_path):
    assert check_pack(make_pack(tmp_path, fmt=fmt)) == []


def test_purple_refuses_a_format_newer_than_it_reads(tmp_path):
    assert check_pack(make_pack(tmp_path, fmt=PACK_FORMAT + 1))


def test_compat_check_reads_the_format_a_build_was_made_with():
    head = subprocess.run(["git", "-C", str(pack_contract.ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert compat_check.format_at(head) == PACK_FORMAT


def test_compat_check_flags_a_build_that_lacks_a_newer_format(tmp_path, monkeypatch, capsys):
    head = subprocess.run(["git", "-C", str(pack_contract.ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    builds = tmp_path / "builds.json"
    builds.write_text(json.dumps({"builds": [
        {"commit": head[:8], "channels": ["preview"], "emails": ["a@example.com"], "anonymous": 0, "drives": 0, "last": "2026-10-21"},
        {"commit": head, "channels": [], "emails": [], "anonymous": 0, "drives": 2, "last": "2026-10-20"},
    ]}))
    monkeypatch.setattr(sys, "argv", ["compat_check", str(builds), "--quick"])
    compat_check.main()
    out = capsys.readouterr().out
    assert out.count(head[:8]) == 1 and "1 people, 2 drives" in out and "opens everything" in out

    monkeypatch.setattr(compat_check, "FORMATS", [*compat_check.FORMATS, {"format": PACK_FORMAT + 1, "date": "2027-01-01", "added": "Stickers", "needs": {}}])
    with pytest.raises(SystemExit) as behind:
        compat_check.main()
    out = capsys.readouterr().out
    assert behind.value.code == 2 and "lacks format" in out and "on it: a@example.com" in out
