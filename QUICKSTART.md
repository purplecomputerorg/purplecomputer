# Purple Computer Quick Start

## For Developers - Testing Locally

### First Time Setup

```bash
# 1. Clone and setup
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
./scripts/setup_dev.sh

# 2. Run Purple Computer
./scripts/run_local.sh

# 3. Play around!
# Try typing:
cat + dog + heart
2 + 2
rainbow

# 4. Test parent mode
# Press Ctrl+C
# Create a parent password
# Explore the menu
```

### Testing Options

**Quick & Easy (Mac/Linux):**
```bash
./scripts/run_local.sh
```

**Full Simulation (Docker):**
```bash
./scripts/run_docker.sh
```

**Production Install:**
- See [docs/autoinstall.md](docs/autoinstall.md)

## For Parents - Installing on Hardware

### Option 1: USB Install (Recommended)

1. Download purple-computer.iso (or build it - see docs)
2. Write to USB drive:
   - **Mac:** Use [balenaEtcher](https://www.balena.io/etcher/)
   - **Windows:** Use [Rufus](https://rufus.ie/)
   - **Linux:** `sudo dd if=purple-computer.iso of=/dev/sdX bs=4M`
3. Boot computer from USB
4. Walk away - installation is automatic (10-15 minutes)
5. Remove USB when prompted, system reboots into Purple Computer
6. First time parent mode access: create your parent password

### Option 2: Manual Install

On an existing Ubuntu 22.04 system:

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
sudo ./autoinstall/files/setup.sh
sudo reboot
```

## Using Purple Computer

### For Kids

Just type! Try:

```python
cat * 10           # Ten cats!
dog + cat + bird   # Animal friends
2 + 2              # Math
"hello" * 3        # Word patterns
```

### For Parents

**Access Parent Mode:**
- Press Ctrl+C (or Ctrl+Alt+P if configured)
- Enter your parent password
- Choose from menu:
  1. Return to kid mode
  2. Check for updates
  3. Install packs
  4. List packs
  5. Change password
  6. System shell (advanced)
  7. Network settings
  8. Shutdown
  9. Restart

**First Time:**
- You'll create a parent password
- Write it down somewhere safe!
- Kids won't see this password

## Quick Commands

### Development

```bash
# Setup environment
./scripts/setup_dev.sh

# Run locally
./scripts/run_local.sh

# Run in Docker
./scripts/run_docker.sh

# Build a pack
./scripts/build_pack.py packs/my-pack packs/my-pack.purplepack

# Clean test environment
rm -rf .test_home/
```

### Pack Creation

```bash
# 1. Create pack structure
mkdir -p my-pack/content
cat > my-pack/manifest.json <<EOF
{
  "id": "my-pack",
  "name": "My Pack",
  "version": "1.0.0",
  "type": "emoji"
}
EOF

# 2. Add content
cat > my-pack/content/emoji.json <<EOF
{
  "unicorn": "🦄",
  "dragon": "🐉"
}
EOF

# 3. Build pack
./scripts/build_pack.py my-pack my-pack.purplepack

# 4. Test it
./scripts/run_local.sh
# Press Ctrl+C → option 3 → enter path to my-pack.purplepack
```

## Documentation

- **[README.md](README.md)** - Project overview
- **[docs/testing.md](docs/testing.md)** - Testing guide (you are here!)
- **[docs/packs.md](docs/packs.md)** - Creating packs
- **[docs/parent-mode.md](docs/parent-mode.md)** - Parent mode guide
- **[docs/updates.md](docs/updates.md)** - Update system
- **[docs/architecture.md](docs/architecture.md)** - Technical architecture

## Common Issues

**"Module not found"**
```bash
pip3 install ipython colorama termcolor packaging
```

**Docker won't start**
- Make sure Docker Desktop is running
- Try: `docker info`

**Can't access parent mode**
- Press Ctrl+C (not Ctrl+Alt+P - that's not implemented yet)

**Parent password forgotten**
```bash
# Local mode
rm .test_home/.purple/parent.json

# Docker mode
docker volume rm purplecomputer_purple-config

# Real install
rm ~/.purple/parent.json
```

## Getting Help

- **Issues:** File on GitHub
- **Docs:** Check the docs/ folder
- **Community:** (coming soon!)

---

Made with 💜 for curious little minds
