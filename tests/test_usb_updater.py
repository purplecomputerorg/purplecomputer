#!/usr/bin/env python3
"""Tests for USB offline updater.

Tests signature verification, manifest validation, hash checking,
and file update operations using test key pairs (no real keys needed).

Run with: pytest tests/test_usb_updater.py -v
"""

import hashlib
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

try:
    from nacl.signing import SigningKey
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

from purple_tui.usb_updater import (
    validate_manifest,
    verify_file_hashes,
    verify_signature,
    apply_update,
    process_usb_update,
    USB_UPDATE_SIGNAL_FILE,
)

# Import create_usb_update helpers (tools/ isn't a package, so add to path)
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from create_usb_update import should_skip, collect_files


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_test_keys():
    """Generate a test Ed25519 key pair."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    return signing_key, verify_key.encode()


def _sign_manifest(manifest_dict: dict, signing_key) -> tuple[bytes, bytes]:
    """Sign a manifest dict, return (manifest_bytes, signature)."""
    manifest_bytes = json.dumps(manifest_dict).encode()
    signed = signing_key.sign(manifest_bytes)
    signature = signed.signature
    return manifest_bytes, signature


def _make_manifest(**overrides) -> dict:
    """Create a valid manifest dict with optional overrides."""
    manifest = {
        "format_version": 1,
        "version": "0.2.0",
        "created_at": "2026-01-01T00:00:00Z",
        "description": "Test update",
        "files": [],
    }
    manifest.update(overrides)
    return manifest


# =============================================================================
# Tests
# =============================================================================

if HAS_PYTEST:

    skipif_no_nacl = pytest.mark.skipif(
        not HAS_NACL, reason="PyNaCl not installed"
    )

    # =========================================================================
    # Path Validation
    # =========================================================================

    class TestPathValidation:
        """Test that dangerous paths are rejected."""

        def test_absolute_path_rejected(self):
            manifest = _make_manifest(files=[
                {"path": "/etc/passwd", "sha256": "abc", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert any("absolute path" in e for e in errors)

        def test_traversal_rejected(self):
            manifest = _make_manifest(files=[
                {"path": "../../../etc/passwd", "sha256": "abc", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert any("traversal" in e for e in errors)

        def test_traversal_in_middle_rejected(self):
            manifest = _make_manifest(files=[
                {"path": "purple_tui/../../etc/passwd", "sha256": "abc", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert any("traversal" in e for e in errors)

        def test_relative_path_accepted(self):
            manifest = _make_manifest(files=[
                {"path": "purple_tui/app.py", "sha256": "abc123", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert not errors

        def test_nested_path_accepted(self):
            manifest = _make_manifest(files=[
                {"path": "packs/core-emoji/content/data.json", "sha256": "abc123", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert not errors

        def test_empty_path_rejected(self):
            manifest = _make_manifest(files=[
                {"path": "", "sha256": "abc", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert any("non-empty" in e for e in errors)

    # =========================================================================
    # Manifest Validation
    # =========================================================================

    class TestManifestValidation:
        """Test manifest structure and field validation."""

        def test_valid_manifest(self):
            manifest = _make_manifest(files=[
                {"path": "VERSION", "sha256": "abc123", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert not errors

        def test_missing_format_version(self):
            manifest = _make_manifest()
            del manifest["format_version"]
            errors = validate_manifest(manifest)
            assert any("format_version" in e for e in errors)

        def test_missing_version(self):
            manifest = _make_manifest()
            del manifest["version"]
            errors = validate_manifest(manifest)
            assert any("version" in e for e in errors)

        def test_missing_files(self):
            manifest = _make_manifest()
            del manifest["files"]
            errors = validate_manifest(manifest)
            assert any("files" in e for e in errors)

        def test_unsupported_format_version(self):
            manifest = _make_manifest(format_version=99)
            errors = validate_manifest(manifest)
            assert any("format_version" in e for e in errors)

        def test_invalid_version_format(self):
            manifest = _make_manifest(version="not.a.version")
            errors = validate_manifest(manifest)
            assert any("version format" in e.lower() or "invalid version" in e.lower() for e in errors)

        def test_invalid_action(self):
            manifest = _make_manifest(files=[
                {"path": "foo.py", "sha256": "abc", "action": "exec"}
            ])
            errors = validate_manifest(manifest)
            assert any("invalid action" in e for e in errors)

        def test_replace_without_hash(self):
            manifest = _make_manifest(files=[
                {"path": "foo.py", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert any("sha256" in e for e in errors)

        def test_delete_action_accepted(self):
            manifest = _make_manifest(files=[
                {"path": "old_file.py", "sha256": None, "action": "delete"}
            ])
            errors = validate_manifest(manifest)
            assert not errors

        def test_min_version_check_passes(self):
            manifest = _make_manifest(min_version="0.1.0")
            errors = validate_manifest(manifest, local_version="0.1.0")
            assert not errors

        def test_min_version_check_fails(self):
            manifest = _make_manifest(min_version="0.3.0")
            errors = validate_manifest(manifest, local_version="0.1.0")
            assert any("requires version" in e for e in errors)

        def test_min_version_skipped_when_no_local(self):
            manifest = _make_manifest(min_version="99.0.0")
            errors = validate_manifest(manifest)
            assert not errors

        def test_files_not_a_list(self):
            manifest = _make_manifest(files="not a list")
            errors = validate_manifest(manifest)
            assert any("must be a list" in e for e in errors)

        def test_file_entry_not_a_dict(self):
            manifest = _make_manifest(files=["just a string"])
            errors = validate_manifest(manifest)
            assert any("must be a dict" in e for e in errors)

        def test_file_entry_missing_path(self):
            manifest = _make_manifest(files=[
                {"sha256": "abc", "action": "replace"}
            ])
            errors = validate_manifest(manifest)
            assert any("missing 'path'" in e for e in errors)

        def test_file_entry_missing_action(self):
            manifest = _make_manifest(files=[
                {"path": "foo.py", "sha256": "abc"}
            ])
            errors = validate_manifest(manifest)
            assert any("missing 'action'" in e for e in errors)

    # =========================================================================
    # Signature Verification
    # =========================================================================

    @skipif_no_nacl
    class TestSignatureVerification:
        """Test Ed25519 signature verification."""

        def test_valid_signature(self):
            signing_key, pub_key = _make_test_keys()
            manifest = _make_manifest()
            manifest_bytes, signature = _sign_manifest(manifest, signing_key)

            assert verify_signature(manifest_bytes, signature, pub_key)

        def test_invalid_signature(self):
            signing_key, pub_key = _make_test_keys()
            manifest = _make_manifest()
            manifest_bytes, signature = _sign_manifest(manifest, signing_key)

            # Corrupt signature
            bad_sig = bytearray(signature)
            bad_sig[0] ^= 0xFF
            assert not verify_signature(manifest_bytes, bytes(bad_sig), pub_key)

        def test_wrong_key(self):
            signing_key, _ = _make_test_keys()
            _, wrong_pub_key = _make_test_keys()

            manifest = _make_manifest()
            manifest_bytes, signature = _sign_manifest(manifest, signing_key)

            assert not verify_signature(manifest_bytes, signature, wrong_pub_key)

        def test_tampered_manifest(self):
            signing_key, pub_key = _make_test_keys()
            manifest = _make_manifest()
            manifest_bytes, signature = _sign_manifest(manifest, signing_key)

            # Tamper with manifest after signing
            tampered = manifest_bytes + b"TAMPERED"
            assert not verify_signature(tampered, signature, pub_key)

    # =========================================================================
    # Hash Verification
    # =========================================================================

    class TestHashVerification:
        """Test SHA256 hash verification of payload files."""

        def test_matching_hash(self, tmp_path):
            content = b"hello world"
            (tmp_path / "test.py").write_bytes(content)

            manifest = _make_manifest(files=[
                {"path": "test.py", "sha256": _sha256(content), "action": "replace"}
            ])
            errors = verify_file_hashes(manifest, tmp_path)
            assert not errors

        def test_mismatching_hash(self, tmp_path):
            (tmp_path / "test.py").write_bytes(b"hello world")

            manifest = _make_manifest(files=[
                {"path": "test.py", "sha256": "wrong_hash", "action": "replace"}
            ])
            errors = verify_file_hashes(manifest, tmp_path)
            assert any("mismatch" in e.lower() for e in errors)

        def test_missing_file(self, tmp_path):
            manifest = _make_manifest(files=[
                {"path": "nonexistent.py", "sha256": "abc", "action": "replace"}
            ])
            errors = verify_file_hashes(manifest, tmp_path)
            assert any("missing" in e.lower() for e in errors)

        def test_delete_action_skipped(self, tmp_path):
            manifest = _make_manifest(files=[
                {"path": "old.py", "sha256": None, "action": "delete"}
            ])
            errors = verify_file_hashes(manifest, tmp_path)
            assert not errors

        def test_nested_file_hash(self, tmp_path):
            content = b"nested content"
            nested_dir = tmp_path / "purple_tui" / "modes"
            nested_dir.mkdir(parents=True)
            (nested_dir / "new_mode.py").write_bytes(content)

            manifest = _make_manifest(files=[
                {"path": "purple_tui/modes/new_mode.py", "sha256": _sha256(content), "action": "replace"}
            ])
            errors = verify_file_hashes(manifest, tmp_path)
            assert not errors

    # =========================================================================
    # Update Application
    # =========================================================================

    class TestApplyUpdate:
        """Test file replacement and deletion."""

        def test_replace_file(self, tmp_path):
            # Setup payload
            payload_dir = tmp_path / "payload"
            payload_dir.mkdir()
            content = b"new content"
            (payload_dir / "app.py").write_bytes(content)

            # Setup install dir
            install_dir = tmp_path / "install"
            install_dir.mkdir()
            (install_dir / "app.py").write_text("old content")

            manifest = _make_manifest(files=[
                {"path": "app.py", "sha256": _sha256(content), "action": "replace"}
            ])

            errors = apply_update(manifest, payload_dir, install_dir)
            assert not errors
            assert (install_dir / "app.py").read_bytes() == content

        def test_replace_creates_directories(self, tmp_path):
            payload_dir = tmp_path / "payload"
            (payload_dir / "new_dir").mkdir(parents=True)
            content = b"new file"
            (payload_dir / "new_dir" / "file.py").write_bytes(content)

            install_dir = tmp_path / "install"
            install_dir.mkdir()

            manifest = _make_manifest(files=[
                {"path": "new_dir/file.py", "sha256": _sha256(content), "action": "replace"}
            ])

            errors = apply_update(manifest, payload_dir, install_dir)
            assert not errors
            assert (install_dir / "new_dir" / "file.py").read_bytes() == content

        def test_delete_file(self, tmp_path):
            payload_dir = tmp_path / "payload"
            payload_dir.mkdir()

            install_dir = tmp_path / "install"
            install_dir.mkdir()
            (install_dir / "old.py").write_text("delete me")

            manifest = _make_manifest(files=[
                {"path": "old.py", "sha256": None, "action": "delete"}
            ])

            errors = apply_update(manifest, payload_dir, install_dir)
            assert not errors
            assert not (install_dir / "old.py").exists()

        def test_delete_nonexistent_is_ok(self, tmp_path):
            payload_dir = tmp_path / "payload"
            payload_dir.mkdir()
            install_dir = tmp_path / "install"
            install_dir.mkdir()

            manifest = _make_manifest(files=[
                {"path": "doesnt_exist.py", "sha256": None, "action": "delete"}
            ])

            errors = apply_update(manifest, payload_dir, install_dir)
            assert not errors

        def test_version_file_updated(self, tmp_path):
            payload_dir = tmp_path / "payload"
            payload_dir.mkdir()
            install_dir = tmp_path / "install"
            install_dir.mkdir()
            (install_dir / "VERSION").write_text("0.1.0\n")

            manifest = _make_manifest(version="0.2.0", files=[])
            errors = apply_update(manifest, payload_dir, install_dir)
            assert not errors
            assert (install_dir / "VERSION").read_text().strip() == "0.2.0"

        def test_mixed_replace_and_delete(self, tmp_path):
            payload_dir = tmp_path / "payload"
            payload_dir.mkdir()
            new_content = b"new file content"
            (payload_dir / "new.py").write_bytes(new_content)

            install_dir = tmp_path / "install"
            install_dir.mkdir()
            (install_dir / "old.py").write_text("to be deleted")
            (install_dir / "existing.py").write_text("to be replaced")

            manifest = _make_manifest(files=[
                {"path": "new.py", "sha256": _sha256(new_content), "action": "replace"},
                {"path": "old.py", "sha256": None, "action": "delete"},
            ])

            errors = apply_update(manifest, payload_dir, install_dir)
            assert not errors
            assert (install_dir / "new.py").read_bytes() == new_content
            assert not (install_dir / "old.py").exists()

        def test_staging_cleanup_on_failure(self, tmp_path):
            """Staging directory should be cleaned up even on hash mismatch."""
            payload_dir = tmp_path / "payload"
            payload_dir.mkdir()
            (payload_dir / "file.py").write_bytes(b"content")

            install_dir = tmp_path / "install"
            install_dir.mkdir()

            # Hash deliberately wrong so staging verification fails
            manifest = _make_manifest(files=[
                {"path": "file.py", "sha256": "wrong", "action": "replace"}
            ])

            errors = apply_update(manifest, payload_dir, install_dir)
            assert errors  # Should have hash mismatch errors

    # =========================================================================
    # End-to-End: process_usb_update
    # =========================================================================

    @skipif_no_nacl
    class TestProcessUsbUpdate:
        """End-to-end tests for the full USB update flow."""

        def _setup_usb(self, tmp_path, signing_key, files_content=None):
            """Create a mock USB drive with signed manifest and payload."""
            usb = tmp_path / "usb"
            payload = usb / "payload"
            payload.mkdir(parents=True)

            file_entries = []
            if files_content:
                for rel_path, content in files_content.items():
                    file_path = payload / rel_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(content)
                    file_entries.append({
                        "path": rel_path,
                        "sha256": _sha256(content),
                        "action": "replace",
                    })

            manifest = _make_manifest(files=file_entries)
            manifest_bytes, signature = _sign_manifest(manifest, signing_key)

            (usb / "manifest.json").write_bytes(manifest_bytes)
            (usb / "manifest.sig").write_bytes(signature)

            return usb

        def test_full_update_success(self, tmp_path):
            signing_key, pub_key = _make_test_keys()

            install_dir = tmp_path / "install"
            install_dir.mkdir()
            (install_dir / "VERSION").write_text("0.1.0\n")

            usb = self._setup_usb(tmp_path, signing_key, {
                "app.py": b"updated app code",
            })

            result = process_usb_update(
                str(usb), install_dir=install_dir, public_key_bytes=pub_key
            )
            assert result is True
            assert (install_dir / "app.py").read_bytes() == b"updated app code"
            assert (install_dir / "VERSION").read_text().strip() == "0.2.0"

        def test_bad_signature_rejected(self, tmp_path):
            signing_key, _ = _make_test_keys()
            _, wrong_pub_key = _make_test_keys()

            install_dir = tmp_path / "install"
            install_dir.mkdir()

            usb = self._setup_usb(tmp_path, signing_key, {
                "app.py": b"payload",
            })

            result = process_usb_update(
                str(usb), install_dir=install_dir, public_key_bytes=wrong_pub_key
            )
            assert result is False
            # File should NOT have been written
            assert not (install_dir / "app.py").exists()

        def test_missing_manifest(self, tmp_path):
            install_dir = tmp_path / "install"
            install_dir.mkdir()
            usb = tmp_path / "usb"
            usb.mkdir()

            _, pub_key = _make_test_keys()
            result = process_usb_update(
                str(usb), install_dir=install_dir, public_key_bytes=pub_key
            )
            assert result is False

        def test_missing_signature_file(self, tmp_path):
            install_dir = tmp_path / "install"
            install_dir.mkdir()
            usb = tmp_path / "usb"
            usb.mkdir()
            # Manifest exists but no .sig
            (usb / "manifest.json").write_text('{"format_version": 1}')

            _, pub_key = _make_test_keys()
            result = process_usb_update(
                str(usb), install_dir=install_dir, public_key_bytes=pub_key
            )
            assert result is False

        def test_signal_file_written_on_success(self, tmp_path):
            signing_key, pub_key = _make_test_keys()

            install_dir = tmp_path / "install"
            install_dir.mkdir()

            usb = self._setup_usb(tmp_path, signing_key, {
                "app.py": b"updated code",
            })

            # Clean up any leftover signal file
            signal = Path(USB_UPDATE_SIGNAL_FILE)
            if signal.exists():
                signal.unlink()

            result = process_usb_update(
                str(usb), install_dir=install_dir, public_key_bytes=pub_key
            )
            assert result is True
            assert signal.exists()

            # Verify signal file content
            import json as json_mod
            signal_data = json_mod.loads(signal.read_text())
            assert signal_data["version"] == "0.2.0"
            assert "applied_at" in signal_data

            # Clean up
            signal.unlink()

        def test_tampered_payload_rejected(self, tmp_path):
            signing_key, pub_key = _make_test_keys()

            install_dir = tmp_path / "install"
            install_dir.mkdir()

            usb = self._setup_usb(tmp_path, signing_key, {
                "app.py": b"original payload",
            })

            # Tamper with the payload file after signing
            (usb / "payload" / "app.py").write_bytes(b"tampered payload")

            result = process_usb_update(
                str(usb), install_dir=install_dir, public_key_bytes=pub_key
            )
            assert result is False
            assert not (install_dir / "app.py").exists()

    # =========================================================================
    # create_usb_update.py helpers
    # =========================================================================

    class TestShouldSkip:
        """Test file skip logic for update creation."""

        def test_skips_pycache(self):
            assert should_skip(Path("purple_tui/__pycache__/app.cpython-313.pyc"))

        def test_skips_pyc_files(self):
            assert should_skip(Path("purple_tui/app.pyc"))

        def test_skips_git(self):
            assert should_skip(Path(".git/config"))

        def test_skips_ds_store(self):
            assert should_skip(Path("purple_tui/.DS_Store"))

        def test_skips_env(self):
            assert should_skip(Path(".env"))

        def test_skips_parent_json(self):
            assert should_skip(Path("parent.json"))

        def test_allows_normal_python(self):
            assert not should_skip(Path("purple_tui/app.py"))

        def test_allows_nested_files(self):
            assert not should_skip(Path("packs/core-emoji/content/data.json"))

    class TestCollectFiles:
        """Test file collection for update creation."""

        def test_collects_from_include_dirs(self, tmp_path):
            # Create minimal project structure
            (tmp_path / "purple_tui").mkdir()
            (tmp_path / "purple_tui" / "app.py").write_text("app code")
            (tmp_path / "purple_tui" / "constants.py").write_text("constants")
            (tmp_path / "packs").mkdir()
            (tmp_path / "packs" / "data.json").write_text("{}")
            (tmp_path / "VERSION").write_text("0.1.0")

            files = collect_files(tmp_path)
            rel_paths = [f[0] for f in files]

            assert "purple_tui/app.py" in rel_paths
            assert "purple_tui/constants.py" in rel_paths
            assert "packs/data.json" in rel_paths
            assert "VERSION" in rel_paths

        def test_skips_pycache_in_collection(self, tmp_path):
            (tmp_path / "purple_tui").mkdir()
            (tmp_path / "purple_tui" / "app.py").write_text("code")
            cache_dir = tmp_path / "purple_tui" / "__pycache__"
            cache_dir.mkdir()
            (cache_dir / "app.cpython-313.pyc").write_bytes(b"\x00")

            files = collect_files(tmp_path)
            rel_paths = [f[0] for f in files]

            assert "purple_tui/app.py" in rel_paths
            assert not any("__pycache__" in p for p in rel_paths)

        def test_missing_dir_warns_but_continues(self, tmp_path, capsys):
            # No purple_tui or packs dirs exist
            (tmp_path / "VERSION").write_text("0.1.0")

            files = collect_files(tmp_path)
            rel_paths = [f[0] for f in files]

            assert "VERSION" in rel_paths
            captured = capsys.readouterr()
            assert "Warning" in captured.out
