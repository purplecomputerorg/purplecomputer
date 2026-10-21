#!/usr/bin/env python3
"""For each Purple build out there (from scripts/compat_check.sh): which pack formats it reads, the
newer ones it lacks (studio/pack_formats.json), and whether today's rooms and room library run on it
(scripts/room_compat.sh). Prints who to email when a build is behind."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMATS = json.loads((ROOT / "studio" / "pack_formats.json").read_text())["formats"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def resolve(commit: str) -> str | None:
    found = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    if found.returncode:
        git("fetch", "--quiet", "origin")
        found = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    return found.stdout.strip() or None


def format_at(sha: str) -> int | None:
    """The newest pack format the build reads; None before Purple read Studio's packs."""
    m = re.search(r"^PACK_FORMAT = (\d+)$", git("show", f"{sha}:purple_tui/content.py").stdout, re.M)
    return int(m.group(1)) if m else None


def rooms_run(sha: str) -> bool | None:
    if git("cat-file", "-e", f"{sha}:purple_tui/canvas/harness.py").returncode:
        return None
    return subprocess.run([str(ROOT / "scripts" / "room_compat.sh"), sha], capture_output=True).returncode == 0


def merged(builds: list[dict]) -> dict[str, dict]:
    """Short and full hashes of one build, as one."""
    out: dict[str, dict] = {}
    for b in builds:
        sha = resolve(b["commit"]) or b["commit"]
        o = out.setdefault(sha, {"channels": set(), "emails": set(), "anonymous": 0, "drives": 0, "last": ""})
        o["channels"] |= set(b["channels"])
        o["emails"] |= set(b["emails"])
        o["anonymous"] += b["anonymous"]
        o["drives"] += b["drives"]
        o["last"] = max(o["last"], b["last"])
    return out


def main() -> None:
    builds = merged(json.loads(Path(sys.argv[1]).read_text())["builds"])
    quick = "--quick" in sys.argv[2:]
    newest = FORMATS[-1]["format"]
    behind = []
    for sha, b in sorted(builds.items(), key=lambda kv: kv[1]["last"], reverse=True):
        reads = format_at(sha) if git("cat-file", "-e", sha).returncode == 0 else None
        who = f"{len(b['emails'])} people" + (f", {b['anonymous']} unknown" if b["anonymous"] else "") + (f", {b['drives']} drives" if b["drives"] else "")
        reads_text = f"reads up to format {reads}" if reads else "doesn't read Studio packs"
        print(f"{sha[:8]}  {b['last'][:10]}  {','.join(sorted(b['channels'])) or 'flashed'}  {who}  {reads_text}")
        if reads is None:
            continue
        for f in FORMATS[reads:]:
            print(f"    lacks format {f['format']} ({f['date']}): {f['added']}")
        ok = None if quick else rooms_run(sha)
        if ok is not None:
            print(f"    today's rooms: {'run' if ok else 'FAIL, see just room-compat ' + sha[:8]}")
        if reads < newest or ok is False:
            behind.append(b)
            if b["emails"]:
                print(f"    on it: {', '.join(sorted(b['emails']))}")
    print()
    if not behind:
        print("Every build that reads Studio packs opens everything Studio makes today.")
    else:
        print(f"{len(behind)} build(s) are behind. Packs that use something newer won't open there until those families download Purple again.")
        sys.exit(2)


if __name__ == "__main__":
    main()
