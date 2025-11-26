# Purple Computer 💜

A kid-friendly computing environment for ages 3-8. Boot directly into a fullscreen terminal with emoji, colors, and creative exploration.

## What Is This?

Purple Computer is a real computer for young kids. They type on a keyboard, run commands, and see what happens. It teaches:
- Typing and keyboard use
- Text-based interaction
- Creative exploration with code
- How computers follow instructions

No desktop. No apps. Just a purple terminal where they explore and create.

It's offline, private, and runs on old hardware.

---

## Quick Start

### For Testing (Developers)

```bash
# One-time setup (creates .venv and installs dependencies)
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
make setup

# Run Purple Computer locally (auto-activates venv)
make run
```

**Note:** Uses Python virtual environment (`.venv/`) - standard practice that avoids system package conflicts.

Inside Purple Computer, try:
```python
cat + dog + heart    # 🐱🐶❤️
2 + 2                # 4
star * 10            # ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐
```

Type `parent` at the prompt to access parent mode (first time: create a parent password).

### For Installing (Parents)

**Option 1: USB Install** (Recommended)
1. Download `purple-computer.iso` or build it (see [MANUAL.md](MANUAL.md#installation))
2. Write to USB with [balenaEtcher](https://www.balena.io/etcher/)
3. Boot from USB - installation is automatic (10-15 min)
4. Remove USB when done, system reboots into Purple Computer

**Option 2: Manual Install** (Existing Ubuntu 22.04)
```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
sudo ./autoinstall/files/setup.sh
sudo reboot
```

---

## Using Purple Computer

### For Kids

Just type! Try these:

```python
cat * 5              # Five cats
dog + cat            # Dog and cat
rainbow              # If defined in a pack
2 + 2                # Math works too
"hello" * 3          # Repeat words
```

Kids can:
- Type words and see emoji
- Do simple math
- Create patterns
- Explore Python interactively

### For Parents

Access **Parent Mode** by typing `parent` at the 💜 prompt.

First time: You'll create a parent password (write it down!).

Parent menu options:
1. Return to kid mode
2. Check for updates
3. Install packs (add emoji, educational content)
4. List installed packs
5. Change parent password
6. System shell (advanced)
7. Network settings
8. Shut down
9. Restart

**Important:** The `purple` user has NO system password - it auto-logs in. The parent password is separate and protects parent mode only.

---

## Features

### For Kids
- **Instant Boot** - Powers on straight into kid-friendly interface
- **Emoji Variables** - `cat`, `dog`, `star`, `heart` become emoji
- **Creative Modes** - Switch between different interactive modes
- **Big Letter Mode** - Auto-activates with Caps Lock for beginning readers
- **Safe** - Kids can't break out or damage the system

### For Parents
- **Password-Protected Parent Mode** - No kids in settings
- **Pack System** - Install emoji packs, educational content, modes
- **Update Manager** - One-click updates
- **No System Password** - Instant auto-login for kids
- **Offline First** - Works completely offline

---

## Creating Packs

Packs are `.purplepack` files containing emoji, definitions, or modes.

**Quick Example:**
```bash
# 1. Create pack
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

# 2. Build it
./scripts/build_pack.py mypack mypack.purplepack

# 3. Install it
# Run Purple Computer → Ctrl+C → option 3 → enter path to mypack.purplepack
```

See [MANUAL.md](MANUAL.md#pack-system) for complete pack documentation.

---

## Project Structure

```
purplecomputer/
├── README.md              # You are here
├── MANUAL.md              # Complete documentation
├── CHANGELOG.md           # Version history
├── Makefile               # Convenient shortcuts
│
├── purple_repl/           # The kid-friendly REPL
│   ├── repl.py            # Main entry point
│   ├── pack_manager.py    # Pack system
│   ├── parent_auth.py     # Parent authentication
│   ├── update_manager.py  # Update system
│   └── modes/             # Interaction modes
│
├── packs/                 # Example packs
│   ├── core-emoji.purplepack
│   └── education-basics.purplepack
│
├── scripts/               # Build and test utilities
│   ├── run_local.sh       # Run locally (fast)
│   ├── run_docker.sh      # Run in Docker (full sim)
│   ├── setup_dev.sh       # Setup dependencies
│   ├── build_pack.py      # Build packs
│   └── verify_install.sh  # Verify setup
│
├── autoinstall/           # Ubuntu installation configs
│   └── files/             # Setup scripts and configs
│
└── Dockerfile             # Docker testing environment
```

---

## Development

### Quick Commands

```bash
make setup          # Install dependencies and build packs
make run            # Run Purple Computer locally
make run-docker     # Run in Docker (Ubuntu simulation)
make build-packs    # Build example packs
make clean          # Clean test environment
```

### Testing Modes

**Local** (Fast - Mac/Linux)
- Direct Python on your machine
- Instant startup
- Perfect for quick iteration

**Docker** (Full - Linux container)
- Ubuntu 22.04 environment
- `purple` user simulation
- Near-production testing

**Hardware** (Production)
- Complete experience with X11, auto-login
- Build ISO and install on real machine

See [MANUAL.md](MANUAL.md#development--testing) for details.

---

## Documentation

- **[MANUAL.md](MANUAL.md)** - Complete reference (development, packs, parent mode, updates, installation, architecture, troubleshooting)
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and release notes

---

## System Requirements

- x86_64 processor (Intel or AMD)
- 2GB RAM minimum (4GB recommended)
- 8GB storage minimum (16GB recommended)
- USB port for installation

---

## Philosophy

Purple Computer is built on:
- **Safe to Explore** - No wrong answers, can't break things
- **Age Appropriate** - Designed for ages 3-8
- **Parent Friendly** - Non-technical adults can set it up
- **Offline & Private** - No internet, no tracking, no data collection

---

## Troubleshooting

**Can't run locally?**
```bash
./scripts/verify_install.sh  # Check what's missing
make setup                   # Install dependencies
```

**Parent mode won't open?**
- Type `parent` at the 💜 prompt (or press Ctrl+C as backup)

**Forgot parent password?**
```bash
rm ~/.purple/parent.json  # Reset it
```

**Need more help?**
- See [MANUAL.md](MANUAL.md#troubleshooting)
- File issues on GitHub

---

## License

MIT License - see [LICENSE](LICENSE)

---

Made with 💜 for curious little minds
