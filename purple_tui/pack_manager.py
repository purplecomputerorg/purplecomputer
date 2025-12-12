"""
Purple Computer Pack Manager (Content-Only)

Handles installation of content purplepacks. These are CONTENT ONLY:
- emoji packs (JSON)
- sounds packs (audio files)
- stories packs (text + audio)

NO PYTHON CODE is ever executed from packs. Modes are Python modules
shipped with the app and curated/reviewed by Purple Computer team.
"""

import json
import tarfile
import shutil
from pathlib import Path
from typing import Optional


# Valid content-only pack types (no executable code)
VALID_PACK_TYPES = ['emoji', 'sounds', 'stories']


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
        """Validate a pack manifest"""
        required_fields = ['id', 'name', 'version', 'type']

        for field in required_fields:
            if field not in manifest:
                return False, f"Missing required field: {field}"

        # IMPORTANT: Only allow content types, NO modes
        pack_type = manifest['type']
        if pack_type not in VALID_PACK_TYPES:
            return False, f"Invalid pack type: {pack_type}. Content packs only (no modes)."

        # Validate version format (x.y.z)
        version = manifest['version']
        parts = version.split('.')
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return False, f"Invalid version format: {version}"

        # Reject any pack that mentions entrypoint/Python
        if 'entrypoint' in manifest:
            return False, "Executable packs not allowed. Content packs only."

        return True, "OK"

    def _check_for_python(self, pack_dir: Path) -> bool:
        """Check if pack contains any Python files (security check)"""
        for filepath in pack_dir.rglob('*'):
            if filepath.suffix in ['.py', '.pyc', '.pyo', '.pyw']:
                return True
            # Also check for shebangs in files
            if filepath.is_file() and filepath.suffix in ['', '.sh']:
                try:
                    with open(filepath, 'rb') as f:
                        first_line = f.readline()
                        if b'python' in first_line.lower():
                            return True
                except Exception:
                    pass
        return False

    def install_pack(self, pack_path: Path) -> tuple[bool, str]:
        """
        Install a .purplepack file (content only).

        Pack format: tar.gz containing:
          - manifest.json (required)
          - content/ directory with:
            - emoji.json (for emoji packs - word -> emoji mapping)
            - sounds.json + assets/*.wav (for sound packs)
            - stories.json + assets/*.mp3 (for story packs)
        """
        pack_path = Path(pack_path)

        if not pack_path.exists():
            return False, f"Pack file not found: {pack_path}"

        if not pack_path.suffix == '.purplepack':
            return False, "Pack file must have .purplepack extension"

        temp_dir = None
        try:
            # Extract to temporary directory
            temp_dir = self.packs_dir / '.tmp' / pack_path.stem
            temp_dir.mkdir(parents=True, exist_ok=True)

            with tarfile.open(pack_path, 'r:gz') as tar:
                # Security: check for path traversal
                for member in tar.getmembers():
                    if member.name.startswith('/') or '..' in member.name:
                        return False, f"Security error: Invalid path in pack"
                tar.extractall(temp_dir)

            # Load and validate manifest
            manifest_path = temp_dir / 'manifest.json'
            if not manifest_path.exists():
                return False, "Pack missing manifest.json"

            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            valid, msg = self.validate_manifest(manifest)
            if not valid:
                return False, f"Invalid manifest: {msg}"

            # SECURITY: Check for Python files
            if self._check_for_python(temp_dir):
                return False, "Security error: Pack contains executable code. Content packs only."

            pack_id = manifest['id']

            # Check if pack already installed
            final_dir = self.packs_dir / pack_id
            if final_dir.exists():
                return False, f"Pack already installed: {pack_id}"

            # Move to final location
            shutil.move(str(temp_dir), str(final_dir))

            return True, f"Pack installed: {manifest['name']} v{manifest['version']}"

        except json.JSONDecodeError:
            return False, "Invalid manifest.json format"
        except tarfile.TarError as e:
            return False, f"Invalid pack file: {e}"
        except Exception as e:
            return False, f"Error installing pack: {str(e)}"
        finally:
            # Clean up temp directory
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
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

        for pack_dir in self.packs_dir.iterdir():
            if pack_dir.is_dir() and not pack_dir.name.startswith('.'):
                manifest_path = pack_dir / 'manifest.json'
                if manifest_path.exists():
                    try:
                        with open(manifest_path) as f:
                            manifest = json.load(f)
                            packs.append({
                                'id': manifest.get('id', pack_dir.name),
                                'name': manifest.get('name', pack_dir.name),
                                'version': manifest.get('version', '0.0.0'),
                                'type': manifest.get('type', 'unknown'),
                            })
                    except Exception:
                        pass

        return packs


def get_installer() -> PackInstaller:
    """Get a pack installer instance"""
    return PackInstaller()
