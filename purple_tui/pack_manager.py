"""
Purple Computer Pack Manager (Content-Only)

Handles installation of content purplepacks. These are CONTENT ONLY:
- emoji packs (JSON)
- sounds packs (audio files)
- stories packs (text + audio)

NO PYTHON CODE is ever executed from packs. Modes are Python modules
shipped with the app and curated/reviewed by Purple Computer team.

The pack layout, and what the runtime reads from it, is written up in
studio/PACK_FORMAT.md. `check_pack` is the one place that knows the rules;
the installer, the USB updater, and scripts/purplepack.py all go through it.
"""

import json
import shutil
import tarfile
import wave
from pathlib import Path
from typing import Optional

from .content import PACK_FORMAT, read_manifest

# Valid content-only pack types (no executable code)
VALID_PACK_TYPES = ['emoji', 'sounds', 'stories']

CODE_SUFFIXES = {'.py', '.pyc', '.pyo', '.pyw'}
VOICE_RATE, VOICE_CHANNELS, VOICE_WIDTH = 22050, 1, 2
SAMPLE_RATE, SAMPLE_CHANNELS, SAMPLE_WIDTH = 44100, 1, 2


def validate_manifest(manifest: dict) -> tuple[bool, str]:
    """Validate a pack manifest"""
    for field in ('id', 'name', 'version', 'type'):
        if field not in manifest:
            return False, f"Missing required field: {field}"

    pack_id = manifest['id']
    if not isinstance(pack_id, str) or not pack_id or pack_id != Path(pack_id).name or pack_id.startswith('.'):
        return False, f"Invalid pack id: {pack_id!r}"

    # IMPORTANT: Only allow content types, NO modes
    pack_type = manifest['type']
    if pack_type not in VALID_PACK_TYPES:
        return False, f"Invalid pack type: {pack_type}. Content packs only (no modes)."

    version = str(manifest['version'])
    parts = version.split('.')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return False, f"Invalid version format: {version}"

    fmt = manifest.get('format', 1)
    if not isinstance(fmt, int) or fmt < 1 or fmt > PACK_FORMAT:
        return False, f"Unsupported pack format: {fmt!r} (this Purple reads up to {PACK_FORMAT})"

    # Reject any pack that mentions entrypoint/Python
    if 'entrypoint' in manifest:
        return False, "Executable packs not allowed. Content packs only."

    return True, "OK"


def extract_pack(pack_path: Path, dest: Path) -> str | None:
    """Unpack a .purplepack into dest. Returns a message when the archive
    holds anything but plain files under relative paths."""
    with tarfile.open(pack_path, 'r:gz') as tar:
        for member in tar.getmembers():
            if member.name.startswith('/') or '..' in member.name.split('/') or not (member.isfile() or member.isdir()):
                return "Security error: Invalid path in pack"
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)
    return None


def _looks_like_code(path: Path) -> bool:
    if path.suffix in CODE_SUFFIXES:
        return True
    if path.suffix in ('', '.sh'):
        try:
            with open(path, 'rb') as f:
                return b'python' in f.readline().lower()
        except OSError:
            pass
    return False


def _wav_problem(path: Path, rate: int, channels: int, width: int) -> str | None:
    try:
        with wave.open(str(path)) as w:
            got = (w.getframerate(), w.getnchannels(), w.getsampwidth())
    except (wave.Error, EOFError, OSError):
        return f"{path.name}: not a readable WAV"
    if got != (rate, channels, width):
        return f"{path.name}: expected {rate} Hz, {channels} channel, {width * 8}-bit; got {got[0]} Hz, {got[1]} channel, {got[2] * 8}-bit"
    return None


def _json_object(path: Path) -> dict | None:
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def check_pack(pack_dir: Path) -> list[str]:
    """Every reason an unpacked pack directory should not be installed.

    Empty means the pack is well-formed for what Purple reads: the manifest,
    no code, emoji and synonym maps of strings, WAV clips in the format the
    mixer expects, instrument JSON whose parameters exist in the synth, and
    picture ops on the canvas. Directories Purple never reads are ignored.
    """
    problems: list[str] = []
    manifest = read_manifest(pack_dir)
    if manifest is None:
        return ["manifest.json is missing, unreadable, or declares a newer format than this Purple reads"]
    ok, msg = validate_manifest(manifest)
    if not ok:
        return [f"manifest.json: {msg}"]

    for path in sorted(pack_dir.rglob('*')):
        if path.is_file() and _looks_like_code(path):
            problems.append(f"{path.relative_to(pack_dir)}: packs may not contain code")
    if problems:
        return problems

    content = pack_dir / 'content'
    problems += _check_word_maps(content)
    problems += _check_clips(content / 'letters')
    problems += _check_clips(content / 'voice')
    problems += _check_instruments(content)
    problems += _check_pictures(content)
    return problems


def _check_word_maps(content: Path) -> list[str]:
    problems = []
    for name in ('emoji.json', 'synonyms.json'):
        path = content / name
        if not path.exists():
            continue
        data = _json_object(path)
        if data is None:
            problems.append(f"content/{name}: must be a JSON object")
        elif not all(isinstance(k, str) and isinstance(v, str) and k and v for k, v in data.items()):
            problems.append(f"content/{name}: every entry must map a word to a non-empty string")
    return problems


def _check_clips(clips_dir: Path) -> list[str]:
    if not clips_dir.is_dir():
        return []
    problems = []
    for path in sorted(clips_dir.iterdir()):
        if path.suffix != '.wav':
            problems.append(f"content/{clips_dir.name}/{path.name}: only .wav clips are read here")
        elif p := _wav_problem(path, VOICE_RATE, VOICE_CHANNELS, VOICE_WIDTH):
            problems.append(f"content/{clips_dir.name}/{p}")
    return problems


