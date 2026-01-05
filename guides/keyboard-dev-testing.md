# Developing and Testing Keyboard Input

How to test Purple Computer's keyboard features without flashing the golden image every time.

---

## The Architecture

Purple Computer reads keyboard input directly from Linux evdev, bypassing the terminal. The terminal (Alacritty) is display-only.

```
Physical Keyboard
       │
       ▼ evdev (/dev/input/event*)
       │
┌──────────────────────────────────────┐
│         Purple TUI Process           │
│                                      │
│  EvdevReader (async)                 │
│       │ RawKeyEvent                  │
│       ▼                              │
│  KeyboardStateMachine                │
│       │ KeyAction                    │
│       ▼                              │
│  Mode Widgets (Ask, Play, Write)     │
│       │                              │
│       ▼                              │
│  Textual UI ──────► Alacritty        │
│                     (display only)   │
└──────────────────────────────────────┘
```

This architecture gives us:
- True key down/up events (not just key pressed)
- Precise timestamps for timing features
- All keycodes (no terminal filtering of F13-F24)
- Reliable space-hold detection for paint mode

See `guides/keyboard-architecture-v2.md` for the full design rationale.

---

## Keyboard Features

| Feature | What it does | How it works |
|---------|--------------|--------------|
| Sticky shift | Tap shift, then type = capital letter | KeyboardStateMachine detects quick tap |
| Double-tap | Type `a` twice quickly = `A` | DoubleTapDetector tracks timing |
| Long-press Escape | Hold 1 second = parent mode | KeyboardStateMachine tracks press duration |
| Space-hold paint | Hold space + arrows = draw lines | True key release via evdev |
| F-key remapping | F1-F3 work on all laptops | Scancode calibration via keyboard_normalizer.py |

---

## Why You Can't Test on Mac

Purple Computer requires Linux with evdev. It literally cannot run on macOS.

The app will fail at startup with a clear error:

```
Purple Computer cannot start:
evdev not available. Purple Computer requires Linux with python-evdev.
```

**macOS is not supported at all.** Not even for UI development. You need a Linux environment.

---

## Why SSH Doesn't Work

You might think: "I have a Linux server. I'll SSH in and test there."

**It doesn't work.** Here's why:

```
┌─────────────────────────────────────────────────────┐
│                   Linux Server                       │
│                                                      │
│  EvdevReader tries to grab /dev/input/event*         │
│       │                                              │
│       ▼                                              │
│  Physical keyboard (attached to server)              │
│       │                                              │
│  BUT your keystrokes come from SSH, not evdev!       │
│                                                      │
│  ─────────────────────────────────────────────────── │
│                                                      │
│  SSH connection ◄──────── your Mac                   │
│       │                                              │
│       ▼                                              │
│  PTY (pseudo-terminal) ──► Textual on_key            │
│                            (which is suppressed)     │
└─────────────────────────────────────────────────────┘
```

The EvdevReader grabs the physical keyboard attached to the server. Your SSH keystrokes come through a PTY, which evdev doesn't see. And we suppress terminal keyboard events since we expect evdev input.

**SSH simply won't work for testing.**

---

## The Solution: Linux VM with Console

Run a Linux VM on your Mac. Use the VM's console window (not SSH into the VM).

```
┌─────────────────────────────────────────────────────┐
│                   Linux VM                           │
│                                                      │
│  EvdevReader                                         │
│       │                                              │
│       ▼                                              │
│  Virtual Keyboard ──► /dev/input/by-id/*-kbd         │
│                                                      │
│  Purple TUI ◄─── you see this in the VM window       │
└─────────────────────────────────────────────────────┘
       ▲
       │
  Your Mac keyboard input goes here
  (VM captures it as if it were a physical keyboard)
```

The VM presents your Mac keyboard as a virtual evdev device. Purple reads from that device. You see the output in the VM window.

---

## Setting Up the VM

**One-time setup (~30 minutes):**

1. Install UTM (free, works on Apple Silicon)

2. Download Ubuntu Server ARM64 ISO (not x86)

3. Create VM in UTM:
   - Enable "Apple Virtualization" (checked)
   - Do NOT enable Rosetta
   - Do NOT emulate x86
   - Guest architecture: ARM64 (aarch64)
   - RAM: 2-4 GB (2 GB is sufficient)
   - Disk: 16 GB
   - Display output enabled

