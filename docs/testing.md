# Testing Purple Computer

Guide to running and testing Purple Computer locally without installing on physical hardware.

## Quick Start

### 1. One-Time Setup

```bash
# Clone the repo
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer

# Run setup
./scripts/setup_dev.sh
```

This installs Python dependencies and builds example packs.

### 2. Choose Your Testing Mode

**Option A: Lightweight (Mac/Linux)**
```bash
./scripts/run_local.sh
```

**Option B: Full Simulation (Docker)**
```bash
./scripts/run_docker.sh
```

## Testing Modes

### Mode 1: Local Runner (Lightweight)

**What it is:**
- Runs Purple Computer REPL directly on your Mac or Linux machine
- Uses your system Python
- Creates temporary test environment in `.test_home/`
- Fastest way to test code changes

**What works:**
- ✅ Purple REPL and IPython environment
- ✅ Emoji variables from packs
- ✅ Pack installation and management
- ✅ Parent mode and password authentication
- ✅ Update manager (with network)
- ✅ All Python-based functionality

**What doesn't work:**
- ❌ X11/Kitty terminal (uses your terminal instead)
- ❌ Auto-login on boot (manual start)
- ❌ System-level integration
- ❌ Text-to-speech (unless installed separately)

**Best for:**
- Quick iteration on REPL code
- Testing pack system
- Testing parent mode
- Developing new modes
- Debugging Python code

**Usage:**
```bash
# Basic run
./scripts/run_local.sh

# Inside Purple Computer:
cat + dog          # Test emoji
2 + 2              # Test Python
^C                 # Access parent mode (Ctrl+C)
exit()             # Quit
```

**File locations:**
- Test home: `.test_home/`
- Packs: `.test_home/.purple/packs/`
- Parent password: `.test_home/.purple/parent.json`

**Clean up:**
```bash
rm -rf .test_home/
```

### Mode 2: Docker (Full Simulation)

**What it is:**
- Runs Purple Computer in Ubuntu 22.04 container
- Matches production environment closely
- Simulates real user account setup
- Uses Docker for isolation

**What works:**
- ✅ Everything from Local Mode
- ✅ Ubuntu 22.04 environment
- ✅ `purple` user with locked password
- ✅ Persistent pack storage
- ✅ Persistent parent password
- ✅ Closer to production environment

**What doesn't work:**
- ❌ X11/GUI (container runs headless)
- ❌ Auto-login on boot
- ❌ Kitty terminal
- ❌ Audio/TTS

**Best for:**
- Testing environment-specific issues
- Verifying Ubuntu compatibility
- Testing user account setup
- Testing network isolation
- Integration testing

**Usage:**
```bash
# First run (builds image)
./scripts/run_docker.sh

# Force rebuild
./scripts/run_docker.sh --build

# Debug shell
./scripts/run_docker.sh --shell

# Using docker-compose
docker-compose up
docker-compose down
```

**Persistence:**
- Installed packs persist across runs
- Parent password persists
- Code changes mount live (read-only)

**Clean up:**
```bash
# Remove container
docker rm -f purple-computer-test

# Remove image
docker rmi purplecomputer:latest

# Remove volumes (deletes packs/password)
docker volume rm purplecomputer_purple-data purplecomputer_purple-config
```

### Mode 3: Full Hardware Install (Production)

**What it is:**
- Install Purple Computer on physical hardware
- Boot from ISO or run setup.sh on existing Ubuntu
- Real production environment

**What works:**
- ✅ Everything
- ✅ X11 + Kitty terminal
- ✅ Auto-login on boot
- ✅ Full screen purple interface
- ✅ Text-to-speech
- ✅ All system integration

**Best for:**
- Final testing before release
- User experience testing
- Performance testing
- Hardware compatibility testing

**Usage:**
See [autoinstall.md](autoinstall.md) for ISO building and installation.

## Feature Comparison

| Feature | Local | Docker | Hardware |
|---------|-------|--------|----------|
| REPL | ✅ | ✅ | ✅ |
| Emoji | ✅ | ✅ | ✅ |
| Packs | ✅ | ✅ | ✅ |
| Parent Mode | ✅ | ✅ | ✅ |
| Updates | ✅ | ✅ | ✅ |
| Ubuntu 22.04 | ❌ | ✅ | ✅ |
| User Accounts | ❌ | ✅ | ✅ |
| X11/Kitty | ❌ | ❌ | ✅ |
| Auto-login | ❌ | ❌ | ✅ |
| TTS | ⚠️ | ❌ | ✅ |
| Full Screen | ❌ | ❌ | ✅ |
| Boot to Purple | ❌ | ❌ | ✅ |

⚠️ = Requires separate installation

## Testing Workflows

### Testing a Code Change

