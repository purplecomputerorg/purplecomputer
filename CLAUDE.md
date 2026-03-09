# Claude Code Notes for Purple Computer

## Screenshots

Screenshots are stored in `/tmp/screenshots/`. When the user references "the latest screenshot" or visual issues, check this directory for recent files (sorted by date in filename, e.g. `SCR-20260306-*.png`).

---

## Sensitive Files (DO NOT READ)

Never read or access these files:
- `tools/.env` (API keys)
- Any `.env` files
- `credentials.json`, `secrets.yaml`, or similar

---

## Hardware Safety (CRITICAL)

Never make changes that could cause issues on real laptop hardware for the sake of testing, debugging, or VM compatibility. Purple Computer runs on kids' laptops. Real hardware stability always takes priority over UTM/QEMU/VM convenience. Any VM-specific workarounds must be safe no-ops on real devices.

---

## Target Audience

Purple Computer is for **kids 4–7** (and fun for 2–8+) and their **non-technical parents**.

When writing user-facing messages (error messages, setup prompts, UI text):
- Use simple, friendly language
- Avoid technical jargon (no "evdev", "scancode", "EAGAIN", "permission denied")
- Give clear next steps, not explanations of what went wrong
- Point to help resources (GitHub issues) when something fails
- Reassure rather than alarm

**Bad:**
```
ERROR: No keyboard found. Need root or 'input' group.
No scancodes captured. Your keyboard may not report MSC_SCAN events.
```

**Good:**
```
Could not find your keyboard.
Please make sure a keyboard is connected and try again.

If this keeps happening, contact us at {SUPPORT_EMAIL}

(Technical: user not in 'input' group)
```

Use the `SUPPORT_EMAIL` constant from `purple_tui/constants.py` for consistency.

**Technical hints:** When you're confident about the root cause, add a `(Technical: ...)` line at the end. This helps support diagnose issues while keeping the main message friendly. Only include technical hints for known, specific errors (like permission denied → input group). For unknown errors, just log them and point to support.

---

## UX Change Log

When making UX changes (behavior, interaction patterns, visual feedback), add a brief one-line description to `UX_LOG.md`. Keep entries short and focus on what changed from the user's perspective.

---

## Writing Style

**No em-dashes or spaced dashes.** Instead of ` - ` or ` — `, use colons, commas, or periods.

Bad: `Press F1 - opens Play room`
Good: `Press F1: opens Play room` or `Press F1 to open Play room`

This applies to docs, comments, and UI strings.

---

## Python Environment

Always use `.venv` or Docker to access Python dependencies. The system Python won't have the required libraries.

**Prefer `just` commands** over raw shell commands. The justfile handles venv activation and environment setup automatically:

```bash
just test          # Run tests
just run           # Run locally
just lint          # Run linter
just setup         # Install dependencies
just python foo.py       # Run Python script with venv
just python -c '...'     # Run Python one-liner with venv
just               # List all available commands
```

All `just` commands are pre-approved and don't need confirmation. When a justfile recipe exists for what you need, use it instead of the raw command. **Always use `just python` instead of `.venv/bin/python` or `source .venv/bin/activate && python`.**

---

## Scripts Over Ad Hoc Commands

If a shell command or Python snippet might be useful more than once, save it as a script in `scripts/` rather than running it ad hoc. One-off commands are fine inline, but anything reusable should be a script so it can be run again easily and improved over time.

---

## Terminal Layout Constants

**Single source of truth:** `purple_tui/constants.py` defines the viewport dimensions.

```python
VIEWPORT_WIDTH = 112          # Viewport widget width
VIEWPORT_HEIGHT = 32          # Viewport widget height
REQUIRED_TERMINAL_COLS = 114  # Full UI width (viewport + border)
REQUIRED_TERMINAL_ROWS = 39   # Full UI height (viewport + border + title + footer)
```

**Font size calculation:** `scripts/calc_font_size.py` imports these constants and uses a hardcoded cell-to-point ratio for JetBrainsMono (the only font we use) to calculate the Alacritty font size. If you change viewport dimensions in `constants.py`, the font calculator automatically adjusts.

**No fallbacks:** Purple Computer always runs with `purple_tui` installed (either via pip in production or PYTHONPATH in dev). Scripts should import directly from `purple_tui.constants` without try/except fallbacks.

---

## Textual Framework Workarounds

### Background Color Updates (Textual 0.67.0)

**Problem**: Changing `widget.styles.background` on a `Static` widget does not repaint the full widget region until the terminal forces a full redraw (e.g., window loses/regains focus).

