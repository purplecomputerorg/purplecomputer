# Purple Computer Updates

Purple Computer includes a lightweight, secure update system for packs and core files.

## Overview

The update system is designed to be:
- **Simple** - No accounts, logins, or complex infrastructure
- **Secure** - Hash verification, HTTPS only, validation
- **Minimal** - Single JSON feed, static hosting friendly
- **Parent-controlled** - Updates require parent mode access

## How Updates Work

1. **Check** - Purple Computer fetches a JSON feed from a URL
2. **Compare** - Compares available versions with installed versions
3. **Download** - Downloads new/updated files over HTTPS
4. **Verify** - Checks SHA256 hashes
5. **Install** - Installs via the pack manager

No telemetry, tracking, or server-side logic required.

## Update Feed Format

The update feed is a simple JSON file hosted at a static URL:

```json
{
  "packs": [
    {
      "id": "core-emoji",
      "name": "Core Emoji Pack",
      "version": "1.1.0",
      "url": "https://purplecomputer.org/packs/core-emoji.purplepack",
      "hash": "sha256:abc123def456...",
      "description": "Added 20 new emoji!"
    },
    {
      "id": "education-basics",
      "name": "Education Basics Pack",
      "version": "1.0.1",
      "url": "https://purplecomputer.org/packs/education-basics.purplepack",
      "hash": "sha256:789ghi012jkl...",
      "description": "Fixed typos in definitions"
    }
  ],
  "core_files": [
    {
      "path": "repl.py",
      "version": "2.0.0",
      "url": "https://purplecomputer.org/core/repl.py",
      "hash": "sha256:mno345pqr678...",
      "description": "Security improvements"
    }
  ]
}
```

### Feed Fields

**For packs:**
- `id` - Pack identifier (must match manifest)
- `name` - Display name
- `version` - Semantic version (x.y.z)
- `url` - Download URL (HTTPS only)
- `hash` - SHA256 hash (optional but recommended)
- `description` - What's new in this version

**For core files:**
- `path` - File path relative to `~/.purple/`
- `version` - Semantic version
- `url` - Download URL (HTTPS only)
- `hash` - SHA256 hash (required for core files)
- `description` - What changed

## Checking for Updates

### Via Parent Mode

1. Press Ctrl+C (or Ctrl+Alt+P) to enter parent mode
2. Enter parent password
3. Select "Check for updates" (option 2)
4. Purple Computer fetches the feed and displays available updates
5. Confirm to install all updates

### Programmatically

```python
from update_manager import create_update_manager

# Create update manager
updater = create_update_manager()

# Check for updates
success, updates = updater.check_for_updates()

if success:
    for update in updates:
        print(f"{update['name']} - {update['version']}")
```

## Installing Updates

Updates can be installed individually or all at once:

```python
from update_manager import create_update_manager

updater = create_update_manager()
success, updates = updater.check_for_updates()

if updates:
    # Install all
    results = updater.install_all_updates(updates)

    # Or install individually
    for update in updates:
        success, msg = updater.install_update(update)
        print(msg)
```

## Hosting an Update Feed

### Option 1: Static File Hosting

Host `feed.json` on any web server:

```bash
# Create feed
cat > feed.json <<EOF
{
  "packs": [
    {
      "id": "my-pack",
      "name": "My Pack",
      "version": "1.0.0",
      "url": "https://example.com/packs/my-pack.purplepack",
      "hash": "sha256:..."
    }
  ]
}
EOF

# Upload to web server
scp feed.json user@example.com:/var/www/html/purplecomputer/
scp my-pack.purplepack user@example.com:/var/www/html/purplecomputer/packs/
```

### Option 2: GitHub Releases

Use GitHub releases to host pack files:

1. Create release in your repo
2. Attach `.purplepack` files as assets
3. Create `feed.json` with release asset URLs

```json
{
  "packs": [
    {
      "id": "my-pack",
      "name": "My Pack",
      "version": "1.0.0",
      "url": "https://github.com/user/repo/releases/download/v1.0.0/my-pack.purplepack",
      "hash": "sha256:..."
    }
  ]
}
```

Host `feed.json` via GitHub Pages.

### Option 3: CDN

Use a CDN like Cloudflare or jsDelivr:

```bash
# Push to GitHub
git add packs/
git commit -m "Add pack files"
git push

# Reference via CDN
# https://cdn.jsdelivr.net/gh/user/repo@main/packs/my-pack.purplepack
```

## Generating File Hashes

Always include SHA256 hashes for security:

```bash
# Generate hash
sha256sum my-pack.purplepack
# Output: abc123def456... my-pack.purplepack

# Use in feed
"hash": "sha256:abc123def456..."
```

Or use Python:

