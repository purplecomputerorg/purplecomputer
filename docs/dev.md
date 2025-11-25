# Purple Computer: Developer Guide

This guide covers development, customization, and technical architecture.

## Quick Start for Development

### Prerequisites
- Ubuntu 22.04 LTS (or similar Debian-based system)
- Python 3.10+
- Git

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/purplecomputer.git
cd purplecomputer

# Install Python dependencies
pip install ipython colorama pyttsx3

# Run the REPL in development mode
./scripts/dev-run.sh
```

This runs the Purple Computer REPL in your current terminal without needing a full system install.

## Architecture Overview

### System Layers

```
┌─────────────────────────────────────┐
│         Kid Experience              │
│   (fullscreen Kitty terminal)       │
├─────────────────────────────────────┤
│       Purple REPL (IPython)         │
│  - Mode system                      │
│  - Emoji library                    │
│  - TTS integration                  │
├─────────────────────────────────────┤
│      System Services                │
│  - Auto-login (getty)               │
│  - Kiosk mode (systemd)             │
│  - X11/Wayland (minimal)            │
├─────────────────────────────────────┤
│      Ubuntu Server Base             │
└─────────────────────────────────────┘
```

### Boot Flow

1. **GRUB** → Ubuntu kernel
2. **Systemd** starts services
3. **Getty override** auto-logs in as `kiduser`
4. **Bash profile** launches X11
5. **xinitrc** starts Kitty fullscreen
6. **Kitty** runs Purple REPL (IPython)
7. **IPython** loads startup scripts and displays welcome

### Key Components

#### 1. Purple REPL (`purple_repl/`)
The main Python application that provides the kid-friendly environment.

- `repl.py`: Main entry point and REPL configuration
- `emoji_lib.py`: Emoji variable definitions and generators
- `tts.py`: Text-to-speech wrapper
- `modes/`: Different interaction modes

#### 2. Autoinstall System (`autoinstall/`)
Ubuntu autoinstall configuration for hands-off installation.

- `autoinstall.yaml`: Main config
- `build-iso.sh`: ISO creation script
- `files/`: Config files copied during installation

#### 3. System Configuration
- `systemd/kiosk.service`: Launches the kid environment on boot
- `systemd/getty-override.conf`: Auto-login configuration
- `xinit/xinitrc`: X11 startup (launches Kitty)
- `kitty/kitty.conf`: Terminal appearance and behavior

## Component Deep Dive

### The REPL System

The REPL is built on IPython with custom extensions:

```python
# purple_repl/repl.py is the entry point
# It configures IPython with:
# - Custom prompts
# - Startup message
# - Emoji preloading
# - Mode registration
# - Safety timeouts
```

Key features:
- **Input transformation**: Intercepts input to apply mode behaviors
- **Output formatting**: Colors, emojis, and visual enhancements
- **Execution guards**: Prevents infinite loops and dangerous operations

### Mode System

Modes are Python modules in `purple_repl/modes/`. Kids switch modes by typing simple words like `speech` or `emoji` (no parentheses required—IPython's autocall feature handles this).

```python
# Each mode implements:
class Mode:
    name: str
    banner: str

    def activate(self):
        """Called when entering the mode"""

    def process_input(self, text: str) -> str:
        """Transform input before execution"""

    def process_output(self, result) -> str:
        """Transform output before display"""
```

Mode switching functions are registered in `autoinstall/files/ipython/mode_manager.py` and made available globally.

To add a new mode:
1. Create `purple_repl/modes/yourmode.py`
2. Add a switching function in `mode_manager.py`
3. Update the welcome message if desired

### TTS Integration

Text-to-speech uses Piper (preferred) or pyttsx3 (fallback):

```python
# purple_repl/tts.py
# Provides a simple interface:
speak(text)          # Speak text aloud
set_voice(voice_id)  # Change voice
set_rate(speed)      # Adjust speech speed
```

Piper provides high-quality offline synthesis. If not available, the system falls back to pyttsx3/espeak.

### Emoji Library

The emoji library (`emoji_lib.py`) provides:
- Preloaded emoji variables (`cat`, `dog`, `star`, etc.)
- Pattern generators (`repeat()`, `rainbow()`, `grid()`)
- Emoji search and discovery

## Safety Mechanisms

### Execution Timeout
Long-running code is automatically interrupted after 5 seconds:

```python
# Implemented via signal.alarm() in repl.py
signal.alarm(5)
try:
    exec(code)
