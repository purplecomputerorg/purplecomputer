# Purple Computer

**The calm computer for kids.**

Purple isn't a screen your kid stares at. Purple is a calm place your kid *does* things.

> **SOURCE-AVAILABLE LICENSE**
> You may view and run this code for personal use only.
> Forking, modifications, redistribution, and commercial use are prohibited without written permission.
> See [LICENSE](LICENSE) for details.

---

## What Is Purple?

Purple Computer turns old laptops into calm, creative tools for kids ages 3-8.

- **Distraction-free by design.** No videos. No ads. No app store. No infinite feeds.
- **A creativity device, not an entertainment device.** Kids write, draw, explore, type, imagine — slowly and calmly.
- **Safe by default.** No accounts. No tracking. No social media. No algorithm.
- **Eco-friendly & kid-ready.** Every Purple Laptop saves a device from the landfill.

**Tech for screen-skeptical parents.** Screen time that feels like quiet time.

---

## Quick Start

### For Development (Mac/Linux)

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
make setup    # Creates venv, installs deps, downloads TTS voice, installs fonts
make run      # Launches in Alacritty with Purple theme (or current terminal)
```

Inside Purple Computer, try:
```
2 + 2              # Math
cat * 5            # Five cats
dog + cat          # Emoji addition
what is elephant   # Definition lookup
```

### For Installation (Old Laptop)

**Build and test installer:**
```bash
cd build-scripts

# Build everything (30-90 min first time, 10-20 min after)
./build-in-docker.sh

# Validate build (checks configs, verifies artifacts)
./validate-build.sh

# Test boot in QEMU (detects kernel panics, shows what failed)
sudo ./test-boot.sh

# Result: /opt/purple-installer/output/purple-installer-YYYYMMDD.iso
```

**Install to hardware:**
1. Write ISO to USB with [balenaEtcher](https://www.balena.io/etcher/) or `dd`
2. Boot laptop from USB
3. Installation runs automatically (10-20 minutes)
4. System reboots into Purple Computer

**Default credentials:** `purple` / `purple` (change immediately!)

See [MANUAL.md](MANUAL.md) for complete build/customization details.

---

## The Four Modes

Purple has four core modes. Hold a number key to switch:

| Hold | Mode | What It Does |
|------|------|--------------|
| **1** | **Ask** | Math and emoji. Type `2 + 2` or `cat * 3` or `what is elephant` |
| **2** | **Play** | Music and art grid. Letters make notes and colors. Numbers make sounds. |
| **3** | **Listen** | Stories and songs. (Coming soon) |
| **4** | **Write** | Simple text editor. Just type. |

**Controls:**
- **Hold 1-4** — Switch modes
- **Hold 0** — Toggle dark/light mode
- **Ctrl+V** — Cycle views (Screen → Line → Ears)
- **Tab** (in Ask mode) — Toggle speech on/off

---

## Architecture

```
purplecomputer/
├── purple_tui/           # Main Textual TUI application
│   ├── modes/            # Ask, Play, Write, Listen modes
│   ├── content.py        # Content API for packs
│   └── tts.py            # Piper TTS integration
│
├── packs/                # Built-in content (emoji, definitions, sounds)
│
├── build-scripts/        # Module-free ISO build pipeline
│   ├── 00-build-custom-kernel.sh    # Custom kernel with built-in drivers
│   ├── 01-build-golden-image.sh     # Ubuntu base system image
│   ├── 02-build-initramfs.sh        # Minimal initramfs (no modules)
│   ├── 03-build-installer-rootfs.sh # Installer environment
│   ├── 04-build-iso.sh              # USB-bootable hybrid ISO
│   ├── build-all.sh                 # Orchestrate all build steps
│   ├── build-in-docker.sh           # Docker wrapper (NixOS-friendly)
│   ├── validate-build.sh            # Pre-build validation (configs, deps)
│   ├── test-boot.sh                 # QEMU boot testing (detects panics)
│   ├── kernel-config-fragment.config # Kernel driver configuration
│   └── install.sh                   # Installation script (runs on target)
│
└── guides/               # Technical references
    └── module-free-architecture.md
```

**Stack:**
- **Target System:** Ubuntu 24.04 LTS minimal + X11 + Alacritty + Textual TUI
- **Installer:** Module-free custom kernel + minimal initramfs + direct disk imaging
- **Application:** Python + Textual + Piper TTS + Pygame

**How Installation Works:**

The installer does **not** contain an offline apt repository or Ubuntu ISO. Instead, it writes a fully pre-built Ubuntu Noble disk image directly to the internal drive. This eliminates package installation complexity and ensures deterministic, reliable installations.

After installation, the system boots into standard Ubuntu 24.04 LTS and uses Ubuntu's normal apt servers for updates.

**Module-Free Architecture:**
- Custom Linux kernel (6.8.12) with all essential drivers built-in (USB, SATA, NVMe, ext4, vfat)
- No runtime kernel module loading (eliminates insmod, .ko files, ABI mismatches)
- Direct USB boot (no CD-ROM/ISO9660 dependency)
- Improved hardware compatibility across diverse laptops (2010+)

---

## System Requirements

**Target Hardware:**
- x86_64 processor (Intel/AMD)
- 2GB RAM minimum (4GB+ recommended)
- 20GB storage minimum (60GB+ recommended)
- BIOS or UEFI firmware

**Tested on:** 2010-2015 era laptops (ThinkPad, Dell Latitude, MacBook Air/Pro)

**Build Machine:**
- Any system with Docker (NixOS, Ubuntu, macOS, etc.)
- 20GB free disk space
- Docker daemon running
- Internet connection (for package download only)

---

## Documentation

See [MANUAL.md](MANUAL.md) for complete build instructions, customization, and troubleshooting.

Technical guides are in [guides/](guides/).

---

## Philosophy

**A computer kids can't break, and parents don't have to fight with.**

- Simple, text-based interface — easy for kids, calming for parents
- Your kid's first computer that isn't trying to control their attention
- A tool, not a toy — built from sturdy laptops made to survive real kid use
- Offline & private — no internet required, no tracking, no data collection

---

## License

Purple Computer Source-Available License 1.0 — see [LICENSE](LICENSE)

**You may:**
- View the source code
- Run for personal, private use

**You may NOT (without written permission):**
- Fork, modify, or create derivatives
- Redistribute or republish
- Use commercially

---

💜
