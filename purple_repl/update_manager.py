"""
Purple Computer Update Manager
Lightweight update system for packs and core files
"""

import json
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Optional
from packaging import version as version_parser


class UpdateManager:
    """Manages checking for and installing updates"""

    def __init__(self,
                 feed_url: str,
                 packs_dir: Path,
                 cache_dir: Optional[Path] = None):
        """
        Initialize update manager

        Args:
            feed_url: URL to the update feed JSON
            packs_dir: Directory where packs are installed
            cache_dir: Directory for downloaded files (default: ~/.purple/cache)
        """
        self.feed_url = feed_url
        self.packs_dir = Path(packs_dir)

        if cache_dir is None:
            cache_dir = Path.home() / '.purple' / 'cache'

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.installed_versions_path = self.packs_dir / '.versions.json'
        self.installed_versions = self._load_installed_versions()

    def _load_installed_versions(self) -> Dict[str, str]:
        """Load the versions of currently installed packs"""
        if self.installed_versions_path.exists():
            try:
                with open(self.installed_versions_path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_installed_versions(self):
        """Save the installed versions to file"""
        with open(self.installed_versions_path, 'w') as f:
            json.dump(self.installed_versions, f, indent=2)

    def _fetch_json(self, url: str, timeout: int = 10) -> Optional[Dict]:
        """
        Fetch JSON from a URL

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            Parsed JSON dict or None on error
        """
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                if response.status != 200:
                    return None
                data = response.read()
                return json.loads(data)
        except (urllib.error.URLError, json.JSONDecodeError, Exception):
            return None

    def _download_file(self, url: str, dest_path: Path, expected_hash: Optional[str] = None) -> tuple[bool, str]:
        """
        Download a file with optional hash verification

        Args:
            url: URL to download
            dest_path: Destination file path
            expected_hash: Optional SHA256 hash to verify

        Returns:
            Tuple of (success, message)
        """
        try:
            # Download to temporary file first
            temp_path = dest_path.with_suffix('.tmp')

            with urllib.request.urlopen(url, timeout=30) as response:
                if response.status != 200:
                    return False, f"HTTP {response.status}"

                with open(temp_path, 'wb') as f:
                    f.write(response.read())

            # Verify hash if provided
            if expected_hash:
                with open(temp_path, 'rb') as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()

                if file_hash != expected_hash:
                    temp_path.unlink()
                    return False, f"Hash mismatch (expected {expected_hash}, got {file_hash})"

            # Move to final location
            temp_path.rename(dest_path)

            return True, "Downloaded successfully"

        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            return False, f"Download error: {str(e)}"

    def check_for_updates(self) -> tuple[bool, List[Dict]]:
        """
        Check for available updates

        Returns:
            Tuple of (success, list of available updates)
        """
        feed = self._fetch_json(self.feed_url)

        if feed is None:
            return False, []

        updates = []

        # Check pack updates
        for pack_info in feed.get('packs', []):
            pack_id = pack_info['id']
            remote_version = pack_info['version']
            installed_version = self.installed_versions.get(pack_id)

            # If not installed or newer version available
            if installed_version is None:
                updates.append({
                    'type': 'new_pack',
                    'id': pack_id,
                    'name': pack_info['name'],
                    'version': remote_version,
                    'url': pack_info['url'],
                    'hash': pack_info.get('hash'),
                    'description': pack_info.get('description', '')
                })
            elif self._is_newer_version(remote_version, installed_version):
                updates.append({
                    'type': 'pack_update',
                    'id': pack_id,
                    'name': pack_info['name'],
                    'old_version': installed_version,
                    'new_version': remote_version,
                    'url': pack_info['url'],
                    'hash': pack_info.get('hash'),
                    'description': pack_info.get('description', '')
                })

        # Check core file updates
        for core_info in feed.get('core_files', []):
            file_path = core_info['path']
            remote_version = core_info['version']
            installed_version = self.installed_versions.get(f'core:{file_path}')

            if installed_version is None or self._is_newer_version(remote_version, installed_version):
                updates.append({
                    'type': 'core_update',
                    'path': file_path,
                    'version': remote_version,
                    'url': core_info['url'],
                    'hash': core_info.get('hash'),
                    'description': core_info.get('description', '')
                })

        return True, updates

    def _is_newer_version(self, new_ver: str, old_ver: str) -> bool:
        """Compare semantic versions"""
        try:
            return version_parser.parse(new_ver) > version_parser.parse(old_ver)
        except Exception:
            # Fallback to string comparison if parsing fails
            return new_ver > old_ver

    def install_update(self, update_info: Dict) -> tuple[bool, str]:
        """
        Install a single update

        Args:
            update_info: Update information dict

        Returns:
            Tuple of (success, message)
        """
        update_type = update_info['type']

        if update_type in ['new_pack', 'pack_update']:
            return self._install_pack_update(update_info)
        elif update_type == 'core_update':
            return self._install_core_update(update_info)
        else:
            return False, f"Unknown update type: {update_type}"

    def _install_pack_update(self, update_info: Dict) -> tuple[bool, str]:
        """Install a pack update"""
        pack_id = update_info['id']
        url = update_info['url']
        expected_hash = update_info.get('hash')

        # Download pack file
        pack_filename = f"{pack_id}.purplepack"
        pack_path = self.cache_dir / pack_filename

        success, msg = self._download_file(url, pack_path, expected_hash)
        if not success:
            return False, f"Failed to download pack: {msg}"

        # Install using pack manager (will be imported when needed)
        try:
            from pack_manager import PackManager, get_registry

            pack_manager = PackManager(self.packs_dir, get_registry())

            # Uninstall old version if it exists
            if update_info['type'] == 'pack_update':
                pack_manager.uninstall_pack(pack_id)

            # Install new version
            success, msg = pack_manager.install_pack_from_file(pack_path)

            if success:
                # Update installed versions
                self.installed_versions[pack_id] = update_info.get('new_version', update_info['version'])
                self._save_installed_versions()

                # Clean up downloaded file
                pack_path.unlink()

            return success, msg

        except Exception as e:
            return False, f"Error installing pack: {str(e)}"

    def _install_core_update(self, update_info: Dict) -> tuple[bool, str]:
        """Install a core file update"""
        file_path = update_info['path']
        url = update_info['url']
        expected_hash = update_info.get('hash')
        version = update_info['version']

        # Determine target path (relative to Purple Computer home)
        purple_home = Path.home() / '.purple'
        target_path = purple_home / file_path

        # Backup existing file
        if target_path.exists():
            backup_path = target_path.with_suffix(target_path.suffix + '.backup')
            try:
                import shutil
                shutil.copy2(target_path, backup_path)
            except Exception:
                pass

        # Download new file
        success, msg = self._download_file(url, target_path, expected_hash)

        if success:
            # Update installed versions
            self.installed_versions[f'core:{file_path}'] = version
            self._save_installed_versions()

            return True, f"Core file updated: {file_path}"
        else:
            # Restore backup if download failed
            if backup_path.exists():
                backup_path.rename(target_path)

            return False, f"Failed to update {file_path}: {msg}"

    def install_all_updates(self, updates: List[Dict]) -> List[tuple[bool, str]]:
        """
        Install all updates

        Args:
            updates: List of update information dicts

        Returns:
            List of (success, message) tuples
        """
        results = []

        for update in updates:
            result = self.install_update(update)
            results.append(result)

        return results

    def get_current_version(self, pack_id: str) -> Optional[str]:
        """Get the currently installed version of a pack"""
        return self.installed_versions.get(pack_id)

    def mark_pack_version(self, pack_id: str, version: str):
        """Manually mark a pack version (useful for initial setup)"""
        self.installed_versions[pack_id] = version
        self._save_installed_versions()


def create_update_manager(feed_url: str = "https://purplecomputer.org/updates/feed.json") -> UpdateManager:
    """
    Create an update manager instance

    Args:
        feed_url: URL to the update feed

    Returns:
        UpdateManager instance
    """
    packs_dir = Path.home() / '.purple' / 'packs'
    return UpdateManager(feed_url, packs_dir)
