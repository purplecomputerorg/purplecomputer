# Keyboard Architecture: Direct evdev Input

How Purple Computer handles keyboard input by reading directly from Linux evdev.

---

## Why Direct evdev?

Terminals are lossy filters. They convert keycodes to escape sequences and drop keys they don't recognize (F13-F24). They also don't provide key release events.

By reading evdev directly, Purple gets:
- True key down/up events
- Precise timestamps for timing features
- All keycodes (no filtering)

The terminal (Alacritty) becomes display-only.

---

## Architecture

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

evdev provides separate key down (`value=1`) and key up (`value=0`) events, precise timestamps, all keycodes, and scancodes for F-key remapping.

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

### F-Key Calibration

`keyboard_normalizer.py --calibrate` prompts the user to press F1-F12 and saves scancode mappings to `~/.config/purple/keyboard-map.json`. The TUI loads this file on startup to remap F-keys correctly regardless of Fn Lock state.

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

Purple reads keyboard directly from evdev, bypassing the terminal. This gives us key up/down events, precise timing, and all keycodes. The terminal is display-only, which is exactly what we need for a kiosk-style kids' computer.

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