**What doesn't work**:
- `self.styles.background = color` + `self.refresh()`
- `self.styles.background = color` + `self.refresh(repaint=True)`
- CSS variables with `var()` (the `set_var()` API doesn't exist)
- Rich markup backgrounds in `render()` (only colors text background, not cell)

**Solution**: Use a custom `Widget` subclass with `render_line()` that returns `Strip` objects containing `Segment`s with explicit Rich `Style(bgcolor=...)`. This bypasses Textual's compositor entirely.

```python
from textual.widget import Widget
from textual.strip import Strip
from rich.segment import Segment
from rich.style import Style

class ColorCell(Widget):
    def __init__(self):
        super().__init__()
        self._bg_color = "#2a1845"

    def set_color(self, color: str) -> None:
        self._bg_color = color
        self.refresh()

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        style = Style(bgcolor=self._bg_color)
        return Strip([Segment(" " * width, style)])
```

This approach gives full control over every line and updates immediately on `refresh()`.

### Keyboard Input Architecture (evdev)

**Purple Computer requires Linux with evdev.** macOS is not supported.

Keyboard input is read directly from evdev (`/dev/input/event*`), bypassing the terminal entirely. The terminal (Alacritty) is display-only. This gives us:
- True key down/up events (terminals only provide key pressed)
- Precise timestamps for timing features (sticky shift, long-press)
- All keycodes (terminals drop F13-F24)

**Architecture:**
```
Physical Keyboard → evdev → EvdevReader → KeyboardStateMachine → handle_keyboard_action()
                                                                        ↓
                                                              Mode widgets / Modal screens
```

**Key files:**
- `purple_tui/input.py`: `EvdevReader`, `RawKeyEvent`, `KeyCode`
- `purple_tui/keyboard.py`: `KeyboardStateMachine`, action types (`CharacterAction`, `NavigationAction`, `ControlAction`, etc.)
- `keyboard_normalizer.py`: F-key calibration tool only (not used at runtime)

**See:** `guides/keyboard-architecture.md` for full details.

**Single Code Path:** All keyboard logic lives in `handle_keyboard_action()`. Textual's `_on_key()` handlers should suppress events (not process them) to avoid duplicate code paths. This makes testing reliable since there's only one path to test.

```python
async def _on_key(self, event: events.Key) -> None:
    """Suppress terminal key events. All input comes via evdev/handle_keyboard_action()."""
    event.stop()
    event.prevent_default()
```

### Adding Keyboard Handling to Widgets

Every mode widget and modal screen that needs keyboard input must implement `handle_keyboard_action()`:

```python
from ..keyboard import NavigationAction, ControlAction, CharacterAction

class MyMode(Container):
    async def handle_keyboard_action(self, action) -> None:
        if isinstance(action, NavigationAction):
            if action.direction == 'up':
                self._move_up()
            elif action.direction == 'down':
                self._move_down()
            return

        if isinstance(action, ControlAction) and action.is_down:
            if action.action == 'enter':
                self._activate()
            elif action.action == 'escape':
                self._cancel()
            return

        if isinstance(action, CharacterAction):
            self._type_char(action.char)
            return
```

**Important:** If your widget is inside a container (like `ArtCanvas` inside `ArtMode`), the container must delegate:

```python
class ArtMode(Container):
    async def handle_keyboard_action(self, action) -> None:
        canvas = self.query_one("#art-canvas", ArtCanvas)
        await canvas.handle_keyboard_action(action)
```

Modal screens are automatically dispatched to when active (checked via `screen_stack`).

### Focus-Free Navigation

Textual's focus system (Tab/Shift-Tab) doesn't work with evdev since we suppress terminal events. Handle all navigation explicitly via `handle_keyboard_action()` using `NavigationAction` for arrows and `ControlAction` for Enter/Escape.

This pattern is used in:
- `MusicMode`: handles character keys for sound/color
- `PlayMode`: handles characters, navigation, autocomplete
- `ArtMode`: delegates to `ArtCanvas` for painting
- `ParentMenu`: tracks menu selection with up/down/enter
- `SleepScreen`: any key wakes the screen

### Textual Uses stderr for Rendering

**Do not capture stderr when running Purple Computer as a subprocess.** Textual renders its UI to stderr, so redirecting stderr to a file will capture the entire terminal UI output, not debug messages.

For debug logging from the app, write to a file directly instead:
```python
# Bad: debug output goes to stderr (mixed with Textual rendering)
print(f"[Debug] {msg}", file=sys.stderr)

# Good: write to a dedicated log file
with open("/path/to/debug.log", "a") as f:
    f.write(f"[Debug] {msg}\n")
```

---

## Common Python Gotchas

### Environment Variable Checks

**Always compare to "1", never use truthiness.** Any non-empty string is truthy, including "0".

```python
# Bad: "0" is truthy, this runs even when disabled
if os.environ.get("PURPLE_DEMO_AUTOSTART"):
    start_demo()

# Good: explicit check
if os.environ.get("PURPLE_DEMO_AUTOSTART") == "1":
    start_demo()
```

### Local Imports Shadow Module-Level Imports

**Don't use `import X` inside a function if X is already imported at module level.** Python sees the local import and treats X as a local variable throughout the entire function, causing UnboundLocalError before the import line.

```python
import os  # module level

async def on_mount(self):
    # Bad: UnboundLocalError here because Python sees 'import os' below
    if os.environ.get("FOO"):
        pass

    import os  # This makes 'os' local to entire function!

# Good: just use the module-level import, don't re-import
async def on_mount(self):
    if os.environ.get("FOO"):
        pass
```

### Dataclass Constructor Parameters

**Check the actual dataclass definition before constructing.** Different action types have different parameters.

```python
# NavigationAction only has: direction, space_held, is_repeat, other_arrows_held
# Bad: NavigationAction doesn't have is_down
NavigationAction(direction='left', is_down=True)

# Good: check the class definition first
NavigationAction(direction='left')
```

---

## UEFI Boot and Hardware Compatibility

Purple Computer must boot reliably on diverse hardware: ThinkPads, Dell Latitudes, Microsoft Surface, consumer PCs, and other quirky UEFI implementations.

### Philosophy: Robust but Minimal

- **Accumulate small, proven fixes** that help across many devices
- **Avoid abstraction layers** for one-time operations
- **Device-specific workarounds are OK** if they're small and necessary
- **Comments over docs** for boot logic (the code IS the documentation)

### Key Boot Principles

**1. UUID over labels for root partition:**
```bash
# Bad: label search is non-deterministic if multiple disks have same label
search --no-floppy --label PURPLE_ROOT --set=root
root=LABEL=PURPLE_ROOT

# Good: UUID is unique per filesystem
search --no-floppy --fs-uuid a1b2c3d4-... --set=root
root=UUID=a1b2c3d4-...
```

**2. Signed boot chain (shim → GRUB → kernel):**
Uses Ubuntu's signed shim (Microsoft-signed) and GRUB (Canonical-signed) for Secure Boot.
Shim loads `grubx64.efi` from the same directory. Signed GRUB loads `/EFI/ubuntu/grub.cfg`.

**3. Multiple EFI paths (belt and suspenders):**
```
/EFI/BOOT/BOOTX64.EFI           # shim, UEFI spec fallback
/EFI/BOOT/grubx64.efi           # signed GRUB, loaded by shim
/EFI/Microsoft/Boot/bootmgfw.efi # shim, Surface/HP firmware bias
/EFI/Microsoft/Boot/grubx64.efi  # signed GRUB for Microsoft path
/EFI/purple/shimx64.efi          # shim, vendor path for NVRAM entry
/EFI/purple/grubx64.efi          # signed GRUB for purple path
/EFI/ubuntu/grub.cfg             # search config (signed GRUB's prefix)
```
Each directory has shim + GRUB. All signed GRUBs load `/EFI/ubuntu/grub.cfg`.

**4. NVRAM entries are bonus, not requirement:**
- Create them (helps compliant firmware)
- Don't depend on them (firmware resets them, ignores them)
- Fallback paths ensure boot even with empty NVRAM

**5. EFI search config (`/EFI/ubuntu/grub.cfg`) should have multiple search fallbacks:**
```
1. UUID search (primary, set by installer)
2. Label search (fallback for old images)
3. File search (/boot/grub/grub.cfg)
4. Device probe (hd0,gpt2, hd1,gpt2, nvme0n1p2)
```

### When Adding Device-Specific Fixes

1. Add a comment explaining which device/firmware needs it
2. Make it a fallback, not the primary path
3. Test that it doesn't break other devices
4. Keep it under 10 lines if possible

### Debugging Boot Issues

Run `build-scripts/diagnose-boot.sh` on a booted system to check:
- EFI paths present
- NVRAM entries
- UUID vs label usage
- Partition layout
