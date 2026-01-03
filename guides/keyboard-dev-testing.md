# Developing and Testing Keyboard Input

How to test Purple Computer's keyboard features without flashing the golden image every time.

---

## The Architecture

Purple Computer has special keyboard handling for young typists:

| Feature | What it does |
|---------|--------------|
| Sticky shift | Tap shift, then type = capital letter (no holding two keys) |
| Double-tap | Type `a` twice quickly = `A` |
| Long-press Escape | Hold 1 second = parent mode |
| F-key remapping | F1/F2/F3 work on all laptops regardless of Fn Lock |

All of this is handled by `keyboard_normalizer.py`, which runs as a subprocess:

```
Physical Keyboard
       │
       ▼
┌──────────────────────────────────────┐
│       keyboard_normalizer.py         │
│                                      │
│  • Grabs the keyboard exclusively    │
│  • Detects tap vs hold (shift)       │
│  • Detects double-tap                │
│  • Detects long-press (escape)       │
│  • Remaps F-keys via scancodes       │
│  • Emits processed keys              │
└──────────────────────────────────────┘
       │
       ▼
Virtual Keyboard ("Purple Keyboard Normalizer")
       │
       ▼
Terminal (Alacritty)
       │
       ▼
Purple TUI (Textual)
```

**The TUI receives already-processed events.** By the time a keypress reaches the TUI, sticky shift is applied, double-tap is converted, and long-press Escape becomes F24.

---

## Why You Can't Test on Mac

keyboard_normalizer.py requires Linux evdev. It literally cannot run on macOS.

The TUI has fallback code for Mac, but it's approximate:

| Feature | On Linux | On Mac |
|---------|----------|--------|
| Key press/release | Separate events | Only "key pressed" |
| Long-press timing | Accurate | Unreliable (no key-up) |
| Sticky shift | Works perfectly | Timing is guesswork |
| Double-tap | Works perfectly | Key repeat interferes |

**Mac is fine for UI layout. Not for keyboard UX.**

---

## Why SSH Doesn't Work Either

This is the confusing part.

You might think: "I have a NixOS server running Linux. I'll SSH in and test there."

**It doesn't work.** Here's why:

```
┌─────────────────────────────────────────────────────┐
│                   NixOS Server                       │
│                                                      │
│  keyboard_normalizer.py                              │
│         │                                            │
│         ▼                                            │
│  Virtual Keyboard ──────► TTY1 (console)             │
│                              │                       │
│                              ▼                       │
│                     [nothing, no monitor]            │
│                                                      │
│  ─────────────────────────────────────────────────── │
│                                                      │
│  SSH connection ◄──────── your Mac                   │
│         │                                            │
│         ▼                                            │
│  PTY (pseudo-terminal) ──► Purple TUI                │
│                                                      │
└─────────────────────────────────────────────────────┘
```

keyboard_normalizer.py grabs the physical keyboard and emits to a virtual keyboard. That virtual keyboard's output goes to the **Linux console (TTY1)**, not to your SSH session.

Your SSH session has its own input path: keystrokes from your Mac travel over the network into a PTY. keyboard_normalizer.py never sees them.

**SSH gives you Mac keyboard behavior with extra latency.**

---

## The Solution: Linux VM with Console

Run a Linux VM on your Mac. Use the VM's console window (not SSH into the VM).

```
┌─────────────────────────────────────────────────────┐
│                   Linux VM                           │
│                                                      │
│  keyboard_normalizer.py                              │
│         │                                            │
│         ▼                                            │
│  Virtual Keyboard ──────► TTY1 (console)             │
│                              │                       │
│                              ▼                       │
│                     Purple TUI ◄─── you see this     │
│                                     in the VM window │
└─────────────────────────────────────────────────────┘
       ▲
       │
  Your Mac keyboard input goes here
  (VM captures it as if it were a physical keyboard)
```

The VM's console IS the target. keyboard_normalizer.py's output goes there. You see it in the VM window.

---

## Setting Up the VM

**One-time setup (~30 minutes):**

1. Install UTM (free, works on Apple Silicon)
2. Download Ubuntu Server or Debian minimal ISO
3. Create VM: 2GB RAM, 20GB disk
4. Install OS
5. Configure:
   ```bash
   sudo usermod -aG input $USER
   sudo apt install python3-pip python3-venv git
   ```
6. Set up shared folder or rsync for code sync
7. Snapshot the VM in this clean state

**Daily workflow:**

1. Start VM
2. Sync code (shared folder or rsync)
3. Run Purple TUI in the VM console window
4. Test keyboard: long-press Escape, sticky shift, double-tap, F-keys
5. Make changes on Mac, re-sync, restart TUI

---

## When to Use What

| Task | Where to do it |
|------|----------------|
| UI layout, colors, screen flow | Mac directly |
| Basic typing, mode switching | Mac directly |
| Long-press Escape timing | Linux VM |
| Sticky shift behavior | Linux VM |
| Double-tap behavior | Linux VM |
| F-key remapping | Linux VM |
| Final hardware validation | Golden image on real laptop |

---

## Common Mistakes

### "I'll just SSH into a Linux box"

Doesn't work. SSH input bypasses keyboard_normalizer.py. You get Mac keyboard behavior.

### "I'll attach a USB keyboard to my server"

Only works if you also have a monitor. keyboard_normalizer.py output goes to TTY1 (the console), which you can't see without a display.

### "Why can't the TUI read evdev directly?"

It could, but then you'd have two things trying to grab the keyboard. The current architecture (normalizer as subprocess) keeps concerns separated: hardware handling in one place, UI in another.

### "Can I test keyboard_normalizer.py logic without hardware?"

Yes. `KeyEventProcessor` in keyboard_normalizer.py is pure logic. Feed it synthetic events with timestamps:

```python
proc = KeyEventProcessor()

# Simulate escape press
proc.process_event(EV_KEY, KEY_ESC, 1, timestamp=0.0)

# Simulate release after 1.2 seconds
result = proc.process_event(EV_KEY, KEY_ESC, 0, timestamp=1.2)

# Should have emitted F24 (parent mode)
assert (EV_KEY, KEY_F24, 1) in result
```

See `tests/test_keyboard_normalizer.py` for examples.

---

## Files

| File | What it does |
|------|--------------|
| `keyboard_normalizer.py` | Grabs hardware keyboard, processes events, emits to virtual keyboard |
| `purple_tui/keyboard.py` | Pure-logic classes (DoubleTapDetector, ShiftState, etc.) used by normalizer |
| `tests/test_keyboard_normalizer.py` | Unit tests for keyboard logic |
| `~/.config/purple/keyboard-map.json` | Calibrated F-key scancode mapping |

---

## Summary

1. **keyboard_normalizer.py does all the hard keyboard work** (timing, long-press, sticky shift)
2. **It requires Linux evdev**, so Mac can't run it
3. **Its output goes to the Linux console**, so SSH doesn't help
4. **Use a Linux VM** and work in the console window
5. **Mac is fine for UI work**, just not keyboard UX testing
