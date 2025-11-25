# Purple Computer Manual

Complete reference for developing, testing, installing, and using Purple Computer.

---

## Table of Contents

1. [Development & Testing](#development--testing)
2. [Pack System](#pack-system)
3. [Parent Mode](#parent-mode)
4. [Update System](#update-system)
5. [Installation](#installation)
6. [Architecture](#architecture)
7. [Troubleshooting](#troubleshooting)

---

## Development & Testing

### Quick Setup

```bash
# One-time setup
make setup

# Run locally (Mac/Linux)
make run

# Run in Docker (full Ubuntu simulation)
make run-docker
```

### Testing Modes

**Local Runner** (Fast - Mac/Linux)
- Direct Python execution on your machine
- Perfect for quick iteration
- No Ubuntu, no X11

**Docker Runner** (Full Simulation)
- Ubuntu 22.04 container
- `purple` user with locked password
- Near-production environment
- Run: `./scripts/run_docker.sh`

**Hardware Install** (Production)
- Complete experience with X11, auto-login, full screen
- Build ISO: see [Installation](#installation) section

### Feature Comparison

| Feature | Local | Docker | Hardware |
|---------|-------|--------|----------|
| REPL | ✅ | ✅ | ✅ |
| Packs | ✅ | ✅ | ✅ |
| Parent Mode | ✅ | ✅ | ✅ |
| Ubuntu 22.04 | ❌ | ✅ | ✅ |
| X11/Kitty | ❌ | ❌ | ✅ |
| Auto-login | ❌ | ❌ | ✅ |

### Development Workflow

1. Edit code in `purple_repl/`
2. Run `make run` to test
3. Iterate
4. Test in Docker before hardware deployment

### Available Scripts

```bash
make setup          # Install dependencies
make run            # Run locally
make run-docker     # Run in Docker
make build-packs    # Build example packs
make clean          # Clean test environment
```

---

## Pack System

### What Are Packs?

Packs are modular content bundles (`.purplepack` files) containing:
- **emoji** - Variable name → emoji mappings
- **definitions** - Word → definition mappings
- **modes** - Python mode classes
- **sounds** - Audio files
- **mixed** - Combination of above

### Pack Structure

```
mypack.purplepack (tar.gz archive)
├── manifest.json
└── content/
    ├── emoji.json
    ├── definitions.json
    ├── modes/*.py
    └── sounds/*.wav
```

### Creating a Pack

**1. Create pack source:**
```bash
mkdir -p mypack/content

cat > mypack/manifest.json <<EOF
{
  "id": "mypack",
  "name": "My Pack",
  "version": "1.0.0",
  "type": "emoji"
}
EOF

cat > mypack/content/emoji.json <<EOF
{
  "unicorn": "🦄",
  "dragon": "🐉"
}
EOF
```

**2. Build pack:**
```bash
./scripts/build_pack.py mypack mypack.purplepack
```

**3. Install pack:**
- Run Purple Computer
- Press Ctrl+C (parent mode)
- Option 3: Install packs
- Enter path to `mypack.purplepack`

### Manifest Format

Required fields:
```json
{
  "id": "unique-id",           // lowercase, hyphens only
  "name": "Display Name",
  "version": "1.0.0",          // semantic versioning
  "type": "emoji"              // emoji|definitions|mode|sounds|mixed
}
```

Optional fields: `description`, `author`, `url`, `license`

### Pack Types

**Emoji Pack** (`content/emoji.json`):
```json
{
  "cat": "🐱",
  "dog": "🐶"
}
```

**Definitions Pack** (`content/definitions.json`):
```json
{
  "computer": "A machine that follows instructions",
  "code": "Instructions written for computers"
}
```

**Mode Pack** (`content/modes/mymode.py`):
```python
class MyMode:
    def __init__(self):
        self.name = "My Mode"

    def activate(self):
        print("✨ My Mode activated!")
```

**Sound Pack** (`content/sounds/`):
- Supported: `.wav`, `.ogg`, `.mp3`
- Each file becomes accessible by name

### Pack Security

Packs are validated before installation:
- ✅ Manifest format checked
- ✅ Path traversal prevented
- ✅ Hash verification (if provided)
- ⚠️ Never install packs from untrusted sources

### Example Packs

Purple Computer includes:
- **core-emoji** - 100+ emoji (animals, nature, food, symbols)
- **education-basics** - CS definitions for kids

Find them in `packs/` directory.

---

## Parent Mode

### Password Policy

**No System Password:**
- `purple` user has NO password
- Account is locked (can't login with password)
- Auto-login on TTY1 only

**Parent Password:**
- Separate password for parent mode
- Stored in `~/.purple/parent.json`
- SHA256 hashed with unique salt
- Created on first parent mode access

### Accessing Parent Mode

1. Press **Ctrl+C** while Purple Computer is running
2. First time: create parent password (4+ characters)
3. Subsequent times: enter your password
4. Access parent menu

### Parent Menu Options

```
1. Return to Purple Computer  - Exit to kid mode
2. Check for updates          - Fetch and install updates
3. Install packs              - Install .purplepack files
4. List installed packs       - Show all packs
5. Change parent password     - Update password
6. Open system shell          - Bash shell (advanced)
7. Network settings           - Configure network
8. Shut down                  - Power off
9. Restart                    - Reboot
```

### Parent Password Best Practices

**Do:**
- Use 8-10+ characters (minimum 4)
- Set a hint you'll remember
- Write it down somewhere safe
- Share with your co-parent

**Don't:**
- Use obvious words (purple, password, 1234)
- Share with kids
- Leave parent mode open unattended

### Password Recovery

If you forget your password:

**Option 1: Reset via filesystem**
```bash
# Boot into recovery mode or live USB
rm /home/purple/.purple/parent.json
```

**Option 2: Reset via shell**
```bash
# If you can access a shell
rm ~/.purple/parent.json
```

Next parent mode access will prompt for new password.

### Security Model

**Protected:**
- ✅ System settings
- ✅ Pack installation
- ✅ Updates
- ✅ Network configuration

**Not Protected:**
- ❌ Physical USB boot
- ❌ TTY switching (Ctrl+Alt+F2)
- ❌ Power button

Purple Computer assumes **physical security** - it's a supervised toy for kids, not a secure workstation.

---

## Update System

### How Updates Work

1. **Check** - Fetch JSON feed from URL (HTTPS)
2. **Compare** - Check versions vs installed
3. **Download** - Get new/updated files
4. **Verify** - Check SHA256 hashes
5. **Install** - Install via pack manager

No telemetry, no tracking, no server-side logic.

### Update Feed Format

```json
{
  "packs": [
    {
      "id": "mypack",
      "name": "My Pack",
      "version": "1.1.0",
      "url": "https://example.com/mypack.purplepack",
      "hash": "sha256:abc123...",
      "description": "What's new"
    }
  ],
  "core_files": [
    {
      "path": "repl.py",
      "version": "2.0.0",
      "url": "https://example.com/repl.py",
      "hash": "sha256:def456...",
      "description": "Security fix"
    }
  ]
}
```

### Checking for Updates

**Via Parent Mode:**
1. Press Ctrl+C
2. Option 2: Check for updates
3. Confirm to install

**Programmatically:**
```python
from update_manager import create_update_manager

updater = create_update_manager()
success, updates = updater.check_for_updates()

if updates:
    results = updater.install_all_updates(updates)
```

### Hosting an Update Feed

**Option 1: Static file hosting**
```bash
# Upload feed.json and packs to any web server
https://yoursite.com/purple/feed.json
https://yoursite.com/purple/packs/mypack.purplepack
```

**Option 2: GitHub Releases**
```bash
# Upload as release assets
https://github.com/user/repo/releases/download/v1.0.0/mypack.purplepack
```

**Option 3: CDN (jsDelivr, Cloudflare)**

### Update Security

- ✅ HTTPS only
- ✅ SHA256 hash verification
- ✅ Manifest validation
- ✅ Parent authentication required
- ⚠️ Compromised feed server = risk

**Only use trusted feed sources.**

### Custom Update Feed

Default: `https://purplecomputer.org/updates/feed.json`

To use custom feed, modify `update_manager.py`:
```python
feed_url = "https://myschool.edu/purple/feed.json"
```

### Offline Usage

Purple Computer works perfectly offline. Updates are optional.

To distribute updates offline:
1. Copy `.purplepack` files to USB
2. Install via parent mode → option 3
3. No internet required

---

## Installation

### Quick Install (ISO)

**1. Build or download ISO**
```bash
cd autoinstall
./build-iso.sh
```

**2. Write to USB**
- **Mac/Windows:** Use [balenaEtcher](https://www.balena.io/etcher/)
- **Linux:** `sudo dd if=purple-computer.iso of=/dev/sdX bs=4M`

**3. Boot from USB**
- Insert USB, power on
- Select boot from USB (usually F12/F2/ESC)
- Installation is automatic (10-15 minutes)
- Remove USB when prompted

**4. First boot**
- System auto-logs into Purple Computer
- First parent mode access: create parent password

### Manual Install (Existing Ubuntu)

On Ubuntu 22.04:
```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
sudo ./autoinstall/files/setup.sh
sudo reboot
```

### What Gets Installed

**System:**
- Ubuntu 22.04 LTS (minimal)
- X11 + Kitty terminal
- Python 3 + IPython

**User:**
- `purple` user (no password, auto-login)
- `kiduser` user (legacy support)

**Purple Computer:**
- REPL in `~/.purple/`
- Packs in `~/.purple/packs/`
- Parent config in `~/.purple/parent.json`

### System Requirements

- x86_64 processor (Intel or AMD)
- 2GB RAM minimum (4GB recommended)
- 8GB storage minimum (16GB recommended)
- USB port for installation

### Building the ISO

**Prerequisites:**
- Ubuntu 22.04 or similar
- 10GB free disk space
- `xorriso`, `isolinux`, `curl` packages

**Build:**
```bash
cd autoinstall
./build-iso.sh
```

This creates `purple-computer.iso` (~1.4GB).

**Test in VM:**
```bash
qemu-system-x86_64 \
  -cdrom purple-computer.iso \
  -m 2048 \
  -boot d \
  -drive file=test-disk.img,format=raw
```

---

## Architecture

### System Overview

```
┌─────────────────────────────────────┐
│       Purple Computer               │
├─────────────────────────────────────┤
│  Kid Mode  │  Parent Mode  │ Updates│
│            │  (password)   │ (HTTPS)│
└─────┬──────┴───────┬───────┴────┬───┘
      │              │            │
      └──────────────┴────────────┘
                     │
            ┌────────▼────────┐
            │  Pack Registry  │
            │  - Emoji        │
            │  - Definitions  │
            │  - Modes        │
            └────────┬────────┘
                     │
      ┌──────────────┴──────────────┐
      │                             │
┌─────▼──────┐            ┌─────────▼──────┐
│Pack Manager│            │   Pack Loader  │
│- Install   │            │   - Validate   │
│- Uninstall │            │   - Load       │
└────────────┘            └────────────────┘
```

### Core Modules

**repl.py** (Main entry point)
- Initialize IPython
- Load packs at startup
- Parent mode handler

**pack_manager.py** (Pack system)
- `PackRegistry` - Content registry
- `PackManager` - Install/uninstall packs

**parent_auth.py** (Authentication)
- Password hashing (SHA256 + salt)
- Password management
- Parent mode protection

**update_manager.py** (Updates)
- Fetch update feed
- Version comparison
- Download & install

### File Structure

```
/home/purple/
  .purple/
    ├── repl.py
    ├── pack_manager.py
    ├── parent_auth.py
    ├── update_manager.py
    ├── emoji_lib.py
    ├── tts.py
    ├── modes/
    ├── packs/              # Installed packs
    └── parent.json         # Parent password (600 perms)

  .ipython/
    └── profile_default/
        └── startup/        # IPython startup scripts
            ├── 10-emoji.py
            └── 20-mode_manager.py
```

### Startup Flow

1. User logs in (auto-login, no password)
2. `.bash_profile` runs → `startx`
3. `.xinitrc` runs → `kitty`
4. Kitty runs → `python3 ~/.purple/repl.py`
5. repl.py:
   - Create PackRegistry
   - Create PackManager
   - Load all packs
   - Install parent escape handler
   - Start IPython
6. IPython runs startup scripts:
   - Load emoji from registry
   - Load modes
7. Kid sees: 💜 prompt

### Security Design

**System Password:** NONE
- `purple` user account locked
- No password login possible
- Auto-login on TTY1 only

**Parent Password:** Required
- Stored in `~/.purple/parent.json`
- SHA256 + unique salt
- File permissions: 600 (owner only)
- Created on first parent mode access

**Network:** Disabled by default, optional

**Updates:** HTTPS only, SHA256 verified

### Performance

**Startup:** < 5 seconds (power-on to REPL)

**Memory:** ~360 MB total
- Base system: ~200 MB
- X11 + Kitty: ~100 MB
- IPython: ~50 MB
- Packs: ~10 MB

**Storage:** Minimal install ~2 GB

---

## Troubleshooting

### Installation Issues

**Installation hangs**
- Check minimum requirements (2GB RAM, 8GB storage)
- Verify ISO integrity: `md5sum purple-computer.iso`
- Try rebuilding ISO
- Check BIOS settings (UEFI vs Legacy)

**System boots to command line**
```bash
# Check systemd service
systemctl status getty@tty1

# View logs
journalctl -u getty@tty1 -b

# Manually start (testing)
startx
```

### REPL Issues

**Kitty won't start**
```bash
# Check X11
echo $DISPLAY

# Check Kitty
which kitty

# Try manually
kitty
```

**Purple REPL crashes**
```bash
# Check Python
python3 --version
ipython3 --version

# Test manually
cd /home/purple/.purple
python3 repl.py
```

**"Module not found" errors**
```bash
pip3 install ipython colorama termcolor packaging
```

### Parent Mode Issues

**Can't access parent mode**
- Press Ctrl+C (not Ctrl+Alt+P - that's not implemented yet)
- Check for errors in `~/.purple/pack_errors.log`

**Forgot parent password**
```bash
# Delete password file
rm ~/.purple/parent.json
# Next parent mode access will prompt for new password
```

**Access denied with correct password**
- Check caps lock
- Verify you're using current password
- Reset password if needed

### Pack Issues

**Pack won't install**
- Check `manifest.json` is valid JSON
- Verify `id` has no spaces or special characters
- Ensure `version` follows x.y.z format
- Check `type` is valid (emoji, definitions, mode, sounds, mixed)

**Emoji don't appear**
- Verify `emoji.json` is valid JSON
- Check variable names are valid Python identifiers
- Restart Purple Computer
- Check `~/.purple/pack_errors.log`

**Pack errors log location**
```bash
cat ~/.purple/pack_errors.log
```

### Audio Issues

**No speech output**
```bash
# Check audio devices
aplay -l

# Test espeak
espeak "test"

# Check volume
alsamixer
```

### Network Issues

**Can't connect to internet**
- Network disabled by default (by design)
- Enable via parent mode → option 7
- Or use `nmtui` from shell

**Updates fail**
- Check internet connection
- Verify feed URL is accessible
- Check firewall isn't blocking HTTPS

### Development Issues

**Local runner fails**
```bash
# Verify installation
./scripts/verify_install.sh

# Check dependencies
pip3 list | grep -E "ipython|colorama|termcolor|packaging"

# Clean and retry
make clean
make setup
```

**Docker build fails**
```bash
# Clean Docker cache
docker system prune -a

# Rebuild from scratch
docker build --no-cache -t purplecomputer:latest .
```

**Scripts not executable**
```bash
chmod +x scripts/*.sh
```

### Recovery

**Reset everything**
```bash
# Local testing
make clean-all
./scripts/setup_dev.sh

# Real install
rm -rf ~/.purple/
sudo ./autoinstall/files/setup.sh
sudo reboot
```

**Boot into recovery**
1. Boot from USB again
2. Choose "Rescue mode"
3. Mount existing installation
4. Fix configuration

### Getting Help

- Check this manual
- Check `~/.purple/pack_errors.log` for errors
- File issues on GitHub
- Review autoinstall logs: `/var/log/installer/`

---

Made with 💜 for curious little minds
