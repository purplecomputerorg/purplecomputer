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
- **A creativity device, not an entertainment device.** Kids write, draw, explore, type, imagine. Slowly and calmly.
- **Safe by default.** No accounts. No tracking. No social media. No algorithm.
- **Eco-friendly & kid-ready.** Every Purple Laptop saves a device from the landfill.

**Tech for screen-skeptical parents.** Screen time that feels like quiet time.

---

## Quick Start

### For Development (Linux only)

Purple Computer requires Linux with evdev for keyboard input. macOS is not supported. Use a Linux VM if developing on Mac (see `guides/linux-vm-dev-setup.md`).

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
make setup    # Creates venv, installs deps, downloads TTS voice, installs fonts
make run      # Launches in Alacritty with Purple theme
```

Inside Purple Computer, try:
```
2 + 2                  # Math with dot visualization
3 * 4 + 2              # Operator precedence (= 14)
cat * 5                # Five cats
dog + cat              # Emoji addition (🐶 🐱)
3 + 4 + 2 bananas      # Numbers attach to emoji (= 9 bananas)
red + blue             # Color mixing (= purple)
apple + red + green    # Mixed: emoji + colors
```

### For Installation (Old Laptop)

**Build and test installer:**
```bash
cd build-scripts

# Build everything (20-35 min first time, 15-25 min subsequent)
./build-in-docker.sh

# Validate build (checks configs, verifies artifacts)
./validate-build.sh

# Result: /opt/purple-installer/output/purple-installer-YYYYMMDD.iso
```

**Flash to USB:**
```bash
# List USB drives and find your drive's serial number
./build-scripts/flash-to-usb.sh --list

# Add your drive's serial to the whitelist (one-time setup)
echo 'YOUR_DRIVE_SERIAL' >> .flash-drives.conf

# Flash the latest ISO (with verification)
./build-scripts/flash-to-usb.sh
```

**Install to hardware:**
1. Boot laptop from USB (Secure Boot can remain enabled)
2. Installation runs automatically (10-20 minutes)
3. System reboots into Purple Computer

**Default credentials:** `purple` / `purple` (change immediately!)

See [MANUAL.md](MANUAL.md) for complete build/customization details.

---

## The Three Modes

Purple has three core modes:

| Key | Mode | What It Does |
|-----|------|--------------|
| **F1** | **Ask** | Math, emoji, and colors. Maximally permissive: always tries to do something meaningful. See [guides/ask-mode-design.md](guides/ask-mode-design.md) |
| **F2** | **Play** | Music and art grid. Press any key to play a sound and paint a color. |
| **F3** | **Write** | Simple text editor. Just type. |

**Controls:**
- **F1-F3:** Switch modes
- **F12:** Toggle dark/light mode
- **Ctrl+V:** Cycle views (Screen → Line → Ears)
- **Tab** (in Ask mode): Toggle speech on/off
- **Hold Escape (1s):** Parent mode (admin menu)

---

## Keyboard Features

Purple includes a hardware keyboard normalizer that makes typing easier for kids:

### Easy Capitals (No Shift Key Needed)
- **Double-tap any key** — Types the shifted version (`a` `a` → `A`, `1` `1` → `!`)
- **Tap Shift quickly** — Activates "sticky shift" for the next character
- **Hold Shift + type** — Normal shift behavior (uppercase while held)

Kids can type capital letters without holding two keys at once!

### Parent Mode
- **Hold Escape for 1 second** — Opens parent shell

### F-Key Setup

On first boot, Purple automatically runs keyboard setup. You'll be asked to press F1 through F12. This captures each key's scancode, making F-keys work regardless of the laptop's default behavior (some laptops send brightness/volume instead of F1-F12).

### How It Works

**Purple Computer requires Linux with evdev.** macOS is not supported.

Keyboard input is read directly from evdev, bypassing the terminal. The terminal (Alacritty) is display-only. This gives us:
- True key down/up events for reliable timing
- Space-hold detection for paint mode
- All keycodes (terminals drop some F-keys)

The keyboard handling:
- Grabs the hardware keyboard exclusively (kiosk mode)
- Remaps physical F-keys via scancodes (survives Fn Lock changes)
- Detects sticky shift, double-tap, and Escape long-press
- Processes events through a state machine that emits high-level actions

See `guides/keyboard-architecture.md` for technical details.

---

## Screen Size

Purple Computer displays a **100×28 character viewport** (plus header and footer) that fills **80% of the screen**. Font size is automatically calculated to fit, clamped to 12-24pt. On typical donated laptops (11-15"), this fills most of the screen with a visible purple border. On larger displays (17"+), the 24pt cap creates more border space.

**Minimum supported resolution:** 1024×768

---

## Architecture

```
purplecomputer/
├── purple_tui/           # Main Textual TUI application
│   ├── modes/            # Ask, Play, Write modes
│   ├── content.py        # Content API for packs
│   └── tts.py            # Piper TTS integration
│
├── packs/                # Built-in content (emoji, sounds)
│
├── build-scripts/        # Ubuntu ISO remaster build pipeline
│   ├── 00-build-golden-image.sh    # Pre-built Ubuntu system image
│   ├── 01-remaster-iso.sh          # Remaster Ubuntu Server ISO (initramfs injection)
│   ├── build-all.sh                # Orchestrate build steps
│   ├── build-in-docker.sh          # Docker wrapper (NixOS-friendly)
│   ├── validate-build.sh           # Pre-build validation
│   ├── flash-to-usb.sh             # Write ISO to USB with verification
│   └── install.sh                  # Installation script (runs in initramfs)
│
└── guides/               # Technical references
    └── ubuntu-live-installer.md
