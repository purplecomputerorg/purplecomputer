# The evdev-Terminal Gap: F-Key Signal Problem

This document describes an architectural issue discovered while implementing space-hold-to-paint in write mode.

---

## The Problem

**Goal:** Detect when space key is released so painting stops.

**Constraint:** Terminals only provide key press events, not key release events.

**Solution attempt:** Use the keyboard_normalizer (which reads evdev and DOES see key release) to emit a signal key (F20 or F23) when space is released.

**Result:** The signal is emitted but never received by the TUI.

---

## Architecture Diagram

```
┌─────────────────────┐
│   Hardware Keyboard │
│  /dev/input/event1  │
└──────────┬──────────┘
           │ evdev (has press AND release)
           ▼
┌─────────────────────┐
│ keyboard_normalizer │
│                     │
│ Sees: KEY_SPACE     │
│       value=1 (down)│
│       value=0 (up)  │  ← WE HAVE RELEASE INFO HERE
│                     │
│ Emits: F20 on       │
│        space release│
└──────────┬──────────┘
           │ uinput virtual keyboard
           ▼
┌─────────────────────┐
│      Terminal       │
│     (Alacritty)     │
│                     │
│ Converts keycodes   │
│ to escape sequences │
│                     │
│ F1-F12: ✓ supported │
│ F13-F24: ✗ UNKNOWN  │  ← SIGNAL LOST HERE
└──────────┬──────────┘
           │ escape sequences only
           ▼
┌─────────────────────┐
│   Textual (TUI)     │
│                     │
│ Receives: "f1"-"f12"│
│ Never sees: "f20"   │  ← NEVER ARRIVES
└─────────────────────┘
```

---

## What We Tried

### Attempt 1: F23 (keycode 193)

```python
# keyboard_normalizer.py
if code == KeyCodes.KEY_SPACE and value == 0:
    return [
        (KeyCodes.EV_KEY, KeyCodes.KEY_SPACE, 0),
        (KeyCodes.EV_KEY, KeyCodes.KEY_F23, 1),
        (KeyCodes.EV_KEY, KeyCodes.KEY_F23, 0),
    ]
```

```python
# write_mode.py
if key == "f23":
    self._release_space_down()
```

**Result:** Normalizer logs show F23 emitted. TUI never receives `key="f23"`.

### Attempt 2: F20 (keycode 191)

Same approach with F20 instead of F23, hoping F20 has better terminal support.

**Result:** Same. Normalizer emits F20, TUI never sees it.

### Debug Log Evidence

```
[NORMALIZER] Space released, emitting F20     ← Normalizer emits
[WRITE_MODE] Arrow with space_down, painting  ← TUI still painting
[WRITE_MODE] Arrow with space_down, painting  ← No F20 received
[WRITE_MODE] Arrow with space_down, painting
[NORMALIZER] Space released, emitting F20     ← Another release
[WRITE_MODE] Arrow with space_down, painting  ← Still no F20
```

Notice: There are NO `[WRITE_MODE] key='f20'` entries. The terminal is not passing F20 through.

---

## Root Cause

### Terminal Escape Sequences

Terminals convert keycodes to escape sequences. Standard mappings:

| Key | Keycode | Escape Sequence | Supported |
|-----|---------|-----------------|-----------|
| F1 | 59 | `\e[11~` or `\eOP` | ✓ |
| F12 | 88 | `\e[24~` | ✓ |
| F13 | 183 | `\e[25~` | Sometimes |
| F20 | 191 | ??? | Usually not |
| F23 | 193 | ??? | Usually not |
| F24 | 194 | `\e[42~` | Sometimes |

High F-keys (F13-F24) have inconsistent or no terminal support. Most terminals simply drop these keys.

### Why This Architecture Exists

The current architecture evolved from:

1. **Textual requirement:** Textual is a terminal UI framework. It expects terminal input.
2. **evdev requirement:** We need key release detection for space-hold painting.
3. **Compromise:** Normalizer handles evdev, emits to virtual keyboard, terminal reads that.

The flaw: we assumed the terminal would pass through all keys. It doesn't.

---

## Possible Solutions

### Option A: Direct evdev Reader in TUI

Add a background thread that reads F20 directly from the normalizer's virtual keyboard via evdev, bypassing the terminal entirely for this specific signal.

```python
class F20Monitor:
    """Reads F20 directly from evdev, bypasses terminal."""

    def _monitor_loop(self):
        device = find_normalizer_device()
        for event in device.read_loop():
            if event.code == KEY_F20 and event.value == 1:
                self._callback()  # Release space
```

**Pros:** Works, minimal changes
**Cons:** Mixing two input sources (terminal + direct evdev), complexity

### Option B: Full evdev Keyboard Backend

Replace Textual's keyboard handling entirely. Read ALL keys from evdev, translate to Textual events manually.

```
Hardware → Normalizer → Virtual KB → TUI reads via evdev → Injects into Textual
                                           ↑
                                    Bypass terminal completely
```

**Pros:** Clean, consistent, full control
**Cons:** Significant refactoring, must handle all key translation

### Option C: IPC Instead of F-Keys

Have normalizer write to a file/socket when space is released. TUI reads from that.

```python
# keyboard_normalizer.py
if code == KeyCodes.KEY_SPACE and value == 0:
    with open("/tmp/purple-space-state", "w") as f:
        f.write("up")

# write_mode.py (polling or inotify)
if read_space_state() == "up":
    self._release_space_down()
```

**Pros:** No terminal involvement
**Cons:** Latency, complexity, file/socket management

### Option D: Use a Recognized Key Combo

Emit a key combination the terminal DOES recognize, like `Ctrl+Shift+Space` or a specific character.

**Pros:** Uses existing terminal path
**Cons:** May conflict with other uses, limited options

---

## Current Status

The F20Monitor approach (Option A) was partially implemented but not completed. The code exists in `write_mode.py` but is not yet integrated into the ArtCanvas lifecycle.

Key files:
- `keyboard_normalizer.py`: Emits F20 on space release (working)
- `write_mode.py`: Has F20Monitor class (not started/integrated)
- `/tmp/purple-debug.log`: Debug output showing the gap

---

## Recommendation

**Short term:** Complete Option A (F20Monitor). It's a targeted fix that works.

**Long term:** Consider Option B (full evdev backend) for a cleaner architecture where all keyboard input flows through evdev, making the terminal purely a display mechanism.

The fundamental insight: **terminals are not designed to pass all keyboard events**. Any solution that relies on the terminal to relay special keys will hit this limitation.

---

## Testing the Gap

To verify the gap still exists:

```bash
# 1. Clear log
echo "=== Test ===" > /tmp/purple-debug.log

# 2. Run Purple, go to F3 mode, enter paint mode (Tab)

# 3. Press and release space, press arrows

# 4. Exit and check log
cat /tmp/purple-debug.log
```

You should see:
- `[NORMALIZER] Space released, emitting F20` (normalizer works)
- `[WRITE_MODE] key='space'` (TUI sees space press)
- NO `[WRITE_MODE] key='f20'` (TUI never sees F20)
- `[WRITE_MODE] Arrow with space_down, painting` (painting continues after release)
