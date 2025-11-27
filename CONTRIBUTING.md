# Contributing to Purple Computer

Thanks for your interest in Purple Computer!

## Getting Started

### Quick Setup

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
make setup
make run
```

See [README.md](README.md#quick-start) for details.

## Development Workflow

### 1. Choose Your Testing Mode

- **Local** (fast iteration) - `make run`
- **Docker** (Ubuntu simulation) - `make run-docker`
- **VM** (full UI testing) - See [MANUAL.md](MANUAL.md#vm-testing-reproducible-environment)
- **Hardware** (production testing) - Build ISO

See [MANUAL.md - Development & Testing](MANUAL.md#development--testing) for full comparison.

### 2. Make Your Changes

- **Core REPL**: Edit files in `purple_repl/`
- **Packs**: Create/modify packs in `packs/`
- **Docs**: Update `README.md`, `MANUAL.md`, `CHANGELOG.md`

### 3. Test

```bash
# Local testing
make run

# Full simulation
make run-docker

# VM testing (for UI/UX changes)
# See MANUAL.md VM Testing section
```

### 4. Submit

- Fork the repository
- Create a feature branch (`git checkout -b feature/my-feature`)
- Commit your changes
- Push and open a pull request

## What to Contribute

### Priority Areas

- **Packs**: Emoji, educational content, interactive modes
- **Modes**: Music, drawing, games, creative tools
- **Documentation**: Tutorials, examples, improvements
- **Bug Fixes**: Issues, edge cases, errors
- **Testing**: Test coverage, QA, UX feedback

### Guidelines

**Do:**
- Keep it kid-friendly (ages 3-8)
- Test on actual hardware when possible
- Update documentation
- Follow existing code style
- Create packs for new features (see [MANUAL.md - Pack System](MANUAL.md#pack-system))

**Don't:**
- Add passive media consumption (videos, image galleries)
- Include internet requirements for core features
- Add complex dependencies
- Break offline functionality

## Creating Packs

Packs are the preferred way to extend Purple Computer. See [MANUAL.md - Pack System](MANUAL.md#pack-system) for complete documentation.

Quick example:
```bash
mkdir -p mypack/data
# Create manifest.json and content files
./scripts/build_pack.py mypack mypack.purplepack
```

## Code Style

- Python: Follow PEP 8, use descriptive names
- Comments: Explain why, not what
- Docstrings: For all public functions
- Keep it simple: This is for kids, not enterprise

## Questions?

- Check [MANUAL.md](MANUAL.md) for comprehensive docs
- Search existing issues on GitHub
- Open a new issue for discussion

---

Made with 💜 for curious little minds
