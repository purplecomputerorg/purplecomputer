# Linux VM Development Guide

Purple Computer requires Linux with evdev for keyboard input. This guide covers VM-specific setup for development on Mac.

---

## Quick Start

```bash
# 1. Set up the dev environment
make setup

# 2. Add yourself to the input group (required for evdev)
sudo usermod -aG input $USER
sudo reboot  # Required for group change

# 3. Run Purple Computer
make run
```

---

## VM Setup (UTM on Mac)

1. **Create VM**: Use UTM with Apple Virtualization, ARM64 guest, Ubuntu Server
2. **Install Ubuntu Server**: Minimal install is fine
3. **Install dependencies**: `sudo apt install gcc python3-dev python3-venv git`
4. **Clone repo and run `make setup`**

The virtual keyboard appears as `Apple Inc. Virtual USB Keyboard` and works with evdev.

---

## Common Issues

### "Could not find your keyboard"

You're not in the `input` group:

```bash
groups  # Should include 'input'
sudo usermod -aG input $USER
sudo reboot  # Logout isn't enough in VMs
```

### Keyboard calibration (F-keys not working)

Run calibration from Parent Mode, or manually:

```bash
python keyboard_normalizer.py --calibrate
```

---

## SSH Access for Debugging

SSH is useful when the app is frozen or the terminal is broken.

**Setup bridged networking in UTM:**
1. VM Settings → Network → "Bridged (Advanced)"
2. Interface: "Wi-Fi (en0)"
3. Install SSH: `sudo apt install openssh-server`

**From Mac:**
```bash
ssh username@vm-ip

# Kill frozen app
pkill -f purple_tui

# Check logs
cat /tmp/purple-debug.log
```

---

## Why evdev?

Purple reads keyboard directly from `/dev/input/event*`, bypassing the terminal. This gives us:
- True key up/down events (terminals only provide key press)
- Precise timing for sticky shift, long-press escape
- All keycodes (terminals drop F13-F24)

The terminal (Alacritty) is display-only. See `guides/keyboard-architecture.md` for details.

---

## Why SSH Testing Doesn't Work

SSH keystrokes come through a PTY, not evdev. Purple grabs the physical keyboard (the VM's virtual keyboard), so SSH input is ignored.

**Solution:** Use the VM console window for testing, SSH for editing code.
