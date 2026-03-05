#!/usr/bin/env python3
"""
Generate Ed25519 key pair for signing USB updates.

Private key: tools/update-key.priv (hex-encoded, chmod 600, gitignored)
Public key:  update-key.pub (hex-encoded, baked into golden image at build time)

Usage:
    python3 tools/usb_update_keygen.py
    # or: just keygen
"""

import os
import sys
from pathlib import Path

try:
    from nacl.signing import SigningKey
except ImportError:
    print("PyNaCl is required. Install it with: pip install pynacl")
    sys.exit(1)


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    priv_path = script_dir / "update-key.priv"
    pub_path = project_root / "update-key.pub"

    if priv_path.exists():
        print(f"Private key already exists: {priv_path}")
        print("Delete it first if you want to generate a new key pair.")
        sys.exit(1)

    # Generate key pair
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key

    # Save private key (hex-encoded)
    priv_path.write_text(signing_key.encode().hex() + "\n")
    os.chmod(priv_path, 0o600)
    print(f"Private key saved: {priv_path}")

    # Save public key (hex-encoded)
    pub_path.write_text(verify_key.encode().hex() + "\n")
    print(f"Public key saved:  {pub_path}")

    print()
    print("The public key will be baked into the golden image at build time.")
    print("Keep the private key safe. It is gitignored.")


if __name__ == "__main__":
    main()
