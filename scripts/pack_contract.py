#!/usr/bin/env python3
"""The pack contract between Studio and the Purples families already have: studio/pack_formats.json lists
each pack format, and a fingerprint of the code that writes or reads packs makes every change to it a
decision (tests/test_pack_contract.py). Rationale: studio/PACK_FORMAT.md, "Format versions".

Usage:
  just pack-contract                       the change is safe both ways: re-record the fingerprint
  just pack-contract bump "what it adds" [--file REGEX ...] [--call NAME ...]
                                           packs using the change need a newer Purple: add a format
"""

import argparse
import ast
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LEDGER = ROOT / "studio" / "pack_formats.json"
CONTENT_PY = ROOT / "purple_tui" / "content.py"
# What Studio writes into a pack (and reads back from one), and what Purple reads out of it.
WATCHED = [
    "studio/sdk/src/pack.ts",
    "studio/src/pack.ts",
    "purple_tui/content.py",
    "purple_tui/pack_manager.py",
    "purple_tui/canvas/theme.py",
    "purple_tui/canvas/rooms/family_room.py",
    "purple_tui/roomkit/purple.py",
    "purple_tui/roomkit/runner.py",
    "purple_tui/roomkit/limits.py",
]

DECIDE = """Code that writes or reads Purple Packs changed ({files}).
Decide, and tell the user which:
  - Safe both ways (a refactor, or nothing a pack holds changed): run `just pack-contract`.
  - Packs Studio makes now need something older Purples lack, so they'd half-work there: run
    `just pack-contract bump "<what it adds>" --file <path regex> --call <room function>` with markers
    that spot packs using it, and tell the user the reminder it prints.
  - Purple stopped reading something older packs hold: don't. Purple keeps reading every format in
    studio/pack_formats.json; ask the user first."""


def _normalized(path: Path) -> str:
    text = path.read_text()
    if path.suffix == ".py":
        return ast.dump(ast.parse(text))
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if not line.lstrip().startswith("//"))
    return "\n".join(line for line in lines if line)


def fingerprint() -> dict[str, str]:
    return {rel: hashlib.sha256(_normalized(ROOT / rel).encode()).hexdigest()[:16] for rel in WATCHED}


def load() -> dict:
    return json.loads(LEDGER.read_text())


def code_format() -> int:
    return int(re.search(r"^PACK_FORMAT = (\d+)$", CONTENT_PY.read_text(), re.M).group(1))


def problems() -> list[str]:
    ledger = load()
    out = []
    numbers = [f["format"] for f in ledger["formats"]]
    if numbers != list(range(1, len(numbers) + 1)):
        out.append(f"studio/pack_formats.json formats must run 1, 2, 3...: {numbers}")
    if code_format() != numbers[-1]:
        out.append(f"purple_tui/content.py PACK_FORMAT is {code_format()} but the ledger's newest is {numbers[-1]}: use `just pack-contract bump`.")
    if changed := [rel for rel, h in fingerprint().items() if ledger["fingerprint"].get(rel) != h]:
        out.append(DECIDE.format(files=", ".join(changed)))
    return out


def _save(ledger: dict) -> None:
    ledger["fingerprint"] = fingerprint()
    LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n")
    from scripts.export_studio import main as export
    export()


def bump(added: str, files: list[str], calls: list[str]) -> None:
    for pattern in files:
        re.compile(pattern)
    if not files and not calls:
        sys.exit("A bump needs --file or --call markers, so Studio can tell which packs need the new Purple.")
    ledger = load()
    n = ledger["formats"][-1]["format"] + 1
    ledger["formats"].append({"format": n, "date": date.today().isoformat(), "added": added, "needs": {"files": files, "calls": calls}})
    CONTENT_PY.write_text(re.sub(r"^PACK_FORMAT = \d+$", f"PACK_FORMAT = {n}", CONTENT_PY.read_text(), flags=re.M))
    _save(ledger)
    print(f"""
Pack format {n}: {added}
Tell the user:
  Packs that use this now say format {n}. A Purple from before today shows "Needs newer Purple
  software" instead of adding them, and Studio's download page warns the family. Other packs
  keep loading everywhere.
  Before `just studio-deploy --prod`, run `just compat-check` to see who's on an older build,
  and plan to email them a new download. Mention format {n} in the commit message.""")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    b = sub.add_parser("bump", help="add a pack format")
    b.add_argument("added", help="what the format adds, in a few plain words")
    b.add_argument("--file", action="append", default=[], help="regex for a pack path that needs it")
    b.add_argument("--call", action="append", default=[], help="a room function whose use needs it")
    args = parser.parse_args()
    if args.cmd == "bump":
        return bump(args.added, args.file, args.call)
    _save(load())
    print("Recorded: Purple Packs read and write the same as before, so the pack format stays the same.")


if __name__ == "__main__":
    main()
