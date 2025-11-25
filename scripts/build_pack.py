#!/usr/bin/env python3
"""
Pack Builder Script
Creates .purplepack files from source directories
"""

import json
import tarfile
import sys
from pathlib import Path


def build_pack(source_dir: Path, output_file: Path):
    """
    Build a .purplepack file from a source directory

    Expected structure:
        source_dir/
            manifest.json
            content/
                ... (pack-specific files)
    """
    source_dir = Path(source_dir)
    output_file = Path(output_file)

    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}")
        return False

    manifest_path = source_dir / 'manifest.json'
    if not manifest_path.exists():
        print(f"Error: manifest.json not found in {source_dir}")
        return False

    # Validate manifest
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        required_fields = ['id', 'name', 'version', 'type']
        for field in required_fields:
            if field not in manifest:
                print(f"Error: Missing required field in manifest: {field}")
                return False

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in manifest: {e}")
        return False

    # Create tar.gz archive
    try:
        with tarfile.open(output_file, 'w:gz') as tar:
            # Add manifest
            tar.add(manifest_path, arcname='manifest.json')

            # Add content directory if it exists
            content_dir = source_dir / 'content'
            if content_dir.exists():
                for item in content_dir.rglob('*'):
                    if item.is_file():
                        arcname = 'content' / item.relative_to(content_dir)
                        tar.add(item, arcname=str(arcname))

        print(f"✓ Pack created: {output_file}")
        print(f"  Name: {manifest['name']}")
        print(f"  Version: {manifest['version']}")
        print(f"  Type: {manifest['type']}")
        return True

    except Exception as e:
        print(f"Error creating pack: {e}")
        return False


def main():
    if len(sys.argv) != 3:
        print("Usage: build_pack.py <source_dir> <output.purplepack>")
        sys.exit(1)

    source_dir = Path(sys.argv[1])
    output_file = Path(sys.argv[2])

    if not output_file.suffix == '.purplepack':
        output_file = output_file.with_suffix('.purplepack')

    if build_pack(source_dir, output_file):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
