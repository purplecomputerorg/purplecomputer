"""
Listen Mode - Stories and Songs (Future Implementation)

A library of stories and songs for kids to listen to.
Content comes from purplepacks (stories, music packs).
"""

from textual.widgets import Static
from textual.containers import Container, Center, Middle
from textual.app import ComposeResult


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
                yield Static(
                    "[bold magenta]👂 Listen Mode[/]\n\n"
                    "[dim]Coming soon![/]\n\n"
                    "This will be a library of\n"
                    "stories and songs for kids.\n\n"
                    "[dim]Press F1-F4 to try other modes[/]",
                    id="coming-soon"
                )
