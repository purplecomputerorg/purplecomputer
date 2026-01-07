# Keyboard Architecture v2: Direct evdev Input

This document explains why we're changing the keyboard architecture and how the new design works.

---

## The Problem with v1

### Original Architecture

```
Hardware Keyboard
       ↓
keyboard_normalizer.py (subprocess)
  - Reads evdev (sees key up/down)
  - Handles timing (sticky shift, long-press, double-tap)
  - Emits processed events to virtual keyboard
       ↓
Virtual Keyboard (uinput)
       ↓
Terminal (Alacritty)
  - Converts keycodes to escape sequences
       ↓
Textual TUI
  - Receives terminal escape sequences
  - Handles app logic
```

### Why We Thought This Would Work

keyboard_normalizer.py handles all the timing-sensitive logic. By the time events reach the TUI, they're "clean": F-keys are remapped, sticky shift is applied, long-press Escape becomes F24.

The TUI just receives simple key events and acts on them.

### The Fatal Flaw

**Terminals are lossy filters.**

Terminals convert keycodes to escape sequences. They only know a limited set of keys:

| Key | Escape Sequence | Supported |
|-----|-----------------|-----------|
| F1 | `\e[11~` or `\eOP` | Yes |
| F12 | `\e[24~` | Yes |
| F13-F19 | varies | Sometimes |
| F20-F24 | ??? | Usually dropped |

When keyboard_normalizer.py needs to signal "space was released," it emits F20. The terminal receives F20, doesn't recognize it, and drops it silently.

**The TUI never sees the signal. Space-hold painting never stops.**

This isn't a bug in Alacritty. It's how terminals work. They were designed for text, not for games or real-time input.

---

## The Solution: Bypass the Terminal

### New Architecture (v2)

```
Hardware Keyboard
       ↓
evdev (/dev/input/event*)
       ↓
TUI Process:
  ├── EvdevReader (async task)
  │     - Reads raw events from evdev
  │     - Sees key down (value=1) and key up (value=0)
  │     - Captures scancodes for F-key remapping
  │     - Emits RawKeyEvent
  │           ↓
  │   KeyboardStateMachine
  │     - Tracks pressed keys with timestamps
  │     - Detects long-press (Escape > 1s)
  │     - Handles sticky shift (tap < 300ms)
  │     - Handles double-tap (same key < 400ms)
  │     - Emits high-level actions
  │           ↓
  │   Textual App
  │     - Receives actions, updates UI
  │           ↓
  └── Alacritty (display only)
        - Renders Textual's output
        - Keyboard input ignored
```

### What Changes

| Component | Before | After |
|-----------|--------|-------|
| keyboard_normalizer.py | Subprocess, emits to uinput | Removed (logic moves into TUI) |
| Keyboard input path | evdev → uinput → terminal → TUI | evdev → TUI directly |
| Terminal role | Input + display | Display only |
| Key up/down | Lost at terminal | Preserved |
| Timing accuracy | Limited by terminal | Full precision |

### Why This Works

evdev provides:
- Separate key down (`value=1`) and key up (`value=0`) events
- Precise timestamps
- All keycodes (no filtering)
- Scancodes for hardware identification

By reading evdev directly, the TUI has full control over keyboard input. No information is lost.

---

## Design Details

### RawKeyEvent

The universal event type that the evdev reader emits:

```python
@dataclass
class RawKeyEvent:
    keycode: int        # Linux keycode (KEY_SPACE, KEY_A, etc.)
    is_down: bool       # True = press, False = release
    timestamp: float    # Monotonic time in seconds
    scancode: int = 0   # Hardware scancode (for F-key remapping)
```

### EvdevReader

Async task that reads from the keyboard device:

```python
class EvdevReader:
    async def run(self):
        async for event in device.async_read_loop():
            if event.type == EV_KEY and event.value in (0, 1):
                raw_event = RawKeyEvent(
                    keycode=event.code,
                    is_down=(event.value == 1),
                    timestamp=event.timestamp(),
                    scancode=self._pending_scancode,
                )
                await self._emit(raw_event)
```

