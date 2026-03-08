#!/usr/bin/env python3
"""Minimal test: does border render on all 4 sides inside a Horizontal?"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static


class TestApp(App):
    CSS = """
    Screen {
        background: #1e1033;
    }

    #outer {
        width: 100%;
        height: 100%;
        align: center middle;
        background: #1e1033;
    }

    #wrapper {
        width: auto;
        height: auto;
    }

    #row {
        width: auto;
        height: auto;
    }

    #box {
        width: 40;
        height: 15;
        border: heavy #9b7bc4;
        background: #2a1845;
    }

    #side {
        width: 4;
        height: 4;
        margin-left: 1;
        margin-top: 10;
        background: red;
    }

    #footer {
        dock: bottom;
        height: 3;
        margin-top: 1;
        background: #1e1033;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="outer"):
            with Vertical(id="wrapper"):
                with Horizontal(id="row"):
                    with Container(id="box"):
                        yield Static("Content inside box")
                    yield Static("SID", id="side")
            yield Static("Footer bar", id="footer")


if __name__ == "__main__":
    TestApp().run()
