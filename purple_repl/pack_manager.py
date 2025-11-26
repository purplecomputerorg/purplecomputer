"""
Purple Computer Pack Manager
Handles loading, validation, and registry of content packs
"""

import json
import tarfile
import hashlib
import shutil
import sys
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any


class PackRegistry:
    """Central registry for all loaded packs and their content"""

    def __init__(self):
        self.packs: Dict[str, Dict] = {}
        self.emoji: Dict[str, str] = {}
        self.definitions: Dict[str, str] = {}
        self.modes: Dict[str, Any] = {}
        self.sounds: Dict[str, Path] = {}

    def register_pack(self, pack_id: str, manifest: Dict):
        """Register a pack in the registry"""
        self.packs[pack_id] = manifest

    def add_emoji(self, name: str, emoji: str, pack_id: str):
        """Add an emoji to the registry"""
        self.emoji[name] = emoji

    def add_definition(self, word: str, definition: str, pack_id: str):
        """Add a word definition to the registry"""
        self.definitions[word] = definition

    def add_mode(self, name: str, mode_class: Any, pack_id: str):
        """Add a mode to the registry"""
        self.modes[name] = mode_class

    def add_sound(self, name: str, sound_path: Path, pack_id: str):
        """Add a sound file to the registry"""
        self.sounds[name] = sound_path

    def get_emoji(self, name: str) -> Optional[str]:
        """Get an emoji by name"""
        return self.emoji.get(name)

    def get_all_emoji(self) -> Dict[str, str]:
        """Get all registered emoji"""
        return self.emoji.copy()

    def get_definition(self, word: str) -> Optional[str]:
        """Get a word definition"""
        return self.definitions.get(word)

    def get_mode(self, name: str) -> Optional[Any]:
        """Get a mode by name"""
        return self.modes.get(name)

    def list_packs(self) -> List[Dict]:
        """List all registered packs"""
        return [
            {
                'id': pack_id,
                'name': manifest.get('name', pack_id),
                'version': manifest.get('version', '0.0.0'),
                'type': manifest.get('type', 'unknown')
            }
            for pack_id, manifest in self.packs.items()
        ]


