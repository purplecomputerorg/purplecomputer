# Claude Code Notes for Purple Computer

## Screenshots

Screenshots are stored in `/tmp/screenshots/`. Check for recent files sorted by date (e.g. `SCR-20260306-*.png`).

---

## Sensitive Files (DO NOT READ)

Never read `tools/.env`, any `.env` files, `credentials.json`, or `secrets.yaml`.

---

## Hardware Safety (CRITICAL)

Never make changes that could cause issues on real laptop hardware for testing, debugging, or VM compatibility. Purple Computer runs on kids' laptops. Real hardware stability always takes priority. VM-specific workarounds must be safe no-ops on real devices.

---

## Target Audience

Purple Computer is for **kids 4-7** (and fun for 2-8+) and their **non-technical parents**.

User-facing messages: simple, friendly language. No jargon. Clear next steps, not error explanations. Add `(Technical: ...)` hint at end for known root causes. Use `SUPPORT_EMAIL` from `purple_tui/constants.py`.

---

## UX Change Log

When making UX changes, add a one-line description to `UX_LOG.md`.

---

## Writing Style

**No em-dashes or spaced dashes.** Use colons, commas, or periods instead of ` - ` or ` — `.

---

## Python Environment

**Use `just` commands** (pre-approved, no confirmation needed):

```bash
just test    just run    just lint    just setup    just python foo.py
```

Always `just python` instead of `.venv/bin/python`. The justfile handles venv activation.

---

## Terminal Layout Constants

**Single source of truth:** `purple_tui/constants.py` defines viewport dimensions (`VIEWPORT_WIDTH=134`, `VIEWPORT_HEIGHT=30`, `REQUIRED_TERMINAL_ROWS=38`). Font size calculation in `scripts/calc_font_size.py` imports from there. No fallbacks needed.

---

## Textual Framework Workarounds

### Background Colors (Textual 0.67.0)

`widget.styles.background` on `Static` doesn't repaint. Use `Widget` subclass with `render_line()` returning `Strip([Segment(" " * width, Style(bgcolor=color))])`. This is the pattern used throughout (MusicGrid, ArtCanvas, ColorLegend, etc.).

### Keyboard Input (evdev)

**Linux only.** Keyboard input via evdev (`/dev/input/event*`), bypassing the terminal. Alacritty is display-only. This gives true key down/up events and precise timestamps.

```
Physical Keyboard → evdev → EvdevReader → KeyboardStateMachine → handle_keyboard_action()
```

**Key files:** `purple_tui/input.py` (EvdevReader), `purple_tui/keyboard.py` (KeyboardStateMachine, action types). See `guides/keyboard-architecture.md`.

**Single code path:** All keyboard logic in `handle_keyboard_action()`. Textual's `_on_key()` must suppress events (`event.stop(); event.prevent_default()`).

**Focus-free navigation:** Textual's Tab/Shift-Tab doesn't work with evdev. All navigation is explicit via `handle_keyboard_action()`.

### HoldOrTap Pattern

`HoldOrTap` (keyboard.py) distinguishes quick taps from long holds (used for space-hold to toggle code panel). Key behavior:
- `on_down()`: starts hold timer
- `on_up()`: returns True if it was a tap (released before threshold)
- `on_other_key()`: returns True if a pending tap should be flushed before the new key

When buffering space in write mode, always check `on_other_key()` return value to flush the space before the next character (otherwise "apple banana" becomes "applebanana").

### Code Panel Architecture

**State:** `_code_panel_active` (bool on app) persists across room switches. Individual `ReplPanel.is_open` is per-room runtime state.

**Room switch behavior:** When `_code_panel_active`, switching to Music/Art auto-opens the REPL panel. Switching to Play shows compact indicator (Play is already a REPL). Mode ends only on explicit close (hold Space, "exit" command, or room picker).

**Canvas sizing:** When opening REPL via space-hold (user-initiated), the canvas/grid height is pinned to its current size. When opening via room switch, height stays at `1fr` (widget may not be laid out yet, `size.height` would be 0).

**Write mode + space buffering:** In art write mode, space-down starts the hold timer but does NOT type immediately. Space repeats are suppressed while pending. On tap (quick release), space is sent to canvas. On `on_other_key()` returning True, space is flushed before the new key.

---

## Python Gotchas

**Environment variable checks:** Always compare to `"1"`, never use truthiness (`"0"` is truthy).

**Dataclass constructors:** Check the actual definition. `NavigationAction` has `direction`, not `is_down`. `ControlAction` has `action` and `is_down`.

---

## UEFI Boot

Boot must work on diverse hardware (ThinkPads, Dells, Surface, etc.). Key principles:
- **UUID over labels** for root partition (labels aren't unique across disks)
- **Signed boot chain:** shim (Microsoft-signed) → GRUB (Canonical-signed) → kernel
- **Multiple EFI paths:** `/EFI/BOOT/`, `/EFI/Microsoft/Boot/`, `/EFI/purple/` each have shim + GRUB
- **NVRAM entries are bonus:** create them but don't depend on them
- **EFI search config** has UUID → label → file → device probe fallbacks

Device-specific fixes: comment which device, make it a fallback, keep under 10 lines. Run `build-scripts/diagnose-boot.sh` to debug.

---

## Build Image Size Reduction

Uses `--no-install-recommends`. `linux-firmware` must be installed explicitly (it's a Recommend, not a dependency).

**Kernel modules (`/lib/modules/`): DANGEROUS to prune.** Modules have invisible cross-directory dependencies (e.g. `i915` → `drm_display_helper` → `cec` in `drivers/media/`). **Only remove networking modules** (`drivers/net`, `drivers/bluetooth`, `net/bluetooth`, `net/wireless`, `drivers/nfc`, `drivers/isdn`). The build runs `modprobe --dry-run` after pruning to catch breakage.

**Firmware files (`/lib/firmware/`): Safe to prune aggressively.** Standalone blobs, no cross-dependencies. Keep only `i915/`, `amdgpu/`, `nvidia/`, `intel/` for GPU/audio.
