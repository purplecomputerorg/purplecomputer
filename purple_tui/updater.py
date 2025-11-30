"""
Purple Computer Auto-Updater

Checks for updates on startup (max once per day).
- Minor updates: applied automatically via git pull
- Breaking updates: prompt shown, requires confirmation
"""

import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# Where Purple is installed
APP_DIR = Path(__file__).parent.parent.resolve()

# Remote version info (raw GitHub URL)
VERSION_URL = "https://raw.githubusercontent.com/purplecomputerorg/purplecomputer/main/version.json"

# Local state file (tracks last update check)
STATE_FILE = Path.home() / ".purple_computer_update_state"


def get_local_version() -> str:
    """Read local VERSION file"""
    version_file = APP_DIR / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return "0.0.0"


def get_local_breaking_version() -> int:
    """Read local BREAKING_VERSION file"""
    breaking_file = APP_DIR / "BREAKING_VERSION"
    if breaking_file.exists():
        try:
            return int(breaking_file.read_text().strip())
        except ValueError:
            return 0
    return 0


def fetch_remote_version() -> Optional[dict]:
    """Fetch version.json from remote"""
    try:
        with urllib.request.urlopen(VERSION_URL, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def should_check_updates() -> bool:
    """Only check once per day"""
    if not STATE_FILE.exists():
        return True

    try:
        state = json.loads(STATE_FILE.read_text())
        last_check = datetime.fromisoformat(state.get("last_check", "2000-01-01"))
        return datetime.now() - last_check > timedelta(days=1)
    except (json.JSONDecodeError, ValueError):
        return True


def save_check_state() -> None:
    """Record that we checked for updates"""
    state = {"last_check": datetime.now().isoformat()}
    STATE_FILE.write_text(json.dumps(state))


def do_update() -> bool:
    """Perform git pull to update"""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=APP_DIR,
            capture_output=True,
            timeout=30
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def parse_version(v: str) -> tuple:
    """Parse version string to tuple for comparison"""
    try:
        parts = v.split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def check_for_updates() -> Optional[dict]:
    """
    Check for updates. Returns dict with update info, or None if no update.

    Returns:
        None - no update available or check skipped
        {"type": "minor", "version": "x.y.z"} - auto-update available
        {"type": "breaking", "version": "x.y.z", "message": "..."} - breaking update needs confirmation
    """
    if not should_check_updates():
        return None

    remote = fetch_remote_version()
    if not remote:
        return None

    save_check_state()

    local_version = get_local_version()
    remote_version = remote.get("version", "0.0.0")

    # Compare versions
    if parse_version(remote_version) <= parse_version(local_version):
        return None  # Already up to date

    # Check if breaking
    local_breaking = get_local_breaking_version()
    remote_breaking = remote.get("breaking_version", 0)

    if remote_breaking > local_breaking:
        return {
            "type": "breaking",
            "version": remote_version,
            "message": remote.get("message")
        }
    else:
        return {
            "type": "minor",
            "version": remote_version
        }


def auto_update_if_available() -> Optional[str]:
    """
    Called on app startup. Checks for updates and auto-applies minor ones.

    Returns:
        None - no update or update failed
        "updated" - minor update applied, restart needed
        "breaking:x.y.z:message" - breaking update available, needs user confirmation
    """
    update = check_for_updates()

    if not update:
        return None

    if update["type"] == "minor":
        if do_update():
            return "updated"
        return None

    elif update["type"] == "breaking":
        msg = update.get("message") or "A new version is available"
        return f"breaking:{update['version']}:{msg}"

    return None


def apply_breaking_update() -> bool:
    """Called when user confirms breaking update"""
    return do_update()
