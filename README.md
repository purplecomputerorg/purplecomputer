# Purple Computer

**Give them a first computer you can feel good about.**

Transform your old laptop into a calm space for open-ended play. Ages 4-7.
They explore, create, and put it down on their own.

> **🚧 WORK IN PROGRESS**
> Purple Computer is still in active development and testing. The installer ISO is not ready for use yet. We'll announce when it's ready.

> **Purple Computer is a paid product.**
> The source code is public so you can see how it works, but Purple Computer
> is not free software. To use it, purchase at [purplecomputer.org](https://purplecomputer.org)
> or contact us at tavi@purplecomputer.org.
>
> You're welcome to look around and try things out.
> See [LICENSE](LICENSE) for details.

---

## What Is Purple?

Purple Computer turns your old laptop into a calm, creative computer for kids. When you turn it on, it starts straight into Purple. There's no desktop and no other apps.

- **Building, not consuming.** Words, colors, sounds, and numbers to play with.
- **Nothing to break.** The whole laptop is Purple. No apps, no internet, nothing to mess up.
- **A screen they walk away from.** No tantrums, no parental controls needed.
- **Pay once, use on every laptop.** Works on every laptop you own, now or later.

**Learn more at [purplecomputer.org](https://purplecomputer.org).**

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
purple truck           # Color swatch + emoji in free text
I love cat!            # Speaks "I love cat" aloud (! triggers speech)
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
| **F1** | **Explore** | Type a word, see an emoji, hear it spoken, mix colors, do math. See [guides/explore-mode-design.md](guides/explore-mode-design.md) |
| **F2** | **Play** | Make music and draw with the keyboard. Press any key to play a sound and paint a color. |
| **F3** | **Doodle** | Write and paint with colors that mix like real paint. |

**Controls:**
- **Escape (tap):** Mode picker (Explore, Play, Doodle)
- **F1-F3:** Switch modes directly
- **F9:** Toggle dark/light theme
- **F10:** Mute/unmute, **F11:** Volume down, **F12:** Volume up
- **Caps Lock:** Toggle big/small letters
- **Ctrl+V:** Cycle views (Screen → Line → Ears)
- **Tab** (in Doodle): Toggle write/paint mode
- **Hold Escape (1s):** Parent mode (admin menu)

**Speech** (in Explore mode): Add `!` anywhere (e.g., `cat!`) or use `say`/`talk` prefix to hear results spoken aloud.

---

## Keyboard Features

Purple includes a hardware keyboard normalizer that makes typing easier for kids:

### Easy Capitals (No Shift Key Needed)
- **Double-tap any key** — Types the shifted version (`a` `a` → `A`, `1` `1` → `!`)
- **Tap Shift quickly** — Activates "sticky shift" for the next character
- **Hold Shift + type** — Normal shift behavior (uppercase while held)

Kids can type capital letters without holding two keys at once!

### Parent Mode
- **Hold Escape for 1 second** — Opens parent menu (display settings, volume, updates)

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

Purple Computer displays a **112×32 character viewport** (plus header and footer) that fills **80% of the screen**. Font size is automatically calculated to fit, clamped to 12-48pt. On typical old laptops (11-15"), this fills most of the screen with a visible purple border.

**Minimum supported resolution:** 1024×768

---

## Architecture

```
purplecomputer/
├── purple_tui/           # Main Textual TUI application
│   ├── modes/            # Explore, Play, Doodle modes
│   ├── demo/             # Demo recording and playback system
│   ├── content.py        # Content API for packs
│   ├── keyboard.py       # Keyboard state machine
│   ├── input.py          # Direct evdev keyboard input
│   └── tts.py            # Piper TTS integration
│
├── packs/                # Built-in content (emoji, sounds)
│
├── build-scripts/        # Ubuntu ISO remaster build pipeline
│   ├── 00-build-golden-image.sh    # Pre-built Ubuntu system image
│   ├── 01-remaster-iso.sh          # Remaster Ubuntu Server ISO (initramfs injection)
│   ├── build-in-docker.sh          # Docker wrapper (NixOS-friendly)
│   ├── validate-build.sh           # Pre-build validation
│   ├── flash-to-usb.sh             # Write ISO to USB with verification
│   └── install.sh                  # Installation script (runs in initramfs)
│
├── recording-setup/      # Demo video recording and post-processing
│   ├── record-demo.sh             # Full recording workflow
│   ├── apply_zoom.py              # FFmpeg zoom/crop/pan post-processing
│   └── zoom_editor_server.py      # Web UI for zoom keyframe editing
│
├── scripts/              # Development utilities
│   ├── calc_font_size.py           # Auto font sizing calculator
│   ├── generate_sounds.py          # Procedural sound synthesis
│   └── generate_voice_clips.py     # TTS narration generation
│
├── tools/                # AI-assisted content creation
│   ├── doodle_ai.py               # AI doodle drawing generation
│   └── play_ai.py                 # AI play mode content
│
├── config/               # System configs (Alacritty, X11, fonts)
├── tests/                # Test suite
└── guides/               # Technical references
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
- **[guides/demo-system.md](guides/demo-system.md):** Creating, generating, and composing demo screencasts
- **[guides/architecture-overview.md](guides/architecture-overview.md):** Why the installer works the way it does
- **[guides/keyboard-architecture.md](guides/keyboard-architecture.md):** evdev input, state machine, F-key calibration
- **[guides/explore-mode-design.md](guides/explore-mode-design.md):** How Explore mode parses and evaluates input
- **[guides/sound-synthesis.md](guides/sound-synthesis.md):** Procedural sound generation
- **[guides/mode-reference.md](guides/mode-reference.md):** Reference for all modes and controls
- **[guides/kid-proofing.md](guides/kid-proofing.md):** Kiosk lockdown and safety measures
- **[guides/production-checklist.md](guides/production-checklist.md):** Pre-ship checklist

---

## Philosophy

**Computers are a big part of their future.** Purple lets them start the way we did: open-ended play, making things, figuring it out.

- Their own computer, a real computer they use and put away on their own
- Building and creating, not watching and swiping
- No Wi-Fi, no browser, no way to connect to the internet
- Your old laptop still works. To your kid, it's a hand-me-down from a legend

---

## Third-Party Credits

Purple Computer includes code from the following open-source projects:

- **[spectral.js](https://github.com/rvanwijnen/spectral.js)** by Ronald van Wijnen (MIT License): Spectral reflectance data and CIE color matching functions, used for Beer-Lambert paint-like color mixing (yellow + blue = green, red + blue = purple)

---

## License

Purple Computer is a paid product. Purchase at [purplecomputer.org](https://purplecomputer.org) or contact tavi@purplecomputer.org.

The source code is public so you can see exactly what runs on your kid's computer.

Source-Available License 1.0 — see [LICENSE](LICENSE)

**You may:**
- View the source code
- Run for personal, private use

**You may NOT (without written permission):**
- Fork, modify, or create derivatives
- Redistribute or republish
- Use commercially

---

💜
