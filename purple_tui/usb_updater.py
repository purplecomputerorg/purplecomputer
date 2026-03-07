#!/usr/bin/env python3
"""
Purple Computer USB Offline Updater

Applies signed updates from a USB drive. Called by systemd when a USB drive
labeled PURPLE_UPDATE is inserted. The update flow:

1. Verify Ed25519 signature on manifest
2. Validate manifest structure and version compatibility
3. Verify SHA256 hashes of all payload files
4. Copy files to staging directory, re-verify hashes
5. Move staged files to /opt/purple/
6. Write signal file so the TUI can prompt for restart

Security: only the manifest signature is checked. File hashes are inside the
signed manifest, so signing transitively verifies all payload files. The manifest
is declarative only (replace/delete), no arbitrary code execution.
"""

import hashlib
import json
import logging
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .constants import USB_UPDATE_SIGNAL_FILE

# Where Purple Computer is installed
INSTALL_DIR = Path("/opt/purple")

# Public key for verifying update signatures
PUBLIC_KEY_PATH = INSTALL_DIR / "update-key.pub"

# Log to file (not stderr, since Textual uses stderr)
LOG_PATH = Path("/var/log/purple-update.log")

logger = logging.getLogger("purple-usb-update")


def setup_logging() -> None:
    """Configure logging to file."""
    handler = logging.FileHandler(LOG_PATH)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def load_public_key() -> bytes:
    """Load the Ed25519 public key from disk.

    Returns the 32-byte raw public key.

    Raises FileNotFoundError if the key file is missing.
    Raises ValueError if the key file content is invalid.
    """
    if not PUBLIC_KEY_PATH.exists():
        raise FileNotFoundError(f"Public key not found: {PUBLIC_KEY_PATH}")

    hex_key = PUBLIC_KEY_PATH.read_text().strip()
    key_bytes = bytes.fromhex(hex_key)

    if len(key_bytes) != 32:
        raise ValueError(f"Invalid public key length: {len(key_bytes)} bytes (expected 32)")

    return key_bytes


def verify_signature(manifest_bytes: bytes, signature: bytes,
                     public_key_bytes: Optional[bytes] = None) -> bool:
    """Verify Ed25519 signature on manifest data.

    Args:
        manifest_bytes: Raw manifest JSON bytes.
        signature: 64-byte Ed25519 signature.
        public_key_bytes: 32-byte public key. If None, loaded from PUBLIC_KEY_PATH.

    Returns True if signature is valid.
    """
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    if public_key_bytes is None:
        public_key_bytes = load_public_key()

    verify_key = VerifyKey(public_key_bytes)

    try:
        verify_key.verify(manifest_bytes, signature)
        return True
    except BadSignatureError:
        return False


def validate_manifest(manifest: dict, local_version: Optional[str] = None) -> list[str]:
    """Validate manifest structure and version compatibility.

    Args:
        manifest: Parsed manifest dict.
        local_version: Current installed version (e.g. "0.1.0"). If None, skips
            version compatibility check.

    Returns list of error strings. Empty list means valid.
    """
    errors = []

    # Required fields
    for field in ("format_version", "version", "files"):
        if field not in manifest:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors  # Can't validate further without required fields

    # Format version
    if manifest["format_version"] != 1:
        errors.append(f"Unsupported format_version: {manifest['format_version']}")

    # Version string format
    version = manifest.get("version", "")
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        errors.append(f"Invalid version format: {version}")

    # Files list
    files = manifest.get("files", [])
    if not isinstance(files, list):
        errors.append("'files' must be a list")
    else:
        for i, entry in enumerate(files):
            if not isinstance(entry, dict):
                errors.append(f"files[{i}]: must be a dict")
                continue

            # Required file fields
            if "path" not in entry:
                errors.append(f"files[{i}]: missing 'path'")
                continue

            if "action" not in entry:
                errors.append(f"files[{i}]: missing 'action'")

            path = entry["path"]

            # Path safety: must be relative, no traversal
            if not isinstance(path, str) or not path:
                errors.append(f"files[{i}]: path must be a non-empty string")
                continue

            path_obj = Path(path)
            if path_obj.is_absolute():
                errors.append(f"files[{i}]: absolute path not allowed: {path}")
            if ".." in path_obj.parts:
                errors.append(f"files[{i}]: path traversal not allowed: {path}")

            # Action validation
            action = entry.get("action", "")
            if action not in ("replace", "delete"):
                errors.append(f"files[{i}]: invalid action: {action}")

            # Replace actions need sha256
            if action == "replace" and not entry.get("sha256"):
                errors.append(f"files[{i}]: 'replace' action requires 'sha256'")

    # Min version check
    if local_version and "min_version" in manifest:
        min_ver = manifest["min_version"]
        if _parse_version(local_version) < _parse_version(min_ver):
            errors.append(
                f"Update requires version {min_ver} or later, "
                f"but current version is {local_version}"
            )

    return errors


def verify_file_hashes(manifest: dict, payload_dir: Path) -> list[str]:
    """Verify SHA256 hashes of payload files against manifest.

    Args:
        manifest: Parsed manifest dict (already validated).
        payload_dir: Directory containing payload files.

    Returns list of error strings. Empty list means all hashes match.
    """
    errors = []

    for entry in manifest.get("files", []):
        if entry["action"] != "replace":
            continue

        rel_path = entry["path"]
        file_path = payload_dir / rel_path
        expected_hash = entry["sha256"]

        if not file_path.exists():
            errors.append(f"Missing payload file: {rel_path}")
            continue

        actual_hash = _sha256_file(file_path)
        if actual_hash != expected_hash:
            errors.append(
                f"Hash mismatch for {rel_path}: "
                f"expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
            )

    return errors


