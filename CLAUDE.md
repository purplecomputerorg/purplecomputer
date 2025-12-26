# Claude Code Notes for Purple Computer

## Writing Style

**No em-dashes or spaced dashes.** Instead of ` - ` or ` — `, use colons, commas, or periods.

Bad: `Press F1 - opens Ask mode`
Good: `Press F1: opens Ask mode` or `Press F1 to open Ask mode`

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

### Focus-Free Keyboard Navigation

**Problem**: Textual's focus system (Tab/Shift-Tab, Button focus) is unreliable without a mouse. Focus can get "stuck" or not move as expected.

**Solution**: Handle all navigation explicitly via `on_key()`. Track selection state manually and update visual styling with CSS classes.

```python
class MyMenu(ModalScreen):
    def __init__(self):
        super().__init__()
        self._selected_index = 0

    def on_key(self, event: events.Key) -> None:
        if event.key == "up":
            event.stop()
            self._selected_index = (self._selected_index - 1) % len(ITEMS)
            self._update_selection()
        elif event.key == "down":
            event.stop()
            self._selected_index = (self._selected_index + 1) % len(ITEMS)
            self._update_selection()
        elif event.key == "enter":
            event.stop()
            self._activate_selected()

    def _update_selection(self) -> None:
        for i, item in enumerate(self.query(MenuItem)):
            if i == self._selected_index:
                item.add_class("selected")
            else:
                item.remove_class("selected")
```

This pattern is used in:
- `PlayMode`: handles grid keys directly
- `AskMode`: focuses an Input widget explicitly
- `ParentMenu`: tracks menu selection with up/down/enter