```

**Stack:**
- **Target System:** Ubuntu 24.04 LTS minimal + X11 + Alacritty + Textual TUI
- **Installer:** Remastered Ubuntu Server ISO with initramfs hook, Secure Boot support
- **Application:** Python + Textual + Piper TTS + Pygame

**How Installation Works:**

There are **two separate systems** involved:

1. **USB Installer** (temporary): A remastered Ubuntu Server ISO with a two-gate safety model.
   - **Gate 1 (initramfs):** Checks for `purple.install=1` in kernel cmdline, writes runtime artifacts to `/run/`
   - **Gate 2 (userspace):** Shows confirmation screen, requires user to press ENTER
   - Ubuntu's boot stack (shim, GRUB, kernel) and squashfs are untouched

2. **Installed System** (permanent): A pre-built Ubuntu 24.04 image created with debootstrap. This is what kids actually use.

The USB's only job is to copy the pre-built image to disk (after user confirmation). After reboot, the USB is never used again.

**Why this design:**
- Ubuntu's signed boot chain → Secure Boot works
- Ubuntu's stock kernel → all hardware drivers included
- No package installation during setup → fast, reliable, offline
- Standard Ubuntu on the installed system → normal apt updates work
- Initramfs hook writes to `/run/` → squashfs never modified
- Two-gate safety → explicit user consent before disk writes

See [guides/architecture-overview.md](guides/architecture-overview.md) for a detailed explanation of why this design exists and what alternatives we tried.

---

## System Requirements

**Target Hardware:**
- x86_64 processor (Intel/AMD, 64-bit)
- 2GB RAM minimum (4GB recommended for smooth TTS)
- 16GB storage minimum (the installer requires this)
- 1024×768 display minimum
- Audio output (speakers or headphones)
- BIOS or UEFI firmware (Secure Boot supported)

**Tested on:** 2010-2020 era laptops (ThinkPad, Dell Latitude, HP EliteBook, Surface, MacBook Air/Pro)

**Build Machine:**
- Any system with Docker (NixOS, Ubuntu, macOS, etc.)
- 20GB free disk space
- Docker daemon running
- Internet connection (for package download only)

---

## Documentation

- **[MANUAL.md](MANUAL.md):** Complete build instructions, customization, and troubleshooting
- **[guides/](guides/):** Technical deep-dives (architecture, installer, ask mode design, etc.)

---

## Philosophy

**A calm computer parents don't have to fight with.**

- Simple, text-based interface: easy for kids, calming for parents
- Your kid's first computer that isn't trying to control their attention
- A tool, not a toy. Runs on any old laptop you have lying around
- Offline and private: no internet required, no tracking, no data collection

---

## Third-Party Credits

Purple Computer includes code from the following open-source projects:

- **[spectral.js](https://github.com/rvanwijnen/spectral.js)** by Ronald van Wijnen (MIT License): Paint-like color mixing using Kubelka-Munk theory, ported to Python for realistic pigment blending (yellow + blue = green)

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
