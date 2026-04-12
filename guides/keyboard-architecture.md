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
Hardware Keyboard  (built-in laptop, USB, Apple SPI, ...)
       ↓
Kernel input driver  (atkbd / usbhid / applespi / ...)
       ↓
evdev (/dev/input/event*)  ← may be multiple devices
       ↓
keyd  (systemd service, golden image only)
  - EVIOCGRAB on every matching physical keyboard
  - Re-emits through /dev/input/event* for "keyd virtual keyboard"
  - Applies /etc/keyd/default.conf remaps (grave→esc, rightalt→f2)
       ↓
evdev (keyd virtual keyboard)
       ↓
TUI Process:
  ├── EvdevReader (one async task per device)
  │     - Prefers keyd virtual device when present
  │     - Still opens any physical keyboards keyd did not grab
  │     - Reads raw events, captures scancodes per device
  │     - Emits RawKeyEvent from whichever device fires
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

evdev provides separate key down (`value=1`) and key up (`value=0`) events, precise timestamps, all keycodes, and scancodes for F-key remapping. keyd is a kernel-adjacent keymap daemon that sits between the physical devices and Purple so remaps apply even before Purple starts; see [Remap Layer Choice](#remap-layer-choice) below for why this specific tool.

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

Finds all real keyboard devices and reads from all of them concurrently. Some laptops expose two keyboard input devices, and which one delivers events can change when USB devices are added/removed.

```python
class EvdevReader:
    # _find_keyboards() returns ALL real keyboards (strict + loose fallback)
    # One async task per device, events delivered from any of them

    async def _read_loop(self, device):
        async for event in device.async_read_loop():
            if event.type == EV_KEY and event.value in (0, 1, 2):
                raw_event = RawKeyEvent(
                    keycode=event.code,
                    is_down=(event.value in (1, 2)),
                    timestamp=event.timestamp(),
                    scancode=self._pending_scancodes.pop(dev_path, 0),
                )
                await self._callback(raw_event)
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
| Copy/paste | Alacritty shortcuts won't work. Not needed for kids 2–8+. |
| Mouse input | Purple disables trackpad anyway. |
| Focus | In kiosk mode, only Purple runs. No focus issues. |

### Device Grabbing

The TUI grabs all keyboard devices (`EVIOCGRAB`):
- Other applications can't receive keyboard input
- This is intentional for kiosk mode
- In dev mode, grabbing can be disabled for convenience
- All grabs are released before shutdown to avoid blocking systemd

---

## Remap Layer Choice

Purple needs two system-level keyboard remaps:

1. **grave/tilde → Escape** — top-left corner key is easier for pre-readers than reaching for Esc, and this needs to work at rescue shells and during Purple startup, not only after the app starts.
2. **RightAlt → F2** — laptops without physical F-keys (2016–2017 Touch Bar MacBooks) cannot type `Ctrl+Alt+F2` to reach tty2. Remapping a real key to F2 restores the standard VT-switch chord.

Both are "system-level" in the sense that we want them to apply *regardless of which process is reading the keyboard*: Purple, a getty, the tty2 debug shell, early systemd, all of them.

There are three real options for doing this on Linux. We tried to pick the most upstream, most distro-standard one — but Apple hardware forces our hand.

### Option A — Python-side remap in `KeyboardStateMachine`

What we did before this architecture. Inside Purple's Python, translate `KEY_GRAVE` / `KEY_102ND` to `KEY_ESC` before the state machine sees the event.

- Pros: zero system surface, zero new packages, works on every evdev device Purple can see.
- Cons: only works *while Purple is running*. Boot hangs, crashes, and rescue shells have no remap. Does nothing for the Touch Bar F2 problem because Purple isn't the process that handles `Ctrl+Alt+F2` — the kernel's VT switch layer is.

Rejected because it doesn't solve the Touch Bar F2 case and doesn't help during hangs.

### Option B — systemd-hwdb (the "most upstream" option)

`systemd-udev` ships a hardware database at `/etc/udev/hwdb.d/*.hwdb` that patches the kernel's scancode→keycode translation table. Example entry:

```
# atkbd (built-in laptop keyboard)
evdev:atkbd:dmi:*
 KEYBOARD_KEY_29=esc         # grave scancode → esc keycode
 KEYBOARD_KEY_64=f2          # rightalt scancode → f2 keycode
```

One stanza per bus type (atkbd, USB HID, etc.). Run `systemd-hwdb update && udevadm trigger --subsystem-match=input` and the kernel itself starts emitting `KEY_ESC` for the grave key. No userspace daemon at all. Available on every systemd Linux since forever.

- Pros: kernel-level (literally the deepest layer), zero packages to install, zero daemons, zero build complexity, THE canonical way to remap keys on Linux.
- Cons: **does not work on Apple SPI keyboards in Touch Bar MacBooks.** See below.

### Why hwdb is off the table despite being the "right" answer

`systemd-hwdb` only works on drivers that use the kernel's generic scancode-to-keycode translation path — i.e. drivers that call `input_set_keycode()` or `sparse_keymap_setup()` to register a keymap with the input subsystem. hwdb entries patch *that* table. atkbd, usbhid, and most sane keyboard drivers do this.

`applespi` — the kernel driver for Apple SPI keyboards in MacBook Pro 2016/2017 Touch Bar models (`drivers/input/keyboard/applespi.c` in mainline) — **does not.** It has its own hardcoded scancode-to-keycode table (`applespi_scancodes[]`) inside the driver, and calls `input_report_key()` directly with already-translated `KEY_*` constants. There is no `input_set_keycode` call, no `sparse_keymap_setup` registration, no `dev->setkeycode` function pointer. The generic keymap layer has nothing to patch. **hwdb entries for this driver have zero effect.**

Remapping the Apple SPI keyboard via hwdb would require modifying the kernel driver source and rebuilding the kernel. Not acceptable for an appliance that must run on any laptop.

The customer case that triggered all of this — installs and boot hangs on a 2016 Touch Bar MacBook — is exactly the hardware hwdb cannot remap. So hwdb is out.

Verified 2026-04 against `drivers/input/keyboard/applespi.c` at mainline `torvalds/linux` master. Revisit if `applespi` ever gains `input_set_keycode()` / `sparse_keymap_setup()` registration — hwdb would then become viable and keyd could be removed.

### Option C — keyd (what we ship)

[keyd](https://github.com/rvaiya/keyd) is a small C daemon that:

1. Grabs every matching physical keyboard via `EVIOCGRAB` (no other reader gets their events).
2. Reads `KEY_*` events from them.
3. Applies user-defined remaps.
4. Re-emits the remapped events through a single `uinput` virtual device named `keyd virtual keyboard`.

Because keyd reads and re-emits at the evdev layer — *after* whatever driver-specific translation has happened — it is driver-agnostic. atkbd, usbhid, applespi, anything that reports `KEY_*` through the input subsystem gets remapped identically. The Touch Bar MacBook's applespi driver emits `KEY_GRAVE`, keyd sees it, keyd remaps it to `KEY_ESC`, keyd writes `KEY_ESC` to the uinput device, Purple reads `KEY_ESC`. Done.

- Pros: works on every evdev device including Apple SPI. Config uses keycode names, not per-bus scancodes, so one config block handles all keyboards. Remap applies system-wide, including before Purple starts.
- Cons: not packaged in Ubuntu 24.04 LTS (landed in 24.10). We build it from source in the chroot during the golden-image build (see `build-scripts/00-build-golden-image.sh`). When we move off 24.04 LTS the source-build goes away and we can switch to `apt-get install keyd`.
- The upstream keyd Makefile gates its systemd-unit install on `/run/systemd/system` existing, which doesn't hold inside a build chroot. Pass `FORCE_SYSTEMD=1 PREFIX=/usr` on `make install` or the unit file is silently skipped. Comment in the build script documents this.

### Decision matrix

| Criterion | Python-side | hwdb | keyd |
|---|---|---|---|
| In Ubuntu 24.04 LTS as a package | n/a | yes (systemd) | no (build from source) |
| Works on atkbd + USB HID | yes | yes | yes |
| Works on Apple SPI (Touch Bar) | yes | **no** | yes |
| Works before Purple starts | no | yes | yes |
| Rescue shell / getty coverage | no | yes | yes |
| Architectural depth | userspace app | kernel scancode table | userspace daemon at evdev |
| Config style | Python code | per-bus scancodes | keyname |
| New build surface | none | none | source build in chroot |

keyd is the only option that satisfies every row *and* covers Apple Touch Bar. We pay the source-build cost.

### How Purple cooperates with keyd

`purple_tui/input.py:_find_keyboards()` has one keyd-specific behavior: when `/etc/keyd/default.conf` exists, it polls briefly (up to `KEYD_WAIT_SECS = 2.0`) for the `keyd virtual keyboard` device to appear before scanning. This closes a startup race: `purple-x11.service` has `After=keyd.service`, but `keyd.service` is `Type=simple` so systemd considers it "started" the moment its main process forks — *before* keyd has enumerated inputs and created its uinput device. Without the poll, Purple can scan past keyd's startup, pick up a physical keyboard, and then have keyd grab it a moment later, leaving Purple with a silent keyboard.

The scan itself is not keyd-specific. The existing strict/loose predicates match keyd's virtual device the same way they match any real keyboard. Both the virtual device *and* any physical keyboards keyd did not grab end up in the returned list. This matters because keyd may successfully create its virtual device but fail to grab some exotic physical keyboard — in that case we still need to read from the physical. Grabbed physicals emit no events, so there is never a "double key press" from having both in the list.

On dev machines and VMs without `/etc/keyd/default.conf`, the poll is skipped entirely and the scan behaves exactly as before keyd existed. Dev startup cost is zero.

See also: `config/keyd/default.conf` for the actual remap config, `build-scripts/00-build-golden-image.sh` for the source-build, and `guides/boot-hang-debugging.md` for how this interacts with boot-time debugging.

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
