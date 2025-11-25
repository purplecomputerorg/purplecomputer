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
See [docs/parents.md](docs/parents.md) for:
- What to expect when your child uses Purple Computer
- How to exit the kid environment (parent escape)
- Simple troubleshooting

### For Developers
See [docs/dev.md](docs/dev.md) for:
- Development environment setup
- Testing the REPL locally
- Contributing guidelines

### Building the ISO
See [docs/autoinstall.md](docs/autoinstall.md) for:
- Creating a bootable USB drive
- Automated installation process
- System configuration details

## Features

- **Instant Boot**: Powers on directly into the kid-friendly environment
- **Speech**: Everything typed can be spoken aloud with pleasant voices
- **Emoji Magic**: Pre-loaded emoji variables and pattern generators
- **Creative Modes**: Switch between speech, emoji, math, rainbow, and surprise modes
- **Big Letter Mode**: Automatically activates when Caps Lock is on, perfect for beginning readers
- **Safe Environment**: Kids can't break out or damage the system
- **Parent Controls**: Secret escape mechanism for adult access
- **Offline**: Works completely offline once installed

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
├── autoinstall/              # Ubuntu autoinstall configs
├── purple_repl/              # The kid-friendly REPL
└── scripts/                  # Build and test utilities
```

## Philosophy

Purple Computer is built on these principles:
- **Safe to Explore**: No wrong answers, no breaking things
- **Age Appropriate**: Designed for ages 3-8
- **Parent Friendly**: Non-technical adults can set it up
- **Offline & Private**: No internet, no tracking, no data collection

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Getting Help

- Check [docs/parents.md](docs/parents.md) for common questions
- See [docs/dev.md](docs/dev.md) for technical documentation
- File issues on GitHub for bugs or feature requests

---

Made with 💜 for curious little minds
