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

## The Four Modes

Purple has four core modes, accessed with F1-F4:

| Key | Mode | What It Does |
|-----|------|--------------|
| F1 | **Ask** | Math and emoji. Type `2 + 2` or `cat * 3` or `what is elephant` |
| F2 | **Play** | Music and art grid. Letters make notes and colors. Numbers make sounds. |
| F3 | **Listen** | Stories and songs. (Coming soon) |
| F4 | **Write** | Simple text editor. Just type. |

**Controls:**
- **F1-F4** — Switch modes
- **Ctrl+V** — Cycle views (Screen → Line → Ears)
- **F12** — Toggle dark/light mode
- **Tab** (in Ask mode) — Toggle speech on/off

---

## Three Views

Purple reduces "screen time" feeling with three views:

- **Screen view** — 8×4.5" viewport centered on screen, purple border filling the rest
- **Line view** — Single line, calculator vibes
- **Ears view** — Screen off, audio only (for Play and Listen modes)

---

## Quick Start

### For Developers (Mac/Linux)

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
make setup    # Creates venv, installs deps, downloads TTS voice, installs fonts
make run      # Launches in Alacritty with Purple theme (or current terminal)
```

**What `make setup` does:**
- Creates Python virtual environment (`.venv/`)
- Installs dependencies: `textual`, `rich`, `wcwidth`, `pygame`, `piper-tts`
- Downloads Piper TTS voice model for speech
- Installs JetBrainsMono Nerd Font
- Builds content packs

Inside Purple Computer, try:
```
2 + 2              # Math
cat * 5            # Five cats
dog + cat          # Emoji addition
what is elephant   # Definition lookup
```

### For Parents (Installing on Old Laptop)

**Target hardware:** 2012-2018 Mac laptops (consistent bootloaders, no T2/Apple Silicon complexity)

**Option 1: USB Install (Recommended)**
1. Download the Purple Computer ISO (or build with `make build-iso`)
2. Write to USB with [balenaEtcher](https://www.balena.io/etcher/)
3. Boot from USB — installation is automatic
4. Remove USB when done

**Option 2: Manual Install** (Existing Ubuntu 22.04):
```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
sudo ./autoinstall/files/setup.sh
sudo reboot
```

---

## Content Packs

Purple uses **purplepacks** for content — emoji, definitions, sounds, words.

Purplepacks are **content only** (JSON + assets). They never contain executable code. Parents can safely install them offline.

**Built-in packs:**
- `core-emoji` — ~100 kid-friendly emojis with synonyms
- `core-definitions` — Simple word definitions
- `core-sounds` — Number and punctuation sounds for Play mode
- `core-words` — Word lookups and synonyms

### Creating Content Packs

```bash
# Emoji pack structure
my-emoji-pack/
├── manifest.json
└── content/
    ├── emoji.json      # {"word": "emoji"}
    └── synonyms.json   # {"synonym": "canonical_word"}
```

**manifest.json:**
```json
{
  "id": "my-pack",
  "name": "My Pack",
  "version": "1.0.0",
  "type": "emoji"
}
```

Valid types: `emoji`, `definitions`, `sounds`, `words`

**Build it:**
```bash
tar -czvf my-pack.purplepack manifest.json content/
```

---

## Architecture

```
purplecomputer/
├── purple_tui/           # Main Textual TUI application
│   ├── purple_tui.py     # App entry point
│   ├── constants.py      # Icons, colors, mode titles
│   ├── modes/            # Mode modules (curated Python code)
│   │   ├── ask_mode.py   # Math and emoji REPL
│   │   ├── play_mode.py  # Music and art grid
│   │   ├── write_mode.py # Simple text editor
│   │   └── listen_mode.py# Stories (stub)
│   ├── content.py        # Content API for purplepacks
│   ├── pack_manager.py   # Content-only pack installer
│   └── tts.py            # Piper TTS integration
│
├── packs/                # Content packs (no executable code)
│   ├── core-emoji/       # Emojis + synonyms
│   ├── core-definitions/ # Word definitions
│   ├── core-sounds/      # Audio files for Play mode
│   └── core-words/       # Word lookups
│
├── autoinstall/          # Ubuntu installation configs
│   └── files/
│       ├── alacritty/    # Terminal config (dev + prod)
│       ├── xinit/        # X11 startup
│       └── setup.sh      # Installation script
│
├── scripts/              # Build and dev utilities
│   ├── setup_dev.sh      # Development environment setup
│   ├── run_local.sh      # Local runner (Mac/Linux)
│   └── generate_sounds.py# Sound generation script
│
└── tests/                # Test suite
```

**Key design decisions:**
- **Modes are Python modules** — Curated, reviewed code shipped with Purple. Future modes distributed via Purple Store only.
- **Purplepacks are content only** — JSON + assets, no Python. Safe for parents to install.
- **Alacritty terminal** — Fast, simple, reliable Unicode/emoji rendering.
- **Textual TUI** — Modern Python TUI framework for the interface.
- **Piper TTS** — Offline text-to-speech using neural voices.
- **Pygame** — Audio playback for sounds in Play mode.
- **10×6" viewport** — Consistent size across laptops, calming, strong purple branding.

---

## System Requirements

- x86_64 processor (Intel or AMD)
- 2GB RAM minimum
- 8GB storage minimum
- USB port for installation

**Recommended:** 2012-2018 MacBook Air/Pro

**Stack:** Ubuntu Server 22.04 + minimal Xorg + Alacritty + Textual TUI

**Python Dependencies:** `textual`, `rich`, `wcwidth`, `pygame`, `piper-tts`

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

Made with 💜 for curious little minds