```python
import hashlib

with open('my-pack.purplepack', 'rb') as f:
    hash_value = hashlib.sha256(f.read()).hexdigest()
    print(f"sha256:{hash_value}")
```

## Custom Update Feed

By default, Purple Computer uses:
```
https://purplecomputer.org/updates/feed.json
```

To use a custom feed, modify the update manager:

```python
from update_manager import UpdateManager
from pathlib import Path

custom_feed = "https://my-school.edu/purple/feed.json"
packs_dir = Path.home() / '.purple' / 'packs'

updater = UpdateManager(custom_feed, packs_dir)
```

Or set in a config file (future feature).

## Automatic Updates

### At Boot (Not Recommended)

To check for updates at startup, add to `repl.py`:

```python
# In main()
from update_manager import create_update_manager

updater = create_update_manager()
success, updates = updater.check_for_updates()

# Silently install if available
if success and updates:
    updater.install_all_updates(updates)
```

**Warning:** Auto-updates can be disruptive. Require parent confirmation instead.

### On a Schedule

Use a systemd timer:

```ini
# /etc/systemd/system/purple-update.timer
[Unit]
Description=Purple Computer Update Check

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/purple-update.service
[Unit]
Description=Purple Computer Update Service

[Service]
Type=oneshot
User=purple
ExecStart=/home/purple/.purple/check_updates.sh
```

Enable:
```bash
systemctl enable purple-update.timer
systemctl start purple-update.timer
```

## Update Security

### Verification Steps

1. **HTTPS only** - Update feed and downloads must use HTTPS
2. **Hash checking** - SHA256 hashes are verified
3. **Manifest validation** - Packs must have valid manifests
4. **Path validation** - No path traversal allowed
5. **Parent authentication** - Updates require parent password

### Best Practices

- Always include SHA256 hashes
- Use HTTPS for all URLs
- Test updates before publishing
- Version updates properly (semantic versioning)
- Keep feed URLs stable (don't change frequently)

### Threat Model

Purple Computer's update system protects against:
- **Man-in-the-middle attacks** - HTTPS encryption
- **Tampered files** - Hash verification
- **Malicious packs** - Manifest validation
- **Unauthorized updates** - Parent authentication

It does NOT protect against:
- **Compromised feed server** - If your server is hacked, malicious updates could be served
- **Social engineering** - If a parent installs a malicious pack manually
- **Malicious mode code** - Mode packs can run arbitrary Python

**Solution:** Only use trusted feed sources and review mode packs before installing.

## Update Workflow Example

### For Pack Creators

1. Create or update your pack:
```bash
# Update version in manifest.json
vim my-pack/manifest.json  # Change version to 1.1.0

# Rebuild pack
./scripts/build_pack.py my-pack my-pack-v1.1.0.purplepack
```

2. Generate hash:
```bash
sha256sum my-pack-v1.1.0.purplepack
```

3. Upload pack file to hosting

4. Update `feed.json`:
```json
{
  "packs": [
    {
      "id": "my-pack",
      "version": "1.1.0",
      "url": "https://example.com/packs/my-pack-v1.1.0.purplepack",
      "hash": "sha256:newhashvalue...",
      "description": "Added cool new features"
    }
  ]
}
```

5. Upload updated `feed.json`

6. Test:
```python
from update_manager import create_update_manager

updater = create_update_manager()
success, updates = updater.check_for_updates()
print(updates)
```

### For System Administrators

1. Set up Purple Computer devices to use your feed
2. Create `feed.json` on your server
3. Upload pack files
4. Notify parents when updates are available
5. Parents install via parent mode

## Troubleshooting

### "Could not connect to update server"

- Check internet connection
- Verify feed URL is correct and accessible
- Check firewall isn't blocking HTTPS
- Try accessing feed URL in a browser

### "Hash mismatch"

- File was corrupted during download
- Hash in feed.json is incorrect
- File was modified after hash was generated

**Solution:** Regenerate hash and update feed.json

### Updates Don't Appear

- Check version numbers are higher than installed versions
- Verify feed.json syntax is valid
- Check pack IDs match exactly
- Look for errors in `~/.purple/pack_errors.log`

### "Pack already installed"

This means the pack ID exists but the version check passed.

**Solution:** Increment version number in both manifest and feed.

## Offline Usage

Purple Computer works perfectly offline. Updates are optional.

To distribute updates offline:

1. Copy `.purplepack` files to USB drive
2. Install manually via parent mode (option 3)
3. No internet required

## Future Enhancements

Planned features for the update system:

- **Update scheduling** - Configure check frequency
- **Update notifications** - Visual indicators when updates available
- **Selective updates** - Choose which packs to update
- **Rollback** - Revert to previous pack version
- **Update history** - Log of installed updates
- **Multiple feeds** - Subscribe to multiple update sources

---

Keep Purple Computer fresh with regular updates! 💜
