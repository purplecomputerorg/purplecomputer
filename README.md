This file is AI-generated with a [human](https://github.com/tavinathanson) heavily involved. Human involvement varies across this repo; see [DISCLOSURE.md](/docs/DISCLOSURE.md). That is about how the code and docs get written; for what's in the product, see [Does Purple use AI?](#does-purple-use-ai) below.

# Purple Computer

**A calm, offline computer for kids.**

Transform your old laptop into an offline space for open-ended play. No internet, no apps. Designed for ages 3-10, from learning letters to writing code.
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

> **Which branch?** `main` is what ships on Purple Keys and the download.
> `release/1.x` is the frozen Purple 1.0 and no longer shipped.

---

## What Is Purple?

Purple Computer turns your old laptop into a calm, creative computer for kids. When you turn it on, it starts straight into Purple. There's no desktop and no other apps.

- **Building, not consuming.** Words, colors, sounds, and numbers to play with.
- **Nothing to break.** The whole laptop is Purple. No apps, no internet, nothing to mess up.
- **No chatbot.** Just regular if/then logic, so it never says anything unexpected. [More below](#does-purple-use-ai).
- **A screen they walk away from.** No tantrums, no parental controls needed.
- **Pay once, use on every laptop.** Works on every laptop you own, now or later.

**Learn more at [purplecomputer.org](https://purplecomputer.org).**

---

## Does Purple use AI?

No. There's no chatbot, no LLM in the product, nothing that generates unpredictable output. The one ML component is speak-out-loud, which uses [Piper](https://github.com/rhasspy/piper) for text-to-speech (or [flite](https://github.com/festvox/flite) as the Quick voice); it runs entirely on the laptop, offline, with nothing sent anywhere. Purple Studio voices a family room's fixed lines with [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), in the parent's browser, before the pack ever reaches Purple.

A lot of the code is LLM-generated, and LLMs are also used to make the demo videos, but no LLM ships in the product. The image gets `purplecomputer/`, `packs/`, and a named list of files from `scripts/` (see `build-scripts/00-build-golden-image.sh`); `anthropic` is only in `tools/requirements.txt`. Generated assets are checked in as fixed data, like the keypress list in `purplecomputer/demo/segments/`. See [DISCLOSURE.md](/docs/DISCLOSURE.md).

---

## Quick Start

### For Development (Linux only)

Purple Computer requires Linux with evdev for keyboard input. macOS is not supported. Use a Linux VM if developing on Mac (see `guides/linux-vm-dev-setup.md`).

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
just setup    # Creates venv, installs deps, downloads TTS voice, installs fonts
just run      # Opens Purple in a window (SDL keyboard, no evdev needed)
PURPLE_UX=tui just run   # The Textual UI the current release ships, in Alacritty
```

In the Play room, try:
```
2 + 2                  # Math with dot visualization
3 * 4 + 2              # Operator precedence (= 14)
cat * 5                # Five cats
dog + cat              # Emoji addition (🐶 🐱)
3 + 4 + 2 bananas      # Numbers attach to emoji (= 9 bananas)
red + blue             # Color mixing (= purple)
2 dark red             # Two dark red squares
purple truck           # Color swatch + emoji in free text
1234                   # Big numbers show as an abacus
I love cat!            # Speaks "I love cat" aloud (! triggers speech)
say 5 x 5 apples       # Shows 25 apples and says "5 times 5 apples equals 25 apples"
red + yellow!          # Shows orange and says "red plus yellow equals orange"
```

### For Installation (Old Laptop)

**Build prerequisites:** [`just`](https://github.com/casey/just), Docker (Podman works too: install your distro's `podman-docker` package so the `docker` command exists), and about 20GB free disk. Linux is the tested platform. Building on a Mac with Docker Desktop should be doable but is currently untested: share `/opt` in Docker Desktop's file-sharing settings, and on Apple silicon enable Rosetta emulation and `export DOCKER_DEFAULT_PLATFORM=linux/amd64` first. The flash tooling is Linux-only either way; on a Mac, write the ISO with `dd` or balenaEtcher instead (see [MANUAL.md](docs/MANUAL.md)).

The build keeps its working state and finished ISOs in `/opt/purple-installer` on the host (root-owned, created by the build). To put it somewhere else, edit the paths at the top of `build-scripts/config.sh` before building.

The happy path for "I tweaked Purple and want it on my USB" is two commands:

```bash
# Build the installer ISOs (20-35 min first time, 15-25 min subsequent)
just build

# Flash to USB: asks which ISO variant to use, verifies the write
just flash
```

No setup needed: `just flash` lists plugged-in USB sticks (64GB or smaller)
and asks which to use, then asks for a final confirmation before erasing it.
Drives larger than 64GB are never offered, so a real hard drive is never one
typo away from being wiped. To flash a bigger drive, or to skip the picker
when flashing often, whitelist it: `just flash --list` shows serials, then
add one per line to `.flash-drives.conf`.

Each build produces two ISO variants; `just flash` shows them and asks
which you want. For a personal USB, **standard** is all you need; **debug**
shows a boot menu with verbose logging for troubleshooting. (A third
variant, **with-backup**, adds a second copy of the install image so the
install self-heals if the USB stick decays. Shipped Purple Keys use it;
build it with `PURPLE_WITH_BACKUP_ISO=1 just build` if you want it.)
Everything else in `build-scripts/` (batch flashing, QA manifests,
corrupt-test ISOs, release uploads) is for producing shipped Purple Keys;
you can ignore it.

Prefer your own flashing tool? The ISOs are hybrid images, so any raw ISO
writer works: write `/opt/purple-installer/output/purple-installer-<date>.iso`
(the standard variant) with `dd`, balenaEtcher, or Rufus (pick DD mode if it
asks). You lose `just flash`'s write verification and its one-time boot-settle,
so the first boot on some sticks is slower; everything else is identical.

**Install to hardware:**
1. Boot laptop from USB (Secure Boot can remain enabled)
2. Open the Parent Menu (hold Escape) and choose Install on this Computer, then confirm
3. Installation runs (10-20 minutes), then system reboots into Purple Computer

Settings, saves and Time Travel from the live session come along. Reinstalling over an existing Purple keeps the kid's work, Purple Packs and computer name by default; starting fresh has its own confirm.

The system logs in automatically as the `purple` user (no password needed).

> **Booting from the USB changes nothing on your laptop.** Windows, macOS, and Linux are untouched. Remove the USB and restart to get back to normal. Installation only happens if you explicitly choose it from the parent menu. See [guides/live-boot-safety.md](guides/live-boot-safety.md) for how this is enforced.

See [MANUAL.md](docs/MANUAL.md) for complete build/customization details.

---

## The Rooms

| Room | What It Does |
|------|--------------|
| **Art** | Paint and write on a grid with colors that mix like real paint. Each letter paints its sticker color; hold two letters to mix them. Purple starts here. |
| **Music** | Every key plays a note or a drum and lights up. Enter changes the instrument, hold Enter to record a loop, arrows change the key. Tab says letters, and a word they spell shows up with its picture. Even a 2-year-old can have fun here. |
| **Play** | Type a word, see an emoji, hear it spoken, mix colors, do math. Pre-readers can use it with just numbers (2 + 3). See [guides/play-room-design.md](guides/play-room-design.md) |
| **Blocks** | Every letter places a block of its sticker color on a 3D floor. Enter builds up, Tab turns the room around, and holding Tab looks down from above. |
| **Write** | A quiet page for stories and letters, for older kids. Off until a parent turns it on in Parent Menu, Rooms. |

Families can add their own rooms (games, stories, worlds) from [Purple Studio](#purple-studio). They show as extra rooms on keys 6 to 0 in the Esc menu once a parent turns them on.

**Controls:**
- **Esc (tap):** the Esc menu: rooms on top (press a number), then tools for the room you're in: **Code** (Space), **Colors** (\\), **Time Travel** (T), **Save** (S), **Open** (O), **Print** (P, when a USB printer is plugged in), **Clear** (C), and **Volume** (V)
- **Hold Esc (1s):** Parent Menu
- **Hold \\ (3s):** Parent Menu (alternate, works on all keyboards)
- **Tab:** the room's switch: Paint/Letters in Art, Notes/Letters in Music, Front/Back in Blocks (hold it to look down from above), `say` on or off in Play
- **Space** (Art, Blocks): put the brush down or lift it; hold it with the arrows to paint a trail or lay a line
- **Enter** (Music): the next instrument; in Letters, whether letters say their names ("bee") or their sounds ("b")
- **Space** (Music, in Letters): say the word the letters just spelled, shown under the grid
- **Volume:** hardware media keys, or V in the Esc menu

**Speech** (in Play room): Add `!` anywhere (e.g., `cat!`), start with `say`, or press Tab to hear the line spoken aloud.

### Code

Older kids can write code in Art, Music and Blocks: hold Esc and press Space (or pick Code in the Esc menu). The code line opens holding the code for what they just did by hand, with a guide of words beside it and example cards below. Esc + Space closes it. Parents can turn it off (Parent Menu, Features).

```
red repeat 4 forward 6 turn       # Art: a red square
right 2 brush up right 3          # Art: a line with a gap
write hi                          # Art: letters on the grid
choose ukulele zxcvbnm            # Music: pick a sound, then play keys
fast asdf slow jkl                # Music: quick notes, then slow
key g                             # Music: same keys, new notes
letters sounds                    # Music: keys say their letter sounds
green repeat 4 right 1 up 1       # Blocks: stairs
right hello                       # Blocks: a block per letter
red up 3 blue right 2             # Blocks: a new color as you go
```

`repeat N` repeats the rest of the line, commas split it into steps, and misspellings are fixed and shown.

### Saving, Time Travel and printing

Every room is kept across restarts. **Time Travel** rewinds a room to any earlier moment (← and →, Enter keeps it). **Save** keeps a picture of the work and **Open** brings saves back; plugging in a USB printer adds **Print**, signed with the computer's name. Parents can copy saved work to a USB drive from the Parent Menu. On a live Purple Key, saves live on the Key itself.

### Parent Menu

Hold Esc for a second (behind an optional PIN): install, name the computer, **Kid Profiles** (each kid gets their own computer name, settings, saves and Time Travel), **Rooms** (turn rooms on and off, and **Littles Mode**: one activity, no menus), code and Music options, **Purple Packs**, ALL CAPS, Sound (with a volume limit, 0 is Silent Mode), Voice, Display, Copy Saved Work to USB, Open Terminal, Support Info and Shut Down.

---

## Purple Studio

[studio.purplecomputer.org](https://studio.purplecomputer.org/) is a website for parents to make a **Purple Pack** for their family: their own words and photos (type "grandma" and see her picture), their voice on the keys, instruments, screen and paint colors, and whole new rooms written with blocks or Python, all tried live on a real Purple running in the browser. Nothing is uploaded. The pack goes onto any USB drive; plug it into Purple and it asks to add it. Source and pack format: [`studio/`](studio/), [`studio/PACK_FORMAT.md`](studio/PACK_FORMAT.md), [guides/family-rooms.md](guides/family-rooms.md).

---

## Keyboard Features

Purple is keyboard only, on purpose. A few things make typing easier for kids:

- **Sticky Shift:** tap Shift and the next key is shifted, with a ⇧ badge on screen until it's used
- **Kid math keys:** `=` types `+`, `/` types `÷`, Shift+8 types `×`, matching the sticker sheet
- **ALL CAPS:** a Parent Menu setting that shows every letter as a capital

### How It Works

**Purple Computer requires Linux with evdev.** macOS is not supported.

Keyboard input is read directly from evdev; the screen is a pygame canvas the app paints itself. This gives us:
- True key down/up events for holds, chords and color mixing
- All keycodes (terminals drop some F-keys)

The keyboard handling:
- Grabs the hardware keyboard exclusively (kiosk mode)
- Remaps physical F-keys via scancodes (survives Fn Lock changes)
- Detects sticky shift and long presses (Escape, Enter, Backspace)
- Processes events through a state machine that emits high-level actions

See `guides/keyboard-architecture.md` for technical details.

---

## Screen Size

The canvas is laid out in fractions of the screen, so it fills any display from a 1024×768 netbook to a 4K TV. Screens over 1920×1200 (Retina MacBooks, 4K TVs) switch to a smaller mode of the same shape to keep software drawing fast; touch `/opt/purple/native-resolution` to keep the native size. See [guides/canvas-architecture.md](guides/canvas-architecture.md).

**Minimum supported resolution:** 1024×768

---

## Architecture

```
purplecomputer/
├── purplecomputer/           # The app: engine modules plus two UIs (see CLAUDE.md, Two UIs)
│   ├── canvas/           # The pygame canvas UI (default): rooms, drawing, headless harness
│   ├── rooms/            # The Textual UI's rooms (frozen: what release/1.x ships; PURPLE_UX=tui)
│   ├── demo/             # Demo recording and playback system
│   ├── content.py        # Content API for packs
│   ├── keyboard.py       # Keyboard state machine
│   ├── input.py          # Direct evdev keyboard input
│   ├── synth.py          # Instrument synthesis, shared with Studio
│   └── tts.py            # Piper TTS integration
│
├── packs/                # Built-in content (emoji, sounds)
├── studio/               # Purple Studio, the parent-facing web app that builds Purple Packs
├── cards/                # Print-ready cards and stickers for the box
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
│   ├── calc_font_size.py           # Font sizing for the Textual UI
│   ├── export_studio.py            # Facts and reference renders Studio depends on
│   ├── generate_sounds.py          # Procedural sound synthesis
│   └── generate_voice_clips.py     # TTS narration generation
│
├── tools/                # Dev-machine only: authoring demo content (never shipped)
│   ├── art_ai.py                  # Generates Art room demo drawings for videos
│   └── music_ai.py                # Generates Music room demo compositions for videos
│
├── config/               # System configs (X11, keyd, picom, systemd)
├── tests/                # Test suite
└── guides/               # Technical references
```

What actually ships is whatever `build-scripts/00-build-golden-image.sh` copies into `/opt/purple`: `purplecomputer/`, `packs/`, and two named scripts. `tools/` and `scripts/ai_ux_*` stay on the developer's machine, as does the demo tooling in `recording-setup/`.

**Stack:**
- **Target System (PurpleOS):** Ubuntu 24.04 LTS minimal + X11 + a fullscreen pygame window (software rendering, no GL). Machines with 32-bit CPUs get a Debian trixie i386 image instead; GRUB picks it per machine (see `guides/hardware-coverage-plan.md`)
- **Installer:** Remastered Ubuntu Server ISO with initramfs hook, Secure Boot support
- **Application:** Python + Pygame (SDL2) + Piper TTS

**How Installation Works:**

There are **two separate systems** involved:

1. **USB (live boot)** (temporary): A remastered Ubuntu Server ISO that boots straight into Purple. Ubuntu's boot stack (shim, GRUB, kernel) is untouched; we swap in our own squashfs. Installation is optional and is started from the Parent Menu inside the running app, not from GRUB.

2. **Installed System** (permanent): A pre-built Ubuntu 24.04 image created with debootstrap (Debian i386 for 32-bit CPUs). This is what kids use once a parent installs to disk.

When a parent chooses "Install on this Computer" from the (PIN-gated) parent menu and confirms the data-loss warning, `install.sh` copies the pre-built image to the internal disk. After reboot, the USB is no longer needed.

**Why this design:**
- Ubuntu's signed boot chain → Secure Boot works
- Ubuntu's stock kernel → all hardware drivers included
- No package installation during setup → fast, reliable, offline
- Same root filesystem for live boot and install → built once, packaged twice
- Install consent lives in the app (PIN + confirmation) → explicit user consent before disk writes

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

**Also:** 2018-2020 Intel Macs with the T2 chip (t2linux kernel), 32-bit CPUs (Debian i386 image), and 32-bit UEFI firmware, each picked per machine by GRUB. `just build-pi` makes a card image for Raspberry Pi 4, 400, 5 and 500.

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
- **[guides/canvas-architecture.md](guides/canvas-architecture.md):** How the canvas UI draws and takes input
- **[guides/family-rooms.md](guides/family-rooms.md):** Family rooms from Purple Packs, and how they run sandboxed
- **[guides/printing.md](guides/printing.md):** Plug-in USB printing
- **[guides/mode-reference.md](guides/mode-reference.md):** Room mechanics for demo scripting (written for the Textual UI)
- **[guides/kid-proofing.md](guides/kid-proofing.md):** Kiosk lockdown and safety measures
- **[guides/usb-flash-settle.md](guides/usb-flash-settle.md):** Why freshly flashed drives get a one-time QEMU boot

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
- **[Twemoji](https://github.com/jdecked/twemoji)** by Twitter and contributors ([CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)): source artwork for several stickers — T-Rex (U+1F996), ringed planet (U+1FA90), Earth (U+1F30E), turtle (U+1F422), and sun-with-face (U+1F31E) — and Purple Studio's section and starter room icons (listed in `cards/make_studio_icons.py`), recolored to Purple Computer shades in the scripts under `cards/`.
- **[Open Letter Sounds](https://github.com/purplecomputerorg/openlettersounds)** by Purple Computer ([CC0](https://creativecommons.org/publicdomain/zero/1.0/)): the letter sounds Music says in Letters with Enter (`packs/core-sounds/content/letter-sounds/`), raised to the letter names' volume.
- **[SCOWL](http://wordlist.aspell.net/)** by Kevin Atkinson (permissive license, full notice in `purplecomputer/music_words_scowl_copyright.txt`): the word list behind the words Music says back in Letters (`purplecomputer/music_words.txt`).

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
