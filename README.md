This file is AI-generated with a [human](https://github.com/tavinathanson) heavily involved. Human involvement varies across this repo; see [DISCLOSURE.md](/docs/DISCLOSURE.md).

# Purple Computer

**Give them a calm computer you can feel good about.**

Transform your old laptop into a calm space for open-ended play. No internet, no apps. Designed for ages 3-10, from learning letters to writing code.
They explore, create, and put it down on their own.

> **Purple Computer is a paid product.**
> The source code is public so you can see how it works, but Purple Computer
> is not free software. To use it, purchase at [purplecomputer.org](https://purplecomputer.org)
> or contact us at tavi@purplecomputer.org.
>
> Purple is source available, **not open source**: you're welcome to look around,
> try things out, and modify your own copy for personal use, but please don't
> redistribute it. Pull requests aren't accepted; bug reports and feature ideas
> are always welcome via email. See [LICENSE](LICENSE) and
> [CONTRIBUTING.md](CONTRIBUTING.md) for details.

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
just setup    # Creates venv, installs deps, downloads TTS voice, installs fonts
just run      # Launches in Alacritty with Purple theme
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
2. Open the parent menu (hold Escape) and choose Install, then confirm
3. Installation runs (10-20 minutes), then system reboots into Purple Computer

The system logs in automatically as the `purple` user (no password needed).

> **Booting from the USB changes nothing on your laptop.** Windows, macOS, and Linux are untouched. Remove the USB and restart to get back to normal. Installation only happens if you explicitly choose it from the parent menu. See [guides/live-boot-safety.md](guides/live-boot-safety.md) for how this is enforced.

See [MANUAL.md](docs/MANUAL.md) for complete build/customization details.

---

## The Three Rooms

Purple has three rooms:

| Room | What It Does |
|------|--------------|
| **Play** | Type a word, see an emoji, hear it spoken, mix colors, do math. Kids who can read get the most out of this, but even pre-readers can use it with just numbers (2 + 3). See [guides/play-room-design.md](guides/play-room-design.md) |
| **Music** | Make music and draw with the keyboard. Press any key to play a sound and paint a color. Even a 2-year-old can have fun here. |
| **Art** | Write and paint with colors that mix like real paint. Great around 3-4+. |

**Controls:**
- **Escape (tap):** Room picker (Play, Music, Art)
- **Hold Escape (1s):** Parent menu
- **Hold \\ (3s):** Parent menu (alternate, works on all keyboards)
- **Caps Lock:** Toggle big/small letters
- **Tab** (in Art): Toggle write/paint mode
- **Volume:** Hardware media keys

**Speech** (in Play room): Add `!` anywhere (e.g., `cat!`) or use `say`/`talk` prefix to hear results spoken aloud.

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

Purple Computer displays a **134×29 character viewport** (plus header and footer). Font size is automatically calculated to fit the screen, clamped to 12-48pt. On typical old laptops (11-15"), this fills most of the screen with a visible purple border.

**Minimum supported resolution:** 1024×768

---

## Architecture

```
purplecomputer/
├── purple_tui/           # Main Textual TUI application
│   ├── rooms/            # Play, Music, Art rooms (+ parent menu, sleep screen)
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
│   ├── doodle_ai.py               # AI art room drawing generation
│   └── play_ai.py                 # AI music room content
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

1. **USB (live boot)** (temporary): A remastered Ubuntu Server ISO that boots straight into Purple. Ubuntu's boot stack (shim, GRUB, kernel) is untouched; we swap in our own squashfs. Installation is optional and is started from the parent menu inside the running TUI, not from GRUB.

2. **Installed System** (permanent): A pre-built Ubuntu 24.04 image created with debootstrap. This is what kids use once a parent installs to disk.

When a parent chooses "Install on this Computer" from the (PIN-gated) parent menu and confirms the data-loss warning, `install.sh` copies the pre-built image to the internal disk. After reboot, the USB is no longer needed.

**Why this design:**
- Ubuntu's signed boot chain → Secure Boot works
- Ubuntu's stock kernel → all hardware drivers included
- No package installation during setup → fast, reliable, offline
- Same root filesystem for live boot and install → built once, packaged twice
- Install consent lives in the TUI (PIN + confirmation) → explicit user consent before disk writes

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

- **[MANUAL.md](docs/MANUAL.md):** Complete build instructions, customization, and troubleshooting
- **[guides/demo-system.md](guides/demo-system.md):** Creating, generating, and composing demo screencasts
- **[guides/architecture-overview.md](guides/architecture-overview.md):** Why the installer works the way it does
- **[guides/keyboard-architecture.md](guides/keyboard-architecture.md):** evdev input, state machine, F-key calibration
- **[guides/play-room-design.md](guides/play-room-design.md):** How the Play room parses and evaluates input
- **[guides/sound-synthesis.md](guides/sound-synthesis.md):** Procedural sound generation
- **[guides/mode-reference.md](guides/mode-reference.md):** Reference for all rooms and controls
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
- **[Twemoji](https://github.com/jdecked/twemoji)** by Twitter and contributors ([CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)): source artwork for several stickers — T-Rex (U+1F996), ringed planet (U+1FA90), Earth (U+1F30E), turtle (U+1F422), and sun-with-face (U+1F31E) — recolored to Purple Computer shades in the scripts under `cards/`.

---

## License

Purple Computer is a paid product. Purchase at [purplecomputer.org](https://purplecomputer.org) or contact tavi@purplecomputer.org.

The source code is public so you can see exactly what runs on your kid's computer. You're welcome to browse the code, try it out, and modify your own copy for personal use, but please purchase a license before regular use.

Purple is source available, **not open source**: no redistribution, and pull requests aren't accepted. Bug reports and feature ideas are always welcome at tavi@purplecomputer.org. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full picture.

See [LICENSE](LICENSE) for the full Source-Available License 1.1.

**Without written permission, you may not:**
- Redistribute the code, modified versions, or add-ons built on it
- Use it commercially or offer it as a service

---

💜