4. Install Ubuntu Server:
   - Minimized install is fine
   - Enable OpenSSH (for setup/editing only)

5. Configure:
   ```bash
   sudo usermod -aG input $USER
   sudo apt install python3-pip python3-venv git evtest
   # Log out and back in for group change to take effect
   ```

6. Verify evdev works:
   ```bash
   # Check architecture
   uname -m  # should show: aarch64

   # Check evdev devices exist
   ls /dev/input/by-id/
   # Should see something like:
   # usb-Apple_Inc._Virtual_USB_Keyboard-event-kbd

   # Test keyboard events (Ctrl+C to exit)
   evtest /dev/input/by-id/usb-Apple_Inc._Virtual_USB_Keyboard-event-kbd
   ```

7. Set up shared folder or rsync for code sync

8. Snapshot the VM in this clean state

**What evtest output looks like:**

```
Event: time 1234.567890, type 1 (EV_KEY), code 30 (KEY_A), value 1   ← key down
Event: time 1234.567890, type 0 (EV_SYN), code 0 (SYN_REPORT), value 0
Event: time 1234.667890, type 1 (EV_KEY), code 30 (KEY_A), value 2   ← repeat
Event: time 1234.767890, type 1 (EV_KEY), code 30 (KEY_A), value 2   ← repeat
Event: time 1234.867890, type 1 (EV_KEY), code 30 (KEY_A), value 0   ← key up
```

- `value=1`: key down
- `value=0`: key up
- `value=2`: auto-repeat (ignored)

**Daily workflow:**

1. Start VM
2. Sync code (shared folder or rsync)
3. Run Purple TUI in the **VM console window** (not SSH)
4. Test keyboard: long-press Escape, sticky shift, double-tap, space-hold
5. Make changes on Mac, re-sync, restart TUI

**Important:** Use SSH for editing code and git operations. Use the VM console window for running and testing Purple Computer.

---

## F-Key Calibration

Different laptops send different scancodes for F-keys. To calibrate:

```bash
python keyboard_normalizer.py --calibrate
```

This prompts you to press F1-F12 and saves the scancode mapping to `~/.config/purple/keyboard-map.json`. The Purple TUI loads this file on startup.

---

## Files

| File | What it does |
|------|--------------|
| `purple_tui/input.py` | EvdevReader, RawKeyEvent: direct keyboard reading |
| `purple_tui/keyboard.py` | KeyboardStateMachine, action types, timing logic |
| `keyboard_normalizer.py` | F-key calibration tool only (not used at runtime) |
| `~/.config/purple/keyboard-map.json` | Calibrated F-key scancode mapping |

---

## Testing Keyboard Logic Without Hardware

The `KeyboardStateMachine` in keyboard.py is pure logic. You can test it with synthetic events:

```python
from purple_tui.input import RawKeyEvent, KeyCode
from purple_tui.keyboard import KeyboardStateMachine, ModeAction

sm = KeyboardStateMachine()

# Simulate escape press
actions = sm.process(RawKeyEvent(
    keycode=KeyCode.KEY_ESC,
    is_down=True,
    timestamp=0.0
))

# Simulate release after 1.2 seconds
actions = sm.process(RawKeyEvent(
    keycode=KeyCode.KEY_ESC,
    is_down=False,
    timestamp=1.2
))

# Should have triggered parent mode
assert any(isinstance(a, ModeAction) and a.mode == 'parent' for a in actions)
```

---

## Summary

1. **Purple reads keyboard directly from evdev**, bypassing the terminal
2. **Requires Linux with evdev**, so Mac can't run it at all
3. **SSH doesn't work** because evdev reads physical keyboard, not PTY
4. **Use a Linux VM** and work in the console window
5. **F-key calibration** is a separate tool (keyboard_normalizer.py --calibrate)

---

## Related Guides

- **[Keyboard Architecture v2](keyboard-architecture-v2.md)**: Full design rationale for direct evdev input
- **[Linux VM Dev Setup](linux-vm-dev-setup.md)**: Complete guide to setting up Ubuntu + Xorg + Alacritty in a VM
