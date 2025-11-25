# Purple Computer 💜

A Linux-based computing environment for young children (ages 3-8) that boots directly into a kid-friendly, fullscreen terminal with emojis, speech, and creative exploration.

## What is Purple Computer?

Purple Computer is a real computer for kids. They type on a keyboard, run commands, and see what happens. It teaches:
- Typing and keyboard use
- Text-based interaction (reading, typing, commands)
- Creative exploration with code
- How to give computers commands

No desktop. No apps. Just a purple terminal where they can explore and create.

It's offline, private, and runs on old hardware you already have.

## Quick Start

### For Parents
- [docs/parents.md](docs/parents.md) - What to expect, basic usage
- [docs/parent-mode.md](docs/parent-mode.md) - Parent mode guide, password setup, settings
- [docs/packs.md](docs/packs.md) - Installing and creating content packs
- [docs/updates.md](docs/updates.md) - How updates work

### For Developers
- [docs/dev.md](docs/dev.md) - Development environment setup
- [docs/architecture.md](docs/architecture.md) - System architecture and design
- [docs/autoinstall.md](docs/autoinstall.md) - Building the installation ISO

### Installing Purple Computer
1. Download or build the ISO (see [docs/autoinstall.md](docs/autoinstall.md))
2. Write to USB drive
3. Boot from USB and walk away - installation is automatic
4. System reboots into Purple Computer
5. Set parent password on first parent mode access

## Features

### For Kids
- **Instant Boot**: Powers on directly into the kid-friendly environment
- **Speech**: Everything typed can be spoken aloud with pleasant voices
- **Emoji Magic**: Pre-loaded emoji variables and pattern generators
- **Creative Modes**: Switch between speech, emoji, math, rainbow, and surprise modes
- **Big Letter Mode**: Automatically activates when Caps Lock is on, perfect for beginning readers
- **Expandable Content**: Emoji and definitions load from installed packs
- **Safe Environment**: Kids can't break out or damage the system

### For Parents
- **Password-Protected Parent Mode**: Manage system without kids accessing settings
- **Pack System**: Install emoji packs, educational content, and more
- **Update Manager**: Check for and install updates with one click
- **No System Password**: Kid user auto-logs in instantly
- **Parent Password**: Separate password protects parent-only features
- **Offline First**: Works completely offline, updates are optional

## System Requirements

- x86_64 computer (Intel or AMD processor)
- 2GB RAM minimum (4GB recommended)
- 8GB storage minimum
- USB port for installation

## Project Structure

```
purplecomputer/
├── README.md                 # This file
├── LICENSE                   # MIT License
├── docs/                     # Documentation
│   ├── architecture.md       # System architecture
│   ├── packs.md              # Pack creation guide
│   ├── updates.md            # Update system guide
│   ├── parent-mode.md        # Parent mode documentation
│   ├── autoinstall.md        # ISO building guide
│   └── dev.md                # Development guide
├── autoinstall/              # Ubuntu autoinstall configs
│   ├── autoinstall.yaml      # Ubuntu autoinstall configuration
│   └── files/                # Files copied during install
├── purple_repl/              # The kid-friendly REPL
│   ├── repl.py               # Main REPL
│   ├── pack_manager.py       # Pack system
│   ├── parent_auth.py        # Parent authentication
│   ├── update_manager.py     # Update system
│   ├── emoji_lib.py          # Emoji utilities
│   ├── tts.py                # Text-to-speech
│   └── modes/                # Interaction modes
├── packs/                    # Example packs
│   ├── core-emoji.purplepack
│   └── education-basics.purplepack
└── scripts/                  # Build and test utilities
    └── build_pack.py         # Pack builder tool
```

## Philosophy

Purple Computer is built on these principles:
- **Safe to Explore**: No wrong answers, no breaking things
- **Age Appropriate**: Designed for ages 3-8
- **Parent Friendly**: Non-technical adults can set it up
- **Offline & Private**: No internet, no tracking, no data collection

## License

MIT License - see [LICENSE](LICENSE) file for details.

## New in Version 2.0

- **Modular Pack System**: Install emoji, definitions, and content as packs
- **Password-Protected Parent Mode**: Secure access to settings and updates
- **Update Manager**: Fetch and install updates over HTTPS
- **No System Password**: Instant boot with auto-login
- **Registry Architecture**: Clean, extensible content management
- **Pack Builder**: Create and share your own content packs

See [docs/architecture.md](docs/architecture.md) for technical details.

## Getting Help

- **Parents**: Check [docs/parent-mode.md](docs/parent-mode.md) for common questions
- **Pack Creators**: See [docs/packs.md](docs/packs.md) for pack creation
- **Developers**: Read [docs/architecture.md](docs/architecture.md) for technical details
- **Issues**: File bugs or feature requests on GitHub

---

Made with 💜 for curious little minds
