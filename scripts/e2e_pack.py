#!/usr/bin/env python3
"""Carry .purplepack files to a fresh headless Purple on a pretend USB drive, add them as a parent
would, and check each thing in them where a kid meets it (tests/canvas/pack_journey.py).

    just e2e-pack the-nathansons-purple.purplepack [--shots DIR] [--json]

Exits 1 when anything in a pack doesn't reach the kid."""

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from purple_tui.canvas.harness import make_app  # noqa: E402
from tests.canvas.pack_journey import check, deliver, isolate, shot  # noqa: E402


async def journey(packs: list[Path], home: Path, shots: Path | None, expect: list[str] = ()) -> dict:
    """expect: things that must have passed a check, so a pack missing them (Studio left them out) fails."""
    drive = home / "drive"
    drive.mkdir(parents=True)
    for p in packs:
        shutil.copy2(p, drive / p.name)
    isolate(home / "purple")
    app = make_app()
    shot(app, shots, "before")
    seen = await deliver(app, drive, shots)
    checks = {p.name: [asdict(c) for c in await check(app, p, shots)] for p in packs}
    for room in app._family_rooms.values():
        room._stop()
    passed = [c["what"] for cs in checks.values() for c in cs if c["ok"]]
    checks["expected"] = [{"ok": any(e in w for w in passed), "what": f"expected: {e}"} for e in expect]
    return {"screens": seen, "checks": checks, "ok": app.top is None and all(c["ok"] for cs in checks.values() for c in cs)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("packs", nargs="+", type=Path)
    ap.add_argument("--shots", type=Path, help="write a screenshot at each step here")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--expect", action="append", default=[], help="text a passing check must contain (repeatable)")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="purple-e2e-") as home:
        report = asyncio.run(journey([p.resolve() for p in args.packs], Path(home), args.shots, args.expect))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for s in report["screens"]:
            print(f"  screen: {s}")
        for name, checks in report["checks"].items():
            print(name)
            for c in checks:
                print(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['what']}")
        print("everything reached the kid" if report["ok"] else "SOMETHING DIDN'T REACH THE KID")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