finally:
    signal.alarm(0)
```

### Input Sanitization
Dangerous operations are blocked:
- System commands (`os.system`, `subprocess`)
- File operations outside safe directories
- Network access
- Imports of unsafe modules

### Keyboard Restrictions
In kiosk mode, certain key combinations are disabled:
- Ctrl+Alt+F1-F12 (TTY switching)
- Ctrl+C (handled gracefully in REPL)
- Alt+F4 (no window manager to close)

The parent escape (Ctrl+Alt+P) is the only way out.

## Testing

### Unit Tests
```bash
python -m pytest purple_repl/tests/
```

### REPL Testing
```bash
# Run in development mode
./scripts/dev-run.sh

# Test specific features
python -c "from purple_repl import emoji_lib; print(emoji_lib.cat)"
```

### ISO Testing
```bash
# Build and test in QEMU
./scripts/test-iso.sh
```

## Customization

### Changing Colors
Edit `autoinstall/files/kitty/kitty.conf`:

```conf
background #800080  # Purple background
foreground #ffffff  # White text
```

### Adding Emoji
Edit `purple_repl/emoji_lib.py`:

```python
# Add new emoji variables
rocket = "🚀"
pizza = "🍕"
```

### Creating New Modes
See `purple_repl/modes/` for examples. Copy an existing mode and modify.

### Adjusting Speech
Edit `purple_repl/tts.py` to change voice, speed, or synthesis engine.

## Building the ISO

See [autoinstall.md](autoinstall.md) for detailed ISO build instructions.

Quick version:
```bash
cd autoinstall
./build-iso.sh
```

This creates `purple-computer.iso` ready to burn to USB.

## System Installation Structure

After installation, the system looks like:

```
/home/kiduser/
  .purple/              # Purple Computer files
    repl.py
    emoji_lib.py
    tts.py
    modes/
  .config/
    kitty/
      kitty.conf
  .xinitrc             # Starts Kitty on login

/etc/systemd/system/
  getty@tty1.service.d/
    override.conf      # Auto-login config

/usr/share/purple/    # System-wide Purple files
  backgrounds/
  sounds/
```

## Debugging

### Check if REPL is running
```bash
ps aux | grep ipython
```

### View systemd logs
```bash
journalctl -u getty@tty1
```

### Check X11
```bash
echo $DISPLAY
xrandr  # Show display info
```

### Test TTS manually
```bash
python3 -c "from purple_repl.tts import speak; speak('hello')"
```

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

### Code Style
- Follow PEP 8 for Python
- Use type hints where helpful
- Comment complex logic
- Keep functions small and focused

### Commit Messages
- Use clear, descriptive messages
- Reference issues where applicable
- Explain the "why" not just the "what"

## Future Enhancements

Potential additions:
- More modes (music, drawing with ASCII art, simple games)
- Multilingual support
- Voice input (speech recognition)
- Customizable themes
- Parent dashboard for activity logging
- Network-free educational content

## Resources

- [IPython Documentation](https://ipython.readthedocs.io/)
- [Kitty Terminal](https://sw.kovidgoyal.net/kitty/)
- [Piper TTS](https://github.com/rhasspy/piper)
- [Ubuntu Autoinstall](https://ubuntu.com/server/docs/install/autoinstall)
- [Systemd Service Files](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

## License

Purple Computer is MIT licensed. See [LICENSE](../LICENSE) for details.

---

Happy hacking! 💜
