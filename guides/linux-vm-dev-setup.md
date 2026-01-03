# Linux Development Setup Guide

Purple Computer requires Linux with evdev for proper keyboard handling. This guide covers setup on bare metal Linux or in a VM.

---

## Quick Setup

```bash
# 1. Install build dependencies
sudo apt install gcc python3-dev

# 2. Add yourself to the input group
sudo usermod -a -G input $USER

# 3. Set up uinput permissions
sudo chmod 660 /dev/uinput
sudo chown root:input /dev/uinput

# 4. Create persistent udev rule (survives reboot)
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-purple-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# 5. Log out and back in (required for group changes)

# 6. Run setup
make setup
make run
```

---

## Why These Steps?

### evdev Requirement

Purple Computer uses evdev for hardware-level keyboard access. This enables:

- **Key release detection**: Terminal input only provides key press events. evdev gives us release events too, which is essential for "hold space to draw" in paint mode.
- **F-key normalization**: Many laptops send brightness/volume instead of F1-F12 by default. The keyboard normalizer remaps physical keys via scancodes.
- **Sticky shift**: Tap shift to activate "sticky shift" for the next character (easier for kids than holding two keys).
- **Long-press escape**: Hold Escape for 1 second to open parent mode.

### Build Dependencies

evdev is a Python C extension that talks to Linux input subsystem. Building it requires:

```bash
sudo apt install gcc python3-dev
```

- `gcc`: C compiler
- `python3-dev`: Python headers for building extensions

### Input Group

The input devices at `/dev/input/event*` are owned by the `input` group:

```
crw-rw---- 1 root input 13, 65 Jan  3 02:58 /dev/input/event1
```

To read keyboard events, your user must be in this group:

```bash
sudo usermod -a -G input $USER
# Then log out and back in
```

Verify with:
```bash
groups  # Should include 'input'
```

### uinput Permissions

The keyboard normalizer creates a virtual keyboard device via `/dev/uinput`. By default, only root can write to it:

```
crw------- 1 root root 10, 223 Jan  3 02:58 /dev/uinput
```

Fix for current session:
```bash
sudo chmod 660 /dev/uinput
sudo chown root:input /dev/uinput
```

Permanent fix (survives reboot):
```bash
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-purple-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

## VM-Specific Notes

Purple Computer works in VMs (tested with UTM/QEMU on macOS). The keyboard appears as a virtual device like "Apple Inc. Virtual USB Keyboard" which is detected correctly.

If using a VM:
- Ensure the VM has a virtual keyboard device (most do by default)
- The same input group and uinput permissions are required
- Performance is generally fine for development

---

## How the Keyboard Normalizer Works

The `keyboard_normalizer.py` script:

1. **Finds the hardware keyboard** by scanning `/dev/input/event*` for devices with letter keys (A-Z)
2. **Grabs it exclusively** so events don't go to both the normalizer and the terminal
3. **Creates a virtual keyboard** via uinput named "Purple Keyboard Normalizer"
4. **Processes events** and emits them to the virtual keyboard:
   - F-key remapping via scancodes
   - Sticky shift (tap shift = shift next char)
   - Long-press Escape (1s) emits F24 for parent mode
   - Space release emits F20 for paint mode brush-up

The TUI reads from the virtual keyboard and responds to the special signals (F20, F24).

---

## Troubleshooting

### "evdev not available"

Install build dependencies and evdev:
```bash
sudo apt install gcc python3-dev
source .venv/bin/activate
pip install evdev
```

### "No input devices found"

You're not in the input group, or the group change hasn't taken effect:
```bash
sudo usermod -a -G input $USER
# Log out and back in
groups  # Verify 'input' is listed
```

### "Keyboard normalizer failed to start" (empty error)

Usually means `/dev/uinput` isn't writable:
```bash
ls -la /dev/uinput  # Check permissions
sudo chmod 660 /dev/uinput
sudo chown root:input /dev/uinput
```

### "No keyboard found"

The normalizer couldn't find a device with letter keys. Check what's available:
```bash
python -c "
import evdev
for path in evdev.list_devices():
    dev = evdev.InputDevice(path)
    print(f'{path}: {dev.name}')
"
```

### Keyboard stops working after starting Purple

The normalizer grabs the keyboard exclusively. If Purple crashes without cleanup, the keyboard may stay grabbed. Fix by unplugging/replugging a USB keyboard, or:
```bash
# Find and kill any stuck normalizer
pkill -f keyboard_normalizer
```

---

## Architecture Diagram

```
┌─────────────────────┐
│   Hardware Keyboard │
│  /dev/input/event1  │
└──────────┬──────────┘
           │ (grabbed exclusively)
           ▼
┌─────────────────────┐
│ keyboard_normalizer │
│    (Python/evdev)   │
│                     │
│ - F-key remapping   │
│ - Sticky shift      │
│ - Escape long-press │
│ - Space release     │
└──────────┬──────────┘
           │ (emits to virtual device)
           ▼
┌─────────────────────┐
│  Virtual Keyboard   │
│ "Purple Keyboard    │
│     Normalizer"     │
│   /dev/uinput       │
└──────────┬──────────┘
           │ (terminal reads this)
           ▼
┌─────────────────────┐
│   Purple TUI App    │
│     (Textual)       │
│                     │
│ Responds to:        │
│ - F1-F3: modes      │
│ - F20: space up     │
│ - F24: parent mode  │
└─────────────────────┘
```

---

## Summary

| Requirement | Why | Command |
|-------------|-----|---------|
| gcc, python3-dev | Build evdev | `sudo apt install gcc python3-dev` |
| input group | Read /dev/input/* | `sudo usermod -a -G input $USER` |
| uinput writable | Create virtual keyboard | `sudo chmod 660 /dev/uinput && sudo chown root:input /dev/uinput` |
| udev rule | Persist uinput permissions | See above |
| Re-login | Apply group changes | Log out and back in |

After setup, `make setup` and `make run` should work.
