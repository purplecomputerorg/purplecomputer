# Claude Code Notes for Purple Computer

## Target Audience

Purple Computer is for **kids ages 3-8** and their **non-technical parents**.

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

## Writing Style

**No em-dashes or spaced dashes.** Instead of ` - ` or ` — `, use colons, commas, or periods.

Bad: `Press F1 - opens Explore mode`
Good: `Press F1: opens Explore mode` or `Press F1 to open Explore mode`

This applies to docs, comments, and UI strings.

---

## Python Environment

Always use `.venv` or Docker to access Python dependencies. The system Python won't have the required libraries.

```bash
# Local development
source .venv/bin/activate
pytest tests/ -v

# Or via Docker (on some machines)
docker compose run app pytest tests/ -v
```

Or use the Makefile shortcuts: `make test`, `make run`, `make setup`.

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

**Important:** If your widget is inside a container (like `ArtCanvas` inside `DoodleMode`), the container must delegate:

```python
class DoodleMode(Container):
    async def handle_keyboard_action(self, action) -> None:
        canvas = self.query_one("#art-canvas", ArtCanvas)
        await canvas.handle_keyboard_action(action)
```

Modal screens are automatically dispatched to when active (checked via `screen_stack`).

### Focus-Free Navigation

Textual's focus system (Tab/Shift-Tab) doesn't work with evdev since we suppress terminal events. Handle all navigation explicitly via `handle_keyboard_action()` using `NavigationAction` for arrows and `ControlAction` for Enter/Escape.

This pattern is used in:
- `PlayMode`: handles character keys for sound/color
- `ExploreMode`: handles characters, navigation, autocomplete
- `DoodleMode`: delegates to `ArtCanvas` for painting
- `ParentMenu`: tracks menu selection with up/down/enter
- `SleepScreen`: any key wakes the screen