1. Edit code in `purple_repl/`
2. Run `./scripts/run_local.sh`
3. Test the change
4. Exit and iterate

Changes are loaded immediately (no rebuild needed).

### Testing a New Pack

1. Create pack source in `packs/my-pack/`
2. Build: `./scripts/build_pack.py packs/my-pack packs/my-pack.purplepack`
3. Run Purple Computer (local or Docker)
4. Enter parent mode (Ctrl+C)
5. Install pack (option 3)
6. Test the pack content

### Testing Parent Mode

1. Run Purple Computer
2. Press Ctrl+C
3. Create parent password on first run
4. Test menu options:
   - Install packs
   - Check for updates
   - Change password
5. Exit to kid mode (option 1)

### Testing Updates

1. Create a mock update feed JSON:
```bash
cat > /tmp/feed.json <<EOF
{
  "packs": [
    {
      "id": "test-pack",
      "name": "Test Pack",
      "version": "1.0.0",
      "url": "file:///path/to/test-pack.purplepack",
      "hash": "sha256:abc123..."
    }
  ]
}
EOF
```

2. Modify `update_manager.py` to use local feed
3. Test update checking and installation

### Testing Full Installation Flow

1. Build ISO: See [autoinstall.md](autoinstall.md)
2. Test in VM:
```bash
# Using QEMU
qemu-system-x86_64 \
  -cdrom purple-computer.iso \
  -m 2048 \
  -boot d \
  -drive file=test-disk.img,format=raw
```

3. Or test on physical hardware

## Debugging

### Enable Debug Logging

```bash
# In run_local.sh or run_docker.sh, add:
export PURPLE_DEBUG=1

# In repl.py, add:
import os
if os.getenv('PURPLE_DEBUG'):
    import logging
    logging.basicConfig(level=logging.DEBUG)
```

### Check Pack Errors

```bash
# Local mode
cat .test_home/.purple/pack_errors.log

# Docker mode
docker exec -it purple-computer-test cat /home/purple/.purple/pack_errors.log
```

### Inspect Installed Packs

```python
# In Purple Computer REPL
from pack_manager import get_registry

registry = get_registry()
print(registry.list_packs())
print(registry.get_all_emoji())
```

### Test Parent Password

```python
# In Purple Computer REPL (outside parent mode)
from parent_auth import get_auth

auth = get_auth()
print(f"Has password: {auth.has_password()}")
print(f"First run: {auth.is_first_run()}")

# Reset password for testing
auth.reset_password()
```

### Interactive Python Testing

```bash
# Run Python with REPL environment
cd purple_repl
python3 -i repl.py

# Or use IPython directly
export HOME=/path/to/test_home
export IPYTHONDIR=$HOME/.ipython
ipython
```

## Automated Testing (Future)

```bash
# Unit tests (coming soon)
python3 -m pytest tests/

# Integration tests
python3 -m pytest tests/integration/

# Pack validation
./scripts/validate_pack.py packs/my-pack.purplepack
```

## Common Issues

### "Module not found" errors

```bash
# Install dependencies
pip3 install ipython colorama termcolor packaging
```

### Parent mode doesn't activate

- Make sure you press Ctrl+C
- Check for errors in pack_errors.log
- Verify parent_auth.py is in the purple_repl directory

### Packs don't load

```bash
# Check pack format
tar -tzf packs/my-pack.purplepack

# Validate manifest
python3 -c "
import json
import tarfile
tar = tarfile.open('packs/my-pack.purplepack')
manifest = json.load(tar.extractfile('manifest.json'))
print(manifest)
"
```

### Docker build fails

```bash
# Clean Docker cache
docker system prune -a

# Rebuild from scratch
docker build --no-cache -t purplecomputer:latest .
```

## Tips

### Fast Iteration

For fastest development:
1. Use `./scripts/run_local.sh`
2. Keep the REPL running
3. Edit code in another terminal
4. Restart REPL to test changes

### Test on Multiple Platforms

```bash
# Mac
./scripts/run_local.sh

# Linux (Docker on Mac)
./scripts/run_docker.sh

# Real Linux
ssh to linux machine
./scripts/run_local.sh

# Production
Build ISO and test on VM/hardware
```

### Share Test Environment

```bash
# Export Docker image
docker save purplecomputer:latest | gzip > purplecomputer-docker.tar.gz

# Import on another machine
gunzip -c purplecomputer-docker.tar.gz | docker load
./scripts/run_docker.sh
```

## Next Steps

After testing locally:

1. **Test on Linux VM** - Closer to production
2. **Build ISO** - See [autoinstall.md](autoinstall.md)
3. **Test in QEMU** - Virtual hardware test
4. **Install on real hardware** - Final test
5. **Let kids use it!** - Real user testing

---

Happy testing! 💜🧪
