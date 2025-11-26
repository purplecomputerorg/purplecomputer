"""
Purple Computer Parent Authentication
Simple password-based protection for parent mode
"""

import json
import hashlib
import secrets
from pathlib import Path
from typing import Optional


class ParentAuth:
    """Manages parent mode password authentication"""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize parent authentication

        Args:
            config_path: Path to password config file (default: ~/.purple/parent.json)
        """
        if config_path is None:
            config_path = Path.home() / '.purple' / 'parent.json'

        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self._load_config()

    def _load_config(self):
        """Load password config from file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
            except Exception:
                # If config is corrupted, reset to default
                self._create_default_config()
        else:
            self._create_default_config()

    def _create_default_config(self):
        """Create default config with no password set"""
        self.config = {
            'password_hash': None,
            'salt': None,
            'hint': None,
            'first_run': True
        }
        self._save_config()

    def _save_config(self):
        """Save password config to file"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

        # Set restrictive permissions (owner only)
        self.config_path.chmod(0o600)

    def _hash_password(self, password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """
        Hash a password using SHA256 with salt

        Args:
            password: Plain text password
            salt: Optional salt (generated if not provided)

        Returns:
            Tuple of (hash, salt)
        """
        if salt is None:
            salt = secrets.token_hex(16)

        hash_input = (password + salt).encode('utf-8')
        password_hash = hashlib.sha256(hash_input).hexdigest()

        return password_hash, salt

    def has_password(self) -> bool:
        """Check if a parent password is set"""
        return self.config.get('password_hash') is not None

    def is_first_run(self) -> bool:
        """Check if this is the first run (no password set yet)"""
        return self.config.get('first_run', True)

    def set_password(self, password: str, hint: Optional[str] = None) -> tuple[bool, str]:
        """
        Set the parent password

        Args:
            password: New password
            hint: Optional password hint

        Returns:
            Tuple of (success, message)
        """
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters"

        password_hash, salt = self._hash_password(password)

        self.config['password_hash'] = password_hash
        self.config['salt'] = salt
        self.config['hint'] = hint
        self.config['first_run'] = False

        self._save_config()

        return True, "Parent password set successfully"

    def change_password(self, old_password: str, new_password: str, hint: Optional[str] = None) -> tuple[bool, str]:
        """
        Change the parent password

        Args:
            old_password: Current password
            new_password: New password
            hint: Optional new password hint

        Returns:
            Tuple of (success, message)
        """
        if not self.has_password():
            return False, "No password is currently set"

        # Verify old password
        if not self.verify_password(old_password):
            return False, "Current password is incorrect"

        # Set new password
        return self.set_password(new_password, hint)

    def verify_password(self, password: str) -> bool:
        """
        Verify a password attempt

        Args:
            password: Password to verify

        Returns:
            True if password is correct, False otherwise
        """
        if not self.has_password():
            # If no password is set, always return True (open access)
            return True

        stored_hash = self.config['password_hash']
        salt = self.config['salt']

        computed_hash, _ = self._hash_password(password, salt)

        return computed_hash == stored_hash

    def get_hint(self) -> Optional[str]:
        """Get the password hint (if set)"""
        return self.config.get('hint')

    def reset_password(self) -> tuple[bool, str]:
        """
        Reset password to none (requires physical access)
        This should only be called from a recovery menu
        """
        self.config['password_hash'] = None
        self.config['salt'] = None
        self.config['hint'] = None
        self.config['first_run'] = True

        self._save_config()

        return True, "Parent password has been reset"

    def prompt_for_password(self, prompt: str = "Enter parent password: ", max_attempts: int = 3) -> bool:
        """
        Prompt user for password with limited attempts

        Args:
            prompt: Password prompt text
            max_attempts: Maximum number of attempts

        Returns:
            True if authentication successful, False otherwise
        """
        import getpass

        # If no password is set and it's first run, set one up
        if self.is_first_run():
            print("\n" + "=" * 50)
            print("PURPLE COMPUTER - PARENT MODE SETUP")
            print("=" * 50)
            print("\nNo parent password is set.")
            print("You need to create one to protect parent mode.\n")

            while True:
                new_password = getpass.getpass("Create parent password (4+ chars): ")
                if len(new_password) < 4:
                    print("Password must be at least 4 characters. Try again.")
                    continue

                confirm = getpass.getpass("Confirm password: ")
                if new_password != confirm:
                    print("Passwords don't match. Try again.")
                    continue

                hint = input("Password hint (optional, press Enter to skip): ").strip()
                hint = hint if hint else None

                success, msg = self.set_password(new_password, hint)
                if success:
                    print(f"\n✓ {msg}\n")
                    return True
                else:
                    print(f"\n✗ {msg}\n")
                    return False

        # If no password is set but not first run, allow access
        if not self.has_password():
            return True

        # Prompt for password
        hint = self.get_hint()
        if hint:
            print(f"\nHint: {hint}")

        for attempt in range(max_attempts):
            password = getpass.getpass(prompt)

            if self.verify_password(password):
                return True

            remaining = max_attempts - attempt - 1
            if remaining > 0:
                print(f"✗ Incorrect password. {remaining} attempt(s) remaining.")
            else:
                print("✗ Incorrect password. Access denied.")

        return False


# Global instance
_global_auth = None


def get_auth() -> ParentAuth:
    """Get the global parent authentication instance"""
    global _global_auth
    if _global_auth is None:
        _global_auth = ParentAuth()
    return _global_auth