def apply_update(manifest: dict, payload_dir: Path,
                 install_dir: Optional[Path] = None) -> list[str]:
    """Apply update: copy files to staging, re-verify, move to install dir.

    Args:
        manifest: Parsed manifest dict (already validated).
        payload_dir: Directory containing payload files.
        install_dir: Target installation directory. Defaults to INSTALL_DIR.

    Returns list of error strings. Empty list means success.
    """
    if install_dir is None:
        install_dir = INSTALL_DIR

    errors = []
    staging_dir = None

    try:
        # Stage files in a temp directory first
        staging_dir = Path(tempfile.mkdtemp(prefix="purple-update-"))

        for entry in manifest.get("files", []):
            rel_path = entry["path"]
            action = entry["action"]

            if action == "replace":
                src = payload_dir / rel_path
                staged = staging_dir / rel_path
                staged.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, staged)

            elif action == "delete":
                target = install_dir / rel_path
                if target.exists():
                    target.unlink()
                    logger.info("Deleted: %s", rel_path)

        # Re-verify hashes in staging
        staged_errors = verify_file_hashes(manifest, staging_dir)
        if staged_errors:
            errors.extend(staged_errors)
            return errors

        # Move staged files to install directory
        for entry in manifest.get("files", []):
            if entry["action"] != "replace":
                continue

            rel_path = entry["path"]
            staged = staging_dir / rel_path
            target = install_dir / rel_path

            target.parent.mkdir(parents=True, exist_ok=True)

            # Remove existing file before moving (shutil.move can fail on cross-device)
            if target.exists():
                target.unlink()

            shutil.move(str(staged), str(target))
            logger.info("Updated: %s", rel_path)

        # Update VERSION file if included in manifest
        version = manifest.get("version")
        if version:
            version_file = install_dir / "VERSION"
            version_file.write_text(version + "\n")

    except OSError as e:
        errors.append(f"File operation failed: {e}")

    finally:
        # Clean up staging directory
        if staging_dir and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    return errors


def process_usb_update(mount_point: str,
                       install_dir: Optional[Path] = None,
                       public_key_bytes: Optional[bytes] = None) -> bool:
    """Main entry point: process a USB update from mount_point.

    Args:
        mount_point: Path to mounted USB drive.
        install_dir: Override install directory (for testing).
        public_key_bytes: Override public key (for testing).

    Returns True on success.
    """
    usb = Path(mount_point)

    # Load and verify manifest
    manifest_path = usb / "manifest.json"
    sig_path = usb / "manifest.sig"
    payload_dir = usb / "payload"

    if not manifest_path.exists():
        logger.error("No manifest.json found on USB drive")
        return False

    if not sig_path.exists():
        logger.error("No manifest.sig found on USB drive")
        return False

    manifest_bytes = manifest_path.read_bytes()
    signature = sig_path.read_bytes()

    # Verify signature
    logger.info("Verifying update signature...")
    try:
        if not verify_signature(manifest_bytes, signature, public_key_bytes):
            logger.error("Invalid signature. Update rejected.")
            return False
    except (FileNotFoundError, ValueError) as e:
        logger.error("Signature verification failed: %s", e)
        return False

    logger.info("Signature verified.")

    # Parse manifest
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as e:
        logger.error("Invalid manifest JSON: %s", e)
        return False

    # Get local version for compatibility check
    local_version = None
    if install_dir is None:
        version_file = INSTALL_DIR / "VERSION"
        if version_file.exists():
            local_version = version_file.read_text().strip()
    else:
        version_file = install_dir / "VERSION"
        if version_file.exists():
            local_version = version_file.read_text().strip()

    # Validate manifest
    validation_errors = validate_manifest(manifest, local_version)
    if validation_errors:
        for err in validation_errors:
            logger.error("Manifest error: %s", err)
        return False

    logger.info("Manifest valid: version %s (%d files)",
                manifest["version"], len(manifest["files"]))

    # Verify payload file hashes
    hash_errors = verify_file_hashes(manifest, payload_dir)
    if hash_errors:
        for err in hash_errors:
            logger.error("Hash error: %s", err)
        return False

    logger.info("All file hashes verified.")

    # Apply update
    target_dir = install_dir if install_dir else None
    apply_errors = apply_update(manifest, payload_dir, target_dir)
    if apply_errors:
        for err in apply_errors:
            logger.error("Apply error: %s", err)
        return False

    logger.info("Update applied successfully: version %s", manifest["version"])

    # Write signal file for TUI
    signal_path = Path(USB_UPDATE_SIGNAL_FILE)
    signal_path.write_text(json.dumps({
        "version": manifest["version"],
        "applied_at": datetime.now().isoformat(),
    }))
    logger.info("Signal file written: %s", signal_path)

    return True


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_version(v: str) -> tuple:
    """Parse version string "x.y.z" to tuple for comparison."""
    try:
        return tuple(int(p) for p in v.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def main():
    """CLI entry point for systemd service."""
    setup_logging()

    if len(sys.argv) != 2:
        logger.error("Usage: python3 -m purple_tui.usb_updater <mount_point>")
        sys.exit(1)

    mount_point = sys.argv[1]
    logger.info("USB update started from: %s", mount_point)

    success = process_usb_update(mount_point)

    if success:
        logger.info("USB update completed successfully.")
        sys.exit(0)
    else:
        logger.error("USB update failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
