# Claude Code Notes for Purple Computer

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