### KeyboardStateMachine

Consumes RawKeyEvent, produces high-level actions:

```python
class KeyboardStateMachine:
    def process(self, event: RawKeyEvent) -> list[KeyboardAction]:
        # Track key state
        if event.is_down:
            self._pressed[event.keycode] = event.timestamp
        else:
            press_time = self._pressed.pop(event.keycode, None)
            if press_time:
                hold_duration = event.timestamp - press_time
                # Check for long-press, etc.
```

### Fallback for macOS

On macOS (no evdev), we fall back to Textual's on_key with approximations:

```python
class TextualInputAdapter:
    def handle_key(self, key: str) -> RawKeyEvent:
        # Convert Textual key name to keycode
        # Synthesize approximate release events
        # Return RawKeyEvent
```

This fallback is for development only. It has the same limitations as before (no true key up, unreliable timing).

---

## What Happens to keyboard_normalizer.py

The runtime normalizer functionality is absorbed into the TUI's EvdevReader and KeyboardStateMachine.

keyboard_normalizer.py is kept only for:
- `--calibrate` mode: Interactive F-key calibration that saves to `~/.config/purple/keyboard-map.json`

The TUI loads this calibration file and applies it in EvdevReader.

---

## UX Considerations

### Terminal as Display Only

With keyboard input bypassing the terminal:

| Concern | Impact |
|---------|--------|
| Character echo | None. Textual controls all display in raw mode. |
| Window resize | Still works. Alacritty notifies Textual via SIGWINCH. |
| Copy/paste | Alacritty shortcuts won't work. Not needed for kids 3-8. |
| Mouse input | Purple disables trackpad anyway. |
| Focus | In kiosk mode, only Purple runs. No focus issues. |

### Device Grabbing

When the TUI grabs the keyboard device (`EVIOCGRAB`):
- Other applications can't receive keyboard input
- This is intentional for kiosk mode
- In dev mode, grabbing can be disabled for convenience

---

## File Structure

| File | Purpose |
|------|---------|
| `purple_tui/input.py` | RawKeyEvent, EvdevReader, TextualInputAdapter |
| `purple_tui/keyboard.py` | KeyboardStateMachine (refactored from current) |
| `keyboard_normalizer.py` | Calibration mode only |
| `~/.config/purple/keyboard-map.json` | F-key scancode mapping |

---

## Summary

| Aspect | v1 (Terminal Path) | v2 (Direct evdev) |
|--------|-------------------|-------------------|
| Key up/down | Lost | Preserved |
| Timing | Approximate | Precise |
| F13-F24 | Dropped by terminal | Available |
| Space release | Cannot detect | Works |
| Long-press | Fragile | Robust |
| Architecture | Subprocess + uinput + terminal | Direct evdev read |
| Complexity | Higher (more moving parts) | Lower (fewer hops) |

The new architecture is simpler AND more capable. The terminal becomes a dumb display, which is exactly what we need for a kiosk-style kids' computer.

---

## Suspending for Terminal Access

Parent mode can open a shell for admin tasks. This requires temporarily releasing the evdev grab so the terminal receives keyboard input.

Use `app.suspend_with_terminal_input()`:

```python
with self.app.suspend_with_terminal_input():
    os.system('stty sane')
    subprocess.run(['/bin/bash', '-i'])
    os.system('stty sane')

self.app.refresh(repaint=True)
```

This context manager:
1. Releases the evdev grab
2. Calls Textual's `suspend()` to restore the terminal
3. Reacquires the grab and resets keyboard state on exit

**Important**: When flushing pending evdev events before reacquiring the grab, use `select()` with a 0 timeout to check for data before calling `read_one()`. Otherwise `read_one()` blocks forever.

**Exiting from suspend**: If you need to exit the app from inside a suspend context, use `os._exit(0)` instead of `sys.exit(0)`. The latter tries to unwind through Textual's cleanup, which can leave the terminal in a broken state.
