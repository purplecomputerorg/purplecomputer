#!/usr/bin/env python3
"""
Create a signed USB update package for Purple Computer.

Takes the project source directory, signs a manifest with the developer's
private key, and writes the update package to a USB mount point (or any
output directory).

Usage:
    python3 tools/create_usb_update.py --version 0.2.0 --output /media/usb
    python3 tools/create_usb_update.py --version 0.2.0 --output /tmp/test-update --dry-run

    # or: just create-update 0.2.0 /media/usb
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from nacl.signing import SigningKey
except ImportError:
    SigningKey = None
    # Only exit if running as main script, not when imported by tests
    if __name__ == "__main__":
        print("PyNaCl is required. Install it with: pip install pynacl")
        sys.exit(1)

# Files and directories to skip when collecting payload
SKIP_PATTERNS = {
    "__pycache__",
    ".pyc",
    ".pyo",
    ".git",
    ".DS_Store",
    ".env",
    "Thumbs.db",
    ".pytest_cache",
    ".venv",
    "venv",
    ".test_home",
    ".docker-data",
    "parent.json",
    "node_modules",
}

# Directories to include in the update payload
# These are relative to the project root
INCLUDE_DIRS = [
    "purple_tui",
    "packs",
]

# Individual files to include
INCLUDE_FILES = [
    "VERSION",
    "version.json",
    "BREAKING_VERSION",
    "keyboard_normalizer.py",
    "requirements.txt",
]


def sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def should_skip(path: Path) -> bool:
    """Check if a file/dir should be skipped."""
    for part in path.parts:
        if part in SKIP_PATTERNS:
            return True
        if part.endswith(".pyc") or part.endswith(".pyo"):
            return True
    return False


def collect_files(source_dir: Path) -> list[tuple[str, Path]]:
    """Collect all files to include in the update.

    Returns list of (relative_path, absolute_path) tuples.
    """
    files = []

    # Collect files from included directories
    for dir_name in INCLUDE_DIRS:
        dir_path = source_dir / dir_name
        if not dir_path.exists():
            print(f"Warning: directory not found: {dir_path}")
            continue

        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_dir():
                continue
            rel = file_path.relative_to(source_dir)
            if should_skip(rel):
                continue
            files.append((str(rel), file_path))

    # Collect individual files
    for file_name in INCLUDE_FILES:
        file_path = source_dir / file_name
        if file_path.exists():
            files.append((file_name, file_path))

    return files


def create_update(source_dir: Path, output_dir: Path, version: str,
                  private_key_path: Path, description: str = "",
                  min_version: str = "", dry_run: bool = False) -> bool:
    """Create a signed update package.

    Args:
        source_dir: Project root directory.
        output_dir: Where to write the update (USB mount or temp dir).
        version: Version string (e.g. "0.2.0").
        private_key_path: Path to hex-encoded Ed25519 private key.
        description: Optional description for the update.
        min_version: Optional minimum version required to apply this update.
        dry_run: If True, print what would be done without writing.

    Returns True on success.
    """
    # Load private key
    if not private_key_path.exists():
        print(f"Error: private key not found: {private_key_path}")
        print("Run 'just keygen' to generate a key pair.")
        return False

    key_hex = private_key_path.read_text().strip()
    signing_key = SigningKey(bytes.fromhex(key_hex))

    # Collect files
    files = collect_files(source_dir)
    if not files:
        print("Error: no files found to include in update.")
        return False

    print(f"Collected {len(files)} files for update v{version}")

    # Build manifest
    file_entries = []
    for rel_path, abs_path in files:
        file_hash = sha256_file(abs_path)
        file_entries.append({
            "path": rel_path,
            "sha256": file_hash,
            "action": "replace",
        })

    # Read breaking version from source
    breaking_version = 1
    breaking_file = source_dir / "BREAKING_VERSION"
    if breaking_file.exists():
        try:
            breaking_version = int(breaking_file.read_text().strip())
        except ValueError:
            pass

    manifest = {
        "format_version": 1,
        "version": version,
        "breaking_version": breaking_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description or f"Purple Computer update v{version}",
        "files": file_entries,
    }

    if min_version:
        manifest["min_version"] = min_version

    if dry_run:
        print("\n--- DRY RUN ---")
        print(f"Version: {version}")
        print(f"Files: {len(file_entries)}")
        print(f"Output: {output_dir}")
        print("\nFiles that would be included:")
        for rel_path, abs_path in files:
            size = abs_path.stat().st_size
            print(f"  {rel_path} ({size:,} bytes)")
        print("\nManifest:")
        print(json.dumps(manifest, indent=2))
        return True

    # Sign manifest
    manifest_bytes = json.dumps(manifest, indent=2).encode()
    signed = signing_key.sign(manifest_bytes)
    signature = signed.signature

    # Write to output directory
    payload_dir = output_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)

    # Write manifest and signature
    (output_dir / "manifest.json").write_bytes(manifest_bytes)
    (output_dir / "manifest.sig").write_bytes(signature)

    # Copy payload files
    import shutil
    for rel_path, abs_path in files:
        dest = payload_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(abs_path, dest)

    print(f"\nUpdate package written to: {output_dir}")
    print(f"  manifest.json ({len(manifest_bytes):,} bytes)")
    print(f"  manifest.sig ({len(signature)} bytes)")
    print(f"  payload/ ({len(files)} files)")

    # Verify what we just wrote (sanity check)
    print("\nVerifying package...")
    verify_key = signing_key.verify_key

    # Re-read and verify
    read_manifest = (output_dir / "manifest.json").read_bytes()
    read_sig = (output_dir / "manifest.sig").read_bytes()

    try:
        verify_key.verify(read_manifest, read_sig)
        print("  Signature: OK")
    except Exception as e:
        print(f"  Signature: FAILED ({e})")
        return False

    # Verify file hashes
    read_manifest_dict = json.loads(read_manifest)
    for entry in read_manifest_dict["files"]:
        file_path = payload_dir / entry["path"]
        actual_hash = sha256_file(file_path)
        if actual_hash != entry["sha256"]:
            print(f"  Hash MISMATCH: {entry['path']}")
            return False

    print(f"  File hashes: all {len(file_entries)} OK")
    print("\nUpdate package is ready.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Create a signed USB update for Purple Computer"
    )
    parser.add_argument("--version", required=True, help="Update version (e.g. 0.2.0)")
    parser.add_argument("--output", required=True, help="Output directory (USB mount point)")
    parser.add_argument("--source", default=None,
                        help="Source directory (defaults to project root)")
    parser.add_argument("--key", default=None,
                        help="Path to private key (defaults to tools/update-key.priv)")
    parser.add_argument("--description", default="", help="Update description")
    parser.add_argument("--min-version", default="", help="Minimum version required")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing")

    args = parser.parse_args()

    # Resolve paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    source_dir = Path(args.source) if args.source else project_root
    output_dir = Path(args.output)
    key_path = Path(args.key) if args.key else (script_dir / "update-key.priv")

    if not source_dir.exists():
        print(f"Error: source directory not found: {source_dir}")
        sys.exit(1)

    success = create_update(
        source_dir=source_dir,
        output_dir=output_dir,
        version=args.version,
        private_key_path=key_path,
        description=args.description,
        min_version=args.min_version,
        dry_run=args.dry_run,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
