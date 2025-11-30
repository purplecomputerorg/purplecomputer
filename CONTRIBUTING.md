# About Purple Computer

> **⚠️ IMPORTANT: This is NOT Open Source**
>
> Purple Computer is **source-available** software with all rights reserved.
> **DO NOT FORK THIS REPOSITORY.**
> Viewing and personal use are permitted. Everything else requires written permission.

## License

This project is licensed under the **Purple Computer Source-Available License 1.0**. See [LICENSE](LICENSE) for full details.

### What You Can Do

You are permitted to:
- Download and view the source code (`git clone` for viewing/testing)
- Run the software for personal, private use
- Learn from the code for educational purposes
- Report bugs via GitHub issues
- Suggest features via GitHub issues

### What You CANNOT Do (Without Written Permission)

**Strictly prohibited:**
- **Fork this repository** (including GitHub forks)
- Modify or create derivative works
- Redistribute or publish the code or modified versions
- Create plugins, add-ons, or extensions
- Submit pull requests from forked repositories
- Use the software commercially
- Host or deploy the software as a service
- Distribute binaries or packaged versions
- Use Purple Computer trademarks or branding

## Requesting Permission

If you would like to contribute, create extensions, or use Purple Computer in ways not covered by the personal-use license, please contact Purple Computer in writing to request permission.

### For Bug Reports and Feature Requests

We welcome:
- Bug reports via GitHub issues
- Feature suggestions via GitHub issues
- Documentation corrections (submit as issues for review)

## Development Reference

For those with permission to modify the code, here's the development workflow:

### Quick Setup

```bash
git clone https://github.com/purplecomputerorg/purplecomputer.git
cd purplecomputer
make setup
make run
```

See [README.md](README.md#quick-start) for details.

### Testing Modes

- **Local** (fast iteration) - `make run`
- **Docker** (Ubuntu simulation) - `make run-docker`
- **VM** (full UI testing) - See [MANUAL.md](MANUAL.md#vm-testing-reproducible-environment)
- **Hardware** (production testing) - Build ISO

See [MANUAL.md - Development & Testing](MANUAL.md#development--testing) for full comparison.

### Code Structure

- **Core REPL**: `purple_repl/`
- **Packs**: `packs/`
- **Docs**: `README.md`, `MANUAL.md`, `CHANGELOG.md`

### Pack System

Packs are Purple Computer's extension system. See [MANUAL.md - Pack System](MANUAL.md#pack-system) for complete documentation.

### Code Style

- Python: Follow PEP 8, use descriptive names
- Comments: Explain why, not what
- Docstrings: For all public functions
- Keep it simple: This is for kids, not enterprise

## Questions?

- Check [MANUAL.md](MANUAL.md) for comprehensive docs
- Search existing issues on GitHub
- Open a new issue for discussion

---

**Note:** This is source-available software. Viewing and running for personal use is permitted. All other uses require written permission from Purple Computer.
