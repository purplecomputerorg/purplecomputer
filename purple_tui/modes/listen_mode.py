"""
Listen Mode - Stories and Songs (Future Implementation)

A library of stories and songs for kids to listen to.
Content comes from purplepacks (stories, music packs).
"""

from textual.widgets import Static
from textual.containers import Container, Center, Middle
from textual.app import ComposeResult


class ListenModeContent(Static):
    """Coming soon message with caps support"""

    def render(self) -> str:
        caps = getattr(self.app, 'caps_text', lambda x: x)
        coming = caps("Coming soon!")
        desc = caps("Stories and songs for kids.")
        hint = caps("Press F1-F4 to try other modes")
        return (
            f"[dim]{coming}[/]\n\n"
            f"{desc}\n\n"
            f"[dim]{hint}[/]"
        )


class ListenMode(Container):
    """
    Listen Mode - Stories and songs library.

    Future implementation will include:
    - Library of kid-friendly stories (from story packs)
    - Simple songs and music (from music packs)
    - Easy navigation (next/previous)
    - Works well with "ears view" (screen off)
    """

    DEFAULT_CSS = """
    ListenMode {
        width: 100%;
        height: 100%;
        align: center middle;
        background: $surface;
    }

    #coming-soon {
        text-align: center;
        width: auto;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield ListenModeContent(id="coming-soon")
