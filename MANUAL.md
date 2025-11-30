# Purple Computer Manual

Complete reference for developing, testing, installing, and using Purple Computer.

> **⚠️ SOURCE-AVAILABLE LICENSE**
> This is **NOT open source**. Code is viewable for transparency/learning only.
> **DO NOT FORK.** Modifications and redistribution require written permission.
> See [LICENSE](LICENSE) and [CONTRIBUTING.md](CONTRIBUTING.md) for details.

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

**Note:** This section is reference material for viewing and personal testing only. Development, modification, and contribution require written permission from Purple Computer. See [CONTRIBUTING.md](CONTRIBUTING.md).

### Quick Setup

```bash
# One-time setup (creates .venv and installs dependencies)
make setup

# Run locally (Mac/Linux) - auto-activates venv
make run

# Run in Docker (full Ubuntu simulation) - no venv needed
make run-docker
```

**Virtual Environment:** Purple Computer uses a Python venv (`.venv/`) to avoid conflicts with system packages. The scripts automatically activate it. This is standard Python practice and works on both Mac and Linux.

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

**VM Runner** (Reproducible Testing)
- Full Ubuntu 22.04 with X11/Kitty
- Repo mounted from host (instant sync)
- Reset script for fresh user state
- Perfect for UI/UX testing
- Run: See VM Testing section below

### Feature Comparison

| Feature | Local | Docker | VM | Hardware |
|---------|-------|--------|-----|----------|
| REPL | ✅ | ✅ | ✅ | ✅ |
| Packs | ✅ | ✅ | ✅ | ✅ |
| Parent Mode | ✅ | ✅ | ✅ | ✅ |
| Ubuntu 22.04 | ❌ | ✅ | ✅ | ✅ |
| X11/Kitty | ❌ | ❌ | ✅ | ✅ |
| Auto-login | ❌ | ❌ | ❌ | ✅ |
| Fresh state | ✅ | ✅ | ✅ | ❌ |
| Code sync | Instant | Instant | Instant | Manual |

### Development Workflow

1. Edit code in `purple_repl/`
2. Run `make run` to test (venv auto-activates)
3. Iterate
4. Test in Docker before hardware deployment

**Manual venv activation** (optional):
```bash
source .venv/bin/activate  # Activate venv
deactivate                  # Deactivate when done
```

### Available Scripts

```bash
make setup          # Install dependencies
make run            # Run locally
make run-docker     # Run in Docker
make build-packs    # Build example packs
make clean          # Clean test environment
```

### VM Testing (Reproducible Environment)

For testing Purple Computer with full UI (Kitty + X11) in a reproducible environment where you can reset to a fresh user state.

#### Why Use a VM?

- **Full UI Testing**: Test Kitty terminal, fonts, emoji rendering
- **Fresh State**: Reset to clean user environment with one script
- **Host Editing**: Code lives on host, instantly visible in VM
- **Reproducible**: Snapshot and restore VM instantly
- **Realistic**: Closest to production without dedicated hardware

#### Quick Setup (30 minutes one-time)

**1. Install VM Software**

macOS (recommended):
```bash
brew install --cask utm
```

Linux (recommended):
```bash
sudo apt install virtualbox virtualbox-guest-utils
```

**2. Create Ubuntu 22.04 VM**

- Download Ubuntu 22.04 Desktop ISO
- Create VM: 4GB RAM, 2 CPU cores, 20GB disk
- Install Ubuntu (username: `purple`, password: `purple`)

**3. Configure Shared Folder**

UTM (macOS):
- VM Settings → Sharing → Add directory
- Name: `purple`, Path: `/path/to/purplecomputer`

VirtualBox (Linux):
- VM Settings → Shared Folders → Add
- Name: `purple`, Path: `/path/to/purplecomputer`, Auto-mount: ✅

**4. Mount Shared Folder in VM**

UTM:
```bash
sudo apt update
sudo apt install -y spice-vdagent spice-webdavd
sudo mkdir -p /mnt/purple
echo "purple /mnt/purple 9p trans=virtio,version=9p2000.L,rw,_netdev,nofail 0 0" | sudo tee -a /etc/fstab
sudo mount -a
ls /mnt/purple  # Verify
```

VirtualBox:
```bash
sudo apt install -y virtualbox-guest-utils virtualbox-guest-dkms
sudo usermod -aG vboxsf $USER
sudo reboot
# After reboot: ls /media/sf_purple
```

**5. Install VM Dependencies**

```bash
# Install Kitty and fonts
sudo apt install -y kitty fonts-noto-color-emoji fonts-dejavu python3 python3-pip python3-venv git

# Configure Kitty
mkdir -p ~/.config/kitty
cp /mnt/purple/scripts/kitty-purple.conf ~/.config/kitty/kitty.conf

# Copy reset script
cp /mnt/purple/scripts/reset-purple-vm.sh ~/reset-purple.sh
chmod +x ~/reset-purple.sh
```