def _check_instruments(content: Path) -> list[str]:
    from .synth import DEFAULTS
    problems = []
    for spec in sorted((content / 'instruments').glob('*.json')):
        rel = f"content/instruments/{spec.name}"
        data = _json_object(spec)
        if data is None:
            problems.append(f"{rel}: must be a JSON object")
            continue
        base = data.get('base')
        if base not in DEFAULTS:
            problems.append(f"{rel}: base must be one of {', '.join(DEFAULTS)}")
            continue
        params = data.get('params', {})
        if not isinstance(params, dict):
            problems.append(f"{rel}: params must be an object")
            continue
        for key, value in params.items():
            if key not in DEFAULTS[base]:
                problems.append(f"{rel}: {base} has no parameter {key!r}")
            elif not isinstance(value, (int, float)) or isinstance(value, bool):
                problems.append(f"{rel}: {key} must be a number")
        samples = content / spec.stem
        if not samples.is_dir():
            problems.append(f"{rel}: no content/{spec.stem}/ sample directory; run `purplepack render` or it will not appear in the Music room")
            continue
        for wav in sorted(samples.glob('*.wav')):
            if p := _wav_problem(wav, SAMPLE_RATE, SAMPLE_CHANNELS, SAMPLE_WIDTH):
                problems.append(f"content/{spec.stem}/{p}")
    return problems


def _check_pictures(content: Path) -> list[str]:
    from .art_config import CANVAS_HEIGHT, CANVAS_WIDTH
    problems = []
    for spec in sorted((content / 'pictures').glob('*.json')):
        rel = f"content/pictures/{spec.name}"
        data = _json_object(spec)
        ops = data.get('ops') if data else None
        if not isinstance(ops, list):
            problems.append(f"{rel}: needs an ops list of [x, y, \"#rrggbb\"]")
            continue
        bad = [op for op in ops if not (isinstance(op, list) and len(op) == 3
                                        and isinstance(op[0], int) and 0 <= op[0] < CANVAS_WIDTH
                                        and isinstance(op[1], int) and 0 <= op[1] < CANVAS_HEIGHT
                                        and isinstance(op[2], str) and len(op[2]) == 7 and op[2][0] == '#')]
        if bad:
            problems.append(f"{rel}: {len(bad)} ops are off the {CANVAS_WIDTH} by {CANVAS_HEIGHT} canvas or not [x, y, \"#rrggbb\"]")
    return problems


class PackInstaller:
    """
    Installs and manages content-only purplepacks.

    Safety: This manager REFUSES to load any Python code.
    Only JSON and asset files (audio, images) are processed.
    """

    def __init__(self, packs_dir: Optional[Path] = None):
        self.packs_dir = packs_dir or Path.home() / ".purple" / "packs"
        self.packs_dir.mkdir(parents=True, exist_ok=True)

    def validate_manifest(self, manifest: dict) -> tuple[bool, str]:
        return validate_manifest(manifest)

    def install_pack(self, pack_path: Path, replace: bool = False) -> tuple[bool, str]:
        """Install a .purplepack file (a gzipped tar of manifest.json and
        content/). With replace, an installed pack of the same id is swapped
        out; otherwise it is left alone and the install is refused."""
        pack_path = Path(pack_path)

        if not pack_path.exists():
            return False, f"Pack file not found: {pack_path}"

        if not pack_path.suffix == '.purplepack':
            return False, "Pack file must have .purplepack extension"

        temp_dir = self.packs_dir / '.tmp' / pack_path.stem
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.mkdir(parents=True)

            if refused := extract_pack(pack_path, temp_dir):
                return False, refused

            if problems := check_pack(temp_dir):
                return False, "Pack not installed: " + "; ".join(problems[:5])

            manifest = read_manifest(temp_dir) or {}
            final_dir = self.packs_dir / manifest['id']
            if final_dir.exists():
                if not replace:
                    return False, f"Pack already installed: {manifest['id']}"
                shutil.rmtree(final_dir)
            shutil.move(str(temp_dir), str(final_dir))
            return True, f"Pack installed: {manifest['name']} v{manifest['version']}"

        except tarfile.TarError as e:
            return False, f"Invalid pack file: {e}"
        except Exception as e:
            return False, f"Error installing pack: {str(e)}"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            try:
                temp_dir.parent.rmdir()
            except OSError:
                pass

    def uninstall_pack(self, pack_id: str) -> tuple[bool, str]:
        """Uninstall a pack"""
        pack_dir = self.packs_dir / pack_id

        if not pack_dir.exists():
            return False, f"Pack not found: {pack_id}"

        try:
            shutil.rmtree(pack_dir)
            return True, f"Pack uninstalled: {pack_id}"
        except Exception as e:
            return False, f"Error uninstalling pack: {str(e)}"

    def list_installed(self) -> list[dict]:
        """List all installed packs"""
        packs = []

        if not self.packs_dir.exists():
            return packs

        for pack_dir in sorted(self.packs_dir.iterdir()):
            if pack_dir.is_dir() and not pack_dir.name.startswith('.'):
                manifest = read_manifest(pack_dir)
                if manifest is not None:
                    packs.append({
                        'id': manifest.get('id', pack_dir.name),
                        'name': manifest.get('name', pack_dir.name),
                        'version': manifest.get('version', '0.0.0'),
                        'type': manifest.get('type', 'unknown'),
                    })

        return packs


def get_installer() -> PackInstaller:
    """Get a pack installer instance"""
    return PackInstaller()
