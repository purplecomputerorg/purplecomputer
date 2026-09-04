#!/usr/bin/env python3
"""Build, check, render, and install .purplepack files from the command line.

The same rules Purple applies when it installs a pack (purple_tui.pack_manager)
and the same synth it ships (purple_tui.synth), so a pack that passes here
installs there, and an instrument rendered here sounds like the Music room.

    just python scripts/purplepack.py check   my-pack/          # or my-pack.purplepack
    just python scripts/purplepack.py render  my-pack/          # instruments/*.json -> <name>/<pitch>.wav
    just python scripts/purplepack.py build   my-pack/          # -> <id>.purplepack next to it
    just python scripts/purplepack.py show    my-pack.purplepack
    just python scripts/purplepack.py install my-pack.purplepack [--packs-dir DIR] [--replace]

A pack directory is manifest.json plus content/. The layout is in
studio/PACK_FORMAT.md.
"""

import argparse
import json
import sys
import tarfile
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from purple_tui import synth  # noqa: E402
from purple_tui.content import read_manifest  # noqa: E402
from purple_tui.music_constants import note_frequency, pitch_filename, reachable_pitches  # noqa: E402
from purple_tui.pack_manager import PackInstaller, check_pack, extract_pack  # noqa: E402

READ_TODAY = {
    "manifest.json": "id, name, version, format",
    "content/emoji.json": "words and emoji, Play room",
    "content/synonyms.json": "nicknames for words, Play room",
    "content/rankings.txt": "autocomplete order, Play room",
    "content/letters/": "letter and number clips, Music room Say Letters",
    "content/voice/": "phrase clips, spoken by Purple",
    "content/pictures/": "pictures, parent menu",
    "content/instruments/": "instrument definitions; samples in content/<name>/",
}


def unpacked(path: Path) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    """A pack directory for either a directory or a .purplepack file."""
    if path.is_dir():
        return path, None
    tmp = tempfile.TemporaryDirectory()
    if refused := extract_pack(path, Path(tmp.name)):
        raise SystemExit(refused)
    return Path(tmp.name), tmp


def cmd_check(args) -> int:
    pack_dir, tmp = unpacked(Path(args.pack))
    problems = check_pack(pack_dir)
    for p in problems:
        print(f"  {p}")
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def render_instruments(pack_dir: Path, force: bool = False) -> list[Path]:
    """Render content/<name>/<pitch>.wav for every content/instruments/<name>.json,
    skipping files that already exist unless force. Returns the files written."""
    content = pack_dir / "content"
    written = []
    for spec_path in sorted((content / "instruments").glob("*.json")):
        spec = json.loads(spec_path.read_text())
        generator = synth.GENERATORS[spec["base"]]
        params = spec.get("params", {})
        target = content / spec_path.stem
        target.mkdir(exist_ok=True)
        for note, octave in reachable_pitches():
            out = target / f"{pitch_filename(note, octave)}.wav"
            if out.exists() and not force:
                continue
            samples = generator(note_frequency(note, octave), **params)
            with wave.open(str(out), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(synth.SAMPLE_RATE)
                w.writeframes(b"".join(max(-32767, min(32767, s)).to_bytes(2, "little", signed=True) for s in samples))
            written.append(out)
    return written


def cmd_render(args) -> int:
    written = render_instruments(Path(args.pack), force=args.force)
    print(f"rendered {len(written)} file(s)")
    return 0


def build_pack(pack_dir: Path, out: Path | None = None) -> Path:
    manifest = read_manifest(pack_dir)
    if manifest is None:
        raise SystemExit("manifest.json is missing or unreadable")
    out = out or pack_dir.parent / f"{manifest['id']}.purplepack"
    with tarfile.open(out, "w:gz") as tar:
        tar.add(pack_dir / "manifest.json", arcname="manifest.json")
        tar.add(pack_dir / "content", arcname="content")
    return out


def cmd_build(args) -> int:
    pack_dir = Path(args.pack)
    if problems := check_pack(pack_dir):
        print("\n".join(f"  {p}" for p in problems))
        return 1
    out = build_pack(pack_dir, Path(args.output) if args.output else None)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


def cmd_show(args) -> int:
    pack_dir, tmp = unpacked(Path(args.pack))
    manifest = read_manifest(pack_dir) or {}
    print(f"{manifest.get('name', '?')}  id={manifest.get('id', '?')}  version={manifest.get('version', '?')}  format={manifest.get('format', 1)}")
    for path in sorted(p for p in pack_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(pack_dir).as_posix()
        reader = next((why for prefix, why in READ_TODAY.items() if rel == prefix or rel.startswith(prefix)), None)
        if reader is None and rel.startswith("content/") and rel.count("/") == 2 and rel.endswith(".wav"):
            reader = "instrument samples, Music room"
        print(f"  {rel:48} {reader or 'not read by Purple'}")
    problems = check_pack(pack_dir)
    print("ok" if not problems else "\n".join(f"  ! {p}" for p in problems))
    return 0


def cmd_install(args) -> int:
    installer = PackInstaller(Path(args.packs_dir) if args.packs_dir else None)
    ok, msg = installer.install_pack(Path(args.pack), replace=args.replace)
    print(msg)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("check", cmd_check), ("show", cmd_show)):
        p = sub.add_parser(name)
        p.add_argument("pack", help="pack directory or .purplepack file")
        p.set_defaults(fn=fn)
    p = sub.add_parser("render")
    p.add_argument("pack", help="pack directory")
    p.add_argument("--force", action="store_true", help="re-render samples that already exist")
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser("build")
    p.add_argument("pack", help="pack directory")
    p.add_argument("-o", "--output")
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("install")
    p.add_argument("pack", help=".purplepack file")
    p.add_argument("--packs-dir", help="default ~/.purple/packs")
    p.add_argument("--replace", action="store_true", help="swap out an installed pack with the same id")
    p.set_defaults(fn=cmd_install)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