**6. Create Snapshot**

- **UTM**: Right-click VM → Take Snapshot → "Clean State"
- **VirtualBox**: VM → Machine → Take Snapshot → "Clean State"

#### Daily Workflow

Edit code on host:
```bash
cd /path/to/purplecomputer
git pull
# Changes instantly visible in VM at /mnt/purple
```

Test in VM:
```bash
~/reset-purple.sh
```

The reset script:
1. Wipes `~/.purple` and `~/.ipython` (fresh state)
2. Copies latest code from `/mnt/purple`
3. Creates fresh Python venv
4. Installs dependencies and packs
5. Launches Purple Computer in Kitty

#### Troubleshooting VM Setup

**Shared folder not mounting:**
```bash
# UTM: Check spice services
ps aux | grep spice
sudo systemctl restart spice-vdagentd

# VirtualBox: Check group membership
groups | grep vboxsf
sudo usermod -aG vboxsf $USER && sudo reboot
```

**Emoji not displaying:**
```bash
sudo apt install --reinstall fonts-noto-color-emoji
fc-cache -fv
```

---

## Pack System

### What Are Packs?

Packs are modular content bundles (`.purplepack` files) that extend Purple Computer. All extensions—including core modes like Music Mode—use the pack format.

Pack types:
- **emoji** - Variable name → emoji mappings
- **definitions** - Word → definition mappings
- **mode** - Interactive modes (keyboard instruments, drawing, games)
- **sound** - Audio files for sound effects
- **effect** - Visual effects and animations
- **mixed** - Combination of above

### Philosophy

Purple Computer's pack system follows these principles:
- **First-class extensions** - Even core modes are packs
- **No passive media** - No videos, no images for passive consumption
- **Interactive and creative** - Modes encourage active participation
- **Child-friendly** - Simple, safe, and age-appropriate
- **Offline-first** - Everything works without internet

### Pack Structure

```
mypack.purplepack (tar.gz archive)
├── manifest.json
└── data/                    # Preferred (content/ also supported)
    ├── emoji.json          # For emoji packs
    ├── definitions.json    # For definition packs
    ├── *.py                # Python modules for mode packs
    └── sounds/*.wav        # Audio files for sound packs
```

**Note:** Both `data/` (preferred) and `content/` (legacy) directories are supported.

### Creating a Pack

**Example: Emoji Pack**
```bash
mkdir -p mypack/data

cat > mypack/manifest.json <<EOF
{
  "id": "mypack",
  "name": "My Pack",
  "version": "1.0.0",
  "type": "emoji",
  "description": "My custom emoji pack"
}
EOF

cat > mypack/data/emoji.json <<EOF
{
  "unicorn": "🦄",
  "dragon": "🐉"
}
EOF

# Build the pack
./scripts/build_pack.py mypack mypack.purplepack
```

**Example: Mode Pack**
```bash
mkdir -p mymode/data

cat > mymode/manifest.json <<EOF
{
  "id": "my-mode",
  "name": "My Mode",
  "version": "1.0.0",
  "type": "mode",
  "entrypoint": "data/mymode.py",
  "description": "A custom interactive mode"
}
EOF

cat > mymode/data/mymode.py <<'PYEOF'
def activate():
    print("✨ My Mode activated!")
    # Your mode logic here
    input("Press Enter to exit...")
    return ""
PYEOF

# Build the pack
./scripts/build_pack.py mymode mymode.purplepack
```

**Installing a Pack:**
1. Run Purple Computer
2. Press Ctrl+C (parent mode)
3. Option 3: Install packs
4. Enter path to `mypack.purplepack`

### Manifest Format

**Required fields:**
```json
{
  "id": "unique-id",           // lowercase, hyphens only
  "name": "Display Name",
  "version": "1.0.0",          // semantic versioning (x.y.z)
  "type": "emoji"              // emoji|definitions|mode|sound|effect|mixed
}
```

**Optional fields:**
- `description` - Brief description of the pack
- `author` - Creator name
- `url` - Homepage or repository URL
- `license` - License identifier (e.g., "MIT", "CC0")
- `entrypoint` - **Required for mode packs** - Path to Python module (e.g., "data/mymode.py")

### Pack Types

**Emoji Pack** (`data/emoji.json`):
```json
{
  "cat": "🐱",
  "dog": "🐶",
  "star": "⭐"
}
```

**Definitions Pack** (`data/definitions.json`):
```json
{
  "computer": "A machine that follows instructions",
  "code": "Instructions written for computers"
}
```

**Mode Pack** (`data/*.py`):
Mode packs provide interactive experiences that can be activated from the Purple Computer prompt.

Requirements:
- Must specify `entrypoint` in manifest pointing to the Python module
- Module must have either:
  - An `activate()` function that runs the mode, OR
  - A `mode` attribute/function that can be called

Example structure:
```python
def activate():
    """Main entry point for the mode"""
    print("🎨 Mode activated!")
    # Your interactive logic here
    # Can use raw keyboard input, graphics, sound, etc.
    return ""  # Return empty string for clean IPython output
```