class PackManager:
    """Manages pack installation, loading, and validation"""

    def __init__(self, packs_dir: Path, registry: PackRegistry):
        self.packs_dir = Path(packs_dir)
        self.registry = registry
        self.packs_dir.mkdir(parents=True, exist_ok=True)

    def validate_manifest(self, manifest: Dict) -> tuple[bool, str]:
        """Validate a pack manifest"""
        required_fields = ['id', 'name', 'version', 'type']

        for field in required_fields:
            if field not in manifest:
                return False, f"Missing required field: {field}"

        # Validate pack type
        valid_types = ['emoji', 'definitions', 'mode', 'sounds', 'effect', 'mixed']
        if manifest['type'] not in valid_types:
            return False, f"Invalid pack type: {manifest['type']}"

        # Validate version format (simple x.y.z)
        version = manifest['version']
        parts = version.split('.')
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return False, f"Invalid version format: {version}"

        # For mode packs, entrypoint is required
        if manifest['type'] == 'mode' and 'entrypoint' not in manifest:
            return False, "Mode packs require 'entrypoint' field"

        return True, "OK"

    def install_pack_from_file(self, pack_path: Path) -> tuple[bool, str]:
        """
        Install a .purplepack file

        Pack format: tar.gz containing:
          - manifest.json (required)
          - data/ (preferred) or content/ (legacy)
            - emoji.json (for emoji packs)
            - definitions.json (for definition packs)
            - *.py (Python modules for mode packs)
            - sounds/*.wav, *.ogg (for sound packs)
        """
        pack_path = Path(pack_path)

        if not pack_path.exists():
            return False, f"Pack file not found: {pack_path}"

        if not pack_path.suffix == '.purplepack':
            return False, "Pack file must have .purplepack extension"

        try:
            # Extract to temporary directory
            temp_dir = self.packs_dir / '.tmp' / pack_path.stem
            temp_dir.mkdir(parents=True, exist_ok=True)

            with tarfile.open(pack_path, 'r:gz') as tar:
                # Security: check for path traversal
                for member in tar.getmembers():
                    if member.name.startswith('/') or '..' in member.name:
                        return False, f"Invalid file path in pack: {member.name}"
                tar.extractall(temp_dir)

            # Load and validate manifest
            manifest_path = temp_dir / 'manifest.json'
            if not manifest_path.exists():
                shutil.rmtree(temp_dir)
                return False, "Pack missing manifest.json"

            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            valid, msg = self.validate_manifest(manifest)
            if not valid:
                shutil.rmtree(temp_dir)
                return False, f"Invalid manifest: {msg}"

            pack_id = manifest['id']

            # Check if pack already installed
            final_dir = self.packs_dir / pack_id
            if final_dir.exists():
                shutil.rmtree(temp_dir)
                return False, f"Pack already installed: {pack_id}"

            # Move to final location
            shutil.move(str(temp_dir), str(final_dir))

            # Load the pack
            success, msg = self.load_pack(pack_id)
            if not success:
                shutil.rmtree(final_dir)
                return False, msg

            return True, f"Pack installed: {manifest['name']} v{manifest['version']}"

        except Exception as e:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            return False, f"Error installing pack: {str(e)}"

    def load_pack(self, pack_id: str) -> tuple[bool, str]:
        """Load a pack from the packs directory"""
        pack_dir = self.packs_dir / pack_id

        if not pack_dir.exists():
            return False, f"Pack not found: {pack_id}"

        manifest_path = pack_dir / 'manifest.json'
        if not manifest_path.exists():
            return False, f"Pack missing manifest: {pack_id}"

        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            # Register the pack
            self.registry.register_pack(pack_id, manifest)

            # Load content based on pack type
            # Support both 'data/' (new) and 'content/' (legacy) directories
            data_dir = pack_dir / 'data'
            content_dir = pack_dir / 'content'

            if data_dir.exists():
                content_dir = data_dir
            elif not content_dir.exists():
                return True, f"Pack loaded (no content): {pack_id}"

            pack_type = manifest['type']

            # Load emoji
            if pack_type in ['emoji', 'mixed']:
                emoji_file = content_dir / 'emoji.json'
                if emoji_file.exists():
                    with open(emoji_file, 'r') as f:
                        emoji_data = json.load(f)
                        for name, emoji in emoji_data.items():
                            self.registry.add_emoji(name, emoji, pack_id)

            # Load definitions
            if pack_type in ['definitions', 'mixed']:
                defs_file = content_dir / 'definitions.json'
                if defs_file.exists():
                    with open(defs_file, 'r') as f:
                        defs_data = json.load(f)
                        for word, definition in defs_data.items():
                            self.registry.add_definition(word, definition, pack_id)

            # Load sounds
            if pack_type in ['sounds', 'mixed']:
                sounds_dir = content_dir / 'sounds'
                if sounds_dir.exists():
                    for sound_file in sounds_dir.glob('*'):
                        if sound_file.suffix in ['.wav', '.ogg', '.mp3']:
                            name = sound_file.stem
                            self.registry.add_sound(name, sound_file, pack_id)

            # Load mode entrypoint
            if pack_type == 'mode' and 'entrypoint' in manifest:
                entrypoint = manifest['entrypoint']
                mode_file = pack_dir / entrypoint

                if not mode_file.exists():
                    return False, f"Mode entrypoint not found: {entrypoint}"

                try:
                    # Load the Python module dynamically
                    spec = importlib.util.spec_from_file_location(
                        f"purple_pack_{pack_id}",
                        mode_file
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[f"purple_pack_{pack_id}"] = module
                        spec.loader.exec_module(module)

                        # Look for a mode activation function or class
                        # Convention: module should have a 'mode' attribute or 'activate' function
                        if hasattr(module, 'activate'):
                            # Store the activate function
                            mode_name = pack_id.replace('-', '_').replace('_mode', '')
                            self.registry.add_mode(mode_name, module.activate, pack_id)
                        elif hasattr(module, 'mode'):
                            # Store the mode object/class
                            mode_name = pack_id.replace('-', '_').replace('_mode', '')
                            self.registry.add_mode(mode_name, module.mode, pack_id)
                        else:
                            return False, f"Mode module missing 'activate' function or 'mode' attribute"

                except Exception as e:
                    return False, f"Error loading mode from {entrypoint}: {str(e)}"

            return True, f"Pack loaded: {manifest['name']}"

        except Exception as e:
            return False, f"Error loading pack {pack_id}: {str(e)}"

    def load_all_packs(self) -> List[tuple[bool, str]]:
        """Load all packs from the packs directory"""
        results = []

        if not self.packs_dir.exists():
            return results

        for pack_dir in self.packs_dir.iterdir():
            if pack_dir.is_dir() and not pack_dir.name.startswith('.'):
                result = self.load_pack(pack_dir.name)
                results.append(result)

        return results

    def uninstall_pack(self, pack_id: str) -> tuple[bool, str]:
        """Uninstall a pack"""
        pack_dir = self.packs_dir / pack_id

        if not pack_dir.exists():
            return False, f"Pack not found: {pack_id}"

        try:
            shutil.rmtree(pack_dir)
            # Remove from registry
            if pack_id in self.registry.packs:
                del self.registry.packs[pack_id]
            return True, f"Pack uninstalled: {pack_id}"
        except Exception as e:
            return False, f"Error uninstalling pack: {str(e)}"

    def verify_pack_integrity(self, pack_id: str, expected_hash: str) -> bool:
        """Verify pack integrity using SHA256 hash"""
        pack_dir = self.packs_dir / pack_id

        if not pack_dir.exists():
            return False

        # Calculate hash of all files in pack
        hasher = hashlib.sha256()

        for filepath in sorted(pack_dir.rglob('*')):
            if filepath.is_file():
                with open(filepath, 'rb') as f:
                    hasher.update(f.read())

        return hasher.hexdigest() == expected_hash


# Global registry instance
_global_registry = PackRegistry()


def get_registry() -> PackRegistry:
    """Get the global pack registry"""
    return _global_registry
