# Keyboard Architecture Guide

How Purple Computer handles keyboard input across all laptops.

---

## The Problem

Purple Computer uses F1-F12 for mode switching. But on most modern laptops:

- **F1** sends brightness down (not KEY_F1)
- **F2** sends brightness up (not KEY_F2)
- **F3** sends mute (not KEY_F3)
- etc.

The **Fn key** toggles between media functions and F-keys, but:
1. Fn is handled at firmware level (Linux never sees it)
2. Default behavior varies by manufacturer
3. Parents don't know what "Fn Lock" means

We need F1 to always be F1, regardless of laptop brand or Fn Lock state.

---

## Why This Is Hard

### The Fn Key Is Invisible

```
Physical key press → Laptop Firmware (EC) → USB/PS2 scan code → Linux
                            ↑
                     Fn key handled HERE
                     (invisible to Linux)
```

The Embedded Controller (EC) decides what keycode to send based on Fn state. By the time Linux sees the event, the decision is already made. We cannot intercept or detect Fn.

### What Linux Sees

When you press the physical F1 key:

**With Fn Lock OFF (typical default):**
```
EV_MSC / MSC_SCAN / 0xe0  ← scancode (physical key identifier)
EV_KEY / KEY_BRIGHTNESSDOWN / 1  ← keycode (firmware's decision)
```

**With Fn Lock ON:**
```
EV_MSC / MSC_SCAN / 0x3b  ← different scancode!
EV_KEY / KEY_F1 / 1  ← keycode is now F1
```

Notice: both the scancode AND keycode change depending on Fn Lock. The firmware completely remaps the key.

---

## MSC_SCAN: Necessary But Not Sufficient

### What Is MSC_SCAN?

`MSC_SCAN` is the raw scancode that identifies which physical control fired. It arrives *before* the keycode:

```
1. EV_MSC / MSC_SCAN / <scancode>   ← "which switch moved"
2. EV_KEY / KEY_* / 1               ← "what it means" (firmware decision)
3. EV_SYN / SYN_REPORT / 0          ← sync
```

### Why Scancode Matters

Keycodes are **policy**, not fact. The firmware chooses:
- "This key is F1" → sends KEY_F1
- "This key is brightness" → sends KEY_BRIGHTNESSDOWN

Once that choice is made, the keycode contains no physical position info.

Scancodes are closer to hardware, but they're still **not physical positions**. They identify "which control on this specific keyboard," not "leftmost F-row key."

### The Hard Limit

If firmware does:
```
Physical F1 → firmware decides "brightness" → scancode 0xe0, KEY_BRIGHTNESSDOWN
```

Then Linux has **no information** that can recover "this was physically F1."

- No sysfs file
- No HID descriptor
- No evdev API
- No kernel parameter

The information simply doesn't exist. The firmware threw it away.

---

## The Solution: Calibration

Since we can't detect physical position programmatically, we ask the user once:

```
Press F1... [captures scancode 0xe0]
Press F2... [captures scancode 0xe1]
...
```

Now we have a mapping:
```json
{
  "scancodes": {
    "224": 59,   // scancode 0xe0 → KEY_F1
    "225": 60,   // scancode 0xe1 → KEY_F2
    ...
  }
}
```

This mapping is stable because:
- Same physical key = same scancode (on this keyboard)
- Fn Lock state doesn't matter after calibration
- Works regardless of what keycode firmware sends

### Why Scancode-Based, Not Keycode-Based?

If we mapped keycodes:
```
KEY_BRIGHTNESSDOWN → KEY_F1
```

This would break on laptops where F1 is mute instead of brightness. Every laptop is different.

By mapping scancodes, we capture "this physical key" regardless of what the firmware calls it.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Physical Keyboard                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Laptop Firmware (Embedded Controller)           │
│                                                              │
│  • Fn key handled here (invisible to OS)                     │
│  • Decides: F1 → brightness or F1 → KEY_F1                   │
│  • We cannot change this                                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Linux Kernel (evdev)                     │
│                                                              │
│  Receives:                                                   │
│  • EV_MSC / MSC_SCAN / <scancode>                           │
│  • EV_KEY / KEY_* / <value>                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              keyboard_normalizer.py (our code)               │
│                                                              │
│  1. Grabs hardware keyboard exclusively                      │
│  2. Captures MSC_SCAN before each KEY event                  │
│  3. Looks up scancode in calibrated mapping                  │
│  4. Remaps to correct F-key if found                         │
│  5. Handles sticky shift, Escape long-press                  │
│  6. Emits to virtual keyboard                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│            Virtual Keyboard (uinput)                         │
│            "Purple Keyboard Normalizer"                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Terminal / Textual                        │
│                    Purple Computer TUI                       │
└─────────────────────────────────────────────────────────────┘
```

---

## What We Handle

### Scancode-Based F-Key Remapping
- Captures MSC_SCAN events before KEY events
- Looks up scancode in calibrated mapping
- Remaps to correct F-key (F1-F12)
- Stored in `~/.config/purple/keyboard-map.json`

### Sticky Shift
- Tap shift quickly (<300ms) = toggle sticky shift
- Next character gets shifted
- Kids can type capitals without holding two keys

### Double-Tap Shift
- Tap same key twice quickly = shifted version
- `a` `a` → `A`
- `1` `1` → `!`
- No latency on normal typing

### Escape Long-Press
- Hold Escape >1 second = emit F24
- App catches F24 → opens parent shell
- Quick tap = normal Escape

---

## Calibration Flow

On first boot (or when `~/.config/purple/keyboard-map.json` is missing):

```
First time setup. Configuring keyboard...

Purple Computer Keyboard Setup
==========================================

Let's set up your keyboard!

Press each key when asked. Don't worry about
holding any extra keys. Just press the key shown.

Press F1... OK!
Press F2... OK!
...
Press F12... OK!

Keyboard setup complete!
```

Settings saved to `~/.config/purple/keyboard-map.json`.

---

## Design Principles

### DRY
One event loop, one mapping function, one config file.

### KISS
- No probing or auto-detection (impossible anyway)
- No vendor-specific logic
- Calibrate once, done forever

### Fail Soft
- No calibration? Keys pass through unchanged
- Unknown scancode? Key passes through unchanged
- Never block input, always do something reasonable

### Offline-First
- No network required
- No database of laptop models
- Everything local to the device

---

## Mental Model

| Concept | What It Answers |
|---------|-----------------|
| **Keycode** | "What action did firmware choose?" |
| **Scancode** | "Which switch moved?" |
| **Calibration** | "What did the human mean?" |

You can capture the first two automatically.
Only calibration gives ground truth.

---

## Files

| File | Purpose |
|------|---------|
| `keyboard_normalizer.py` | Main normalizer (grabs keyboard, remaps, emits) |
| `~/.config/purple/keyboard-map.json` | Calibrated scancode→keycode mapping |
| `purple_tui/keyboard.py` | App-side keyboard state (sticky shift, etc.) |

---

## Troubleshooting

**F-keys not working after setup:**
- Re-run calibration: `python3 /opt/purple/keyboard_normalizer.py --calibrate`
- Or delete config and reboot: `rm ~/.config/purple/keyboard-map.json`

**Calibration sees wrong keys:**
- Make sure you're pressing the top-row F-keys (above number row)
- The key labels might say brightness/volume icons. That's fine

**Normalizer not running:**
- Check if user is in `input` group: `groups`
- Check if evdev is installed: `python3 -c "import evdev"`