Modes can:
- Take over the terminal for raw keyboard input
- Play sounds and music
- Display interactive visuals
- Run games and creative tools
- Return control to Purple Computer when done

**Sound Pack** (`data/sounds/`):
- Supported formats: `.wav`, `.ogg`, `.mp3`
- Each file becomes accessible by name
- Used for sound effects, music snippets, etc.

### Pack Security

Packs are validated before installation:
- ✅ Manifest format checked
- ✅ Path traversal prevented
- ✅ Hash verification (if provided)
- ⚠️ Never install packs from untrusted sources

### Example Packs

Purple Computer includes these packs:

**Content Packs:**
- **core-emoji** - 100+ emoji (animals, nature, food, symbols)
- **education-basics** - CS definitions for kids

**Core Mode Packs:**
- **music-mode-basic** - Keyboard piano mode where each letter key plays a musical note

All example packs are in the `packs/` directory.

### Music Mode

Music Mode is a core pack that demonstrates how modes work. It's an official mode that happens to be implemented as a pack.

**Activating Music Mode:**
```python
💜 music_basic
```

(Note: The mode name is derived from the pack ID by converting to snake_case and removing redundant suffixes.)

**Features:**
- Each letter key (a-z) plays a different musical note
- Real-time sound generation
- Simple visual keyboard display
- Press ESC to exit back to Purple Computer

**How it works:**
- Takes over the terminal for raw keyboard input
- Generates sine wave tones programmatically
- Plays sounds with minimal latency
- Returns control to IPython when you exit

This demonstrates the pack system's extensibility—future modes for drawing, games, and creative tools will follow the same pattern.

### Updating Packs

Packs can be updated through the update system (Parent Mode → Check for updates) or by reinstalling a newer version manually.

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
- **Ubuntu Server 22.04 LTS** (no desktop environment, no GUI)
- **Minimal Xorg** (X11 server only, no window manager, no desktop bloat)
- **Kitty terminal** (launches fullscreen)
- Python 3 + IPython

**User:**
- `purple` user (no password, auto-login)
- `kiduser` user (legacy support)

**Purple Computer:**
- REPL in `~/.purple/`
- Packs in `~/.purple/packs/`
- Parent config in `~/.purple/parent.json`

**Architecture:** Ubuntu Server + minimal Xorg + kitty fullscreen. No GNOME, no KDE, no window manager, no GUI applications.

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

### System Stack

**No GUI. No Desktop Environment. No Window Manager.**

Purple Computer uses a minimal stack:
- **Ubuntu Server 22.04** - Base OS (no desktop packages)
- **Minimal Xorg** - X11 server only (xorg, xinit, xserver-xorg-video-all)
- **Kitty** - Terminal emulator (fullscreen mode)
- **IPython** - Python REPL with Purple extensions

The system boots directly from console to fullscreen terminal. No GNOME, no KDE, no window decorations, no GUI applications.

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

**Boot Sequence (Ubuntu Server → Xorg → Kitty fullscreen):**

1. **GRUB** → boots Ubuntu Server (1 second timeout)
2. **getty@tty1** → auto-login as `purple` user (no password)
3. **`.bash_profile`** → runs `startx` (launches X11)
4. **Xorg** → starts minimal X server (no window manager)
5. **`.xinitrc`** → launches kitty fullscreen with purple background
6. **Kitty** → runs `python3 ~/.purple/repl.py`
7. **repl.py**:
   - Create PackRegistry
   - Create PackManager
   - Load all packs
   - Install parent escape handler
   - Start IPython
8. **IPython** runs startup scripts:
   - Load emoji from registry
   - Load modes
9. **Kid sees:** 💜 prompt

Total boot time: < 5 seconds from power-on to REPL

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

**X11 fails to start / .Xauthority errors**
This is usually caused by incorrect ownership of `/home/purple`. The first-boot script should fix this automatically, but if you need to debug:

```bash
# Check ownership (should be purple:purple, not root:root)
ls -la / | grep home
ls -la /home/

# The purple user has NO password and can't use sudo (correct for security)
# To manually fix during testing, enable root access temporarily:
```

For testing VMs only - add this to `late-commands` in `autoinstall.yaml`:
```yaml
- echo 'root:test123' | chroot /target chpasswd
```

Then you can login as root to test fixes. Remove before production.

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

**"externally-managed-environment" error on Mac**
```bash
# This happens on newer Homebrew Python installations
# Solution: Use venv (already set up by make setup)
make setup  # Creates .venv and installs dependencies

# The scripts auto-activate venv:
make run    # Automatically uses .venv/bin/activate
```

**Local runner fails**
```bash
# Verify installation (checks venv)
./scripts/verify_install.sh

# Check dependencies (venv will auto-activate)
source .venv/bin/activate
pip list | grep -E "ipython|colorama|termcolor|packaging"

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
