#!/usr/bin/env python3
"""For each Purple build out there (from scripts/compat_check.sh): which pack formats it reads, the
newer ones it lacks (studio/pack_formats.json), and whether today's rooms and room library run on it
(scripts/room_compat.sh). Prints who to email when a build is behind, and exits 2 only when a build fell
behind since the last check, so a deploy asks once per new one."""

import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMATS = json.loads((ROOT / "studio" / "pack_formats.json").read_text())["formats"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


COMMON = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def resolve(commit: str) -> str | None:
    found = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    if found.returncode:
        git("fetch", "--quiet", "origin")
        found = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    return found.stdout.strip() or None


def format_at(sha: str) -> int | None:
    """The newest pack format the build reads; None before Purple read Studio's packs."""
    m = re.search(r"^PACK_FORMAT = (\d+)$", git("show", f"{sha}:purplecomputer/content.py").stdout, re.M)
    return int(m.group(1)) if m else None


def room_inputs_digest() -> str:
    """What room_compat.sh brings from this checkout; a build's result holds until one of these changes."""
    files = [ROOT / "purplecomputer" / "roomkit" / "purple.py", ROOT / "tests" / "test_room_compat.py",
             ROOT / "scripts" / "room_compat.sh"]
    files += sorted((ROOT / "tests" / "rooms").glob("*.py")) + sorted((ROOT / "studio" / "src" / "examples").glob("*.py"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def rooms_run(sha: str) -> bool | None:
    if git("cat-file", "-e", f"{sha}:purplecomputer/harness.py").returncode:
        return None
    return subprocess.run([str(ROOT / "scripts" / "room_compat.sh"), sha], capture_output=True).returncode == 0


def rooms_run_all(shas: list[str]) -> dict[str, bool | None]:
    """Results are cached per build and room inputs, and uncached builds run in parallel."""
    cache_file = COMMON / "purple-room-compat.json"
    cache = load_json(cache_file, {})
    digest = room_inputs_digest()
    todo = [s for s in shas if f"{s}:{digest}" not in cache]
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        for sha, ok in zip(todo, pool.map(rooms_run, todo)):
            if ok is not False:
                cache[f"{sha}:{digest}"] = ok
    cache_file.write_text(json.dumps({k: v for k, v in cache.items() if k.endswith(digest)}))
    return {s: cache.get(f"{s}:{digest}", False) for s in shas}


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
    reads_of = {sha: format_at(sha) if git("cat-file", "-e", sha).returncode == 0 else None for sha in builds}
    runs = {} if quick else rooms_run_all([sha for sha, r in reads_of.items() if r is not None])
    behind = []
    for sha, b in sorted(builds.items(), key=lambda kv: kv[1]["last"], reverse=True):
        reads = reads_of[sha]
        who = f"{len(b['emails'])} people" + (f", {b['anonymous']} unknown" if b["anonymous"] else "") + (f", {b['drives']} drives" if b["drives"] else "")
        reads_text = f"reads up to format {reads}" if reads else "doesn't read Studio packs"
        print(f"{sha[:8]}  {b['last'][:10]}  {','.join(sorted(b['channels'])) or 'flashed'}  {who}  {reads_text}")
        if reads is None:
            continue
        for f in FORMATS[reads:]:
            print(f"    lacks format {f['format']} ({f['date']}): {f['added']}")
        ok = runs.get(sha)
        if ok is not None:
            print(f"    today's rooms: {'run' if ok else 'FAIL, see just room-compat ' + sha[:8]}")
        if reads < newest or ok is False:
            behind.append(sha)
            if b["emails"]:
                print(f"    on it: {', '.join(sorted(b['emails']))}")
    print()
    if not behind:
        print("Every build that reads Studio packs opens everything Studio makes today.")
        return
    print(f"{len(behind)} build(s) are behind. Packs that use something newer won't open there until those families download Purple again.")
    seen_file = COMMON / "purple-compat-behind.json"
    seen = load_json(seen_file, [])
    new = [sha[:8] for sha in behind if sha not in seen]
    seen_file.write_text(json.dumps(sorted({*seen, *behind})))
    if new:
        print(f"Newly behind since the last check: {', '.join(new)}")
        sys.exit(2)


if __name__ == "__main__":
    main()
