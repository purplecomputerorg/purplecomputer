"""Each kid's own computer on this one: their own settings, saved work, Time Travel, and packs.
Switching kids just exits: xinitrc starts Purple again, now as that kid."""

from pathlib import Path

from ..settings import add_kid, get_kid, get_kids, kid_path, remove_kid, set_kid
from .ui import CANCELLED, DOWN, UP, Confirm, Picker

PICKED = Path("/tmp/purple-kid-picked")  # the next start skips Pick your computer


def name_file(kid: str | None = None) -> Path:
    return kid_path(Path.home() / ".purple" / "computer_name.txt", kid)


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def computer_name(kid: str | None = None) -> str:
    from .rooms.parent_menu import DEFAULT_COMPUTER_NAME
    kid = get_kid() if kid is None else kid
    return _read(name_file(kid)) or (not kid and _read(Path("/opt/purple/computer_name.txt"))) or DEFAULT_COMPUTER_NAME


def write_computer_name(name: str, kid: str | None = None):
    path = name_file(kid)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if name:
            path.write_text(name)
        elif path.exists():
            path.unlink()
    except OSError:
        pass


def many() -> bool:
    return len(get_kids()) > 1


def switch(app, kid: str):
    set_kid(kid)
    try:
        PICKED.touch()
    except OSError:
        pass
    app.exit()


def ask_at_boot(app):
    picked = PICKED.exists()
    PICKED.unlink(missing_ok=True)
    if many() and not picked:
        app.push(WhoIsPlaying(app))


def ask_name(app, kid: str | None, title: str, description: str, then):
    """Name a kid's computer (kid None adds a new kid), then call then(kid, name)."""
    from .rooms.parent_menu import ComputerNameScreen

    def on_name(name):
        if name is CANCELLED or not name:
            return
        k = add_kid() if kid is None else kid
        write_computer_name(name, k)
        if k == get_kid():
            app.set_computer_name(name)
        then(k, name)
    taken = {computer_name(k) for k in get_kids() if k != kid}
    app.push(ComputerNameScreen(app, title=title, description=description, taken=taken), on_close=on_name)


class WhoIsPlaying(Picker):
    title = "Pick your computer"
    hint = f"{UP} {DOWN}   Enter"

    def __init__(self, app):
        super().__init__(app, [(k, computer_name(k)) for k in get_kids()])
        self.escape_value = get_kid()
        self.selected = get_kids().index(self.escape_value)

    def _on_confirm(self, kid):
        self.close(kid)
        if kid != get_kid():
            switch(self.app, kid)


class WhoGetsIt(Picker):
    """A new pack is for everyone, or just the kid playing now."""
    title = "Who gets it?"
    escape_value = CANCELLED

    def __init__(self, app):
        super().__init__(app, [(None, "Everyone"), (get_kid(), f"Just {computer_name()}")])


class KidsScreen(Picker):
    title = "Kids"
    DESCRIPTION = "Each kid gets their own computer here, with their own settings, saved work, and Time Travel."

    def __init__(self, app):
        super().__init__(app, self._options())

    def _options(self) -> list:
        now = get_kid()
        return [(k, computer_name(k), "Playing now" if k == now else "Enter to switch or remove") for k in get_kids()] \
            + [("add", "Add a kid"), (None, "Done")]

    def _refresh(self, *_):
        self.options = self._options()
        self.selected = min(self.selected, len(self.options) - 1)
        self.app.invalidate()

    def _on_confirm(self, value):
        if value is None:
            return self.close(True)
        if value == "add":
            return self._add()
        if value != get_kid():
            self._open(value)

    def _add(self):
        from .rooms.parent_menu import DEFAULT_COMPUTER_NAME
        if computer_name("") == DEFAULT_COMPUTER_NAME:
            return ask_name(self.app, "", "First, name this computer", "So each kid's computer has its own name.",
                            lambda *_: (self._refresh(), self._add()))
        ask_name(self.app, None, "Name the new computer", "Like Ari's Computer.", self._added)

    def _added(self, kid, name):
        self._refresh()
        self.app.push(Confirm(self.app, f"Switch to {name} now?", yes="Switch", no="Later", default_no=False),
                      on_close=lambda yes: yes is True and switch(self.app, kid))

    def _open(self, kid):
        name = computer_name(kid)
        picker = Picker(self.app, [("switch", f"Switch to {name}")] + ([("remove", f"Remove {name}")] if kid else [])
                        + [(None, "Never mind")])
        picker.title, picker.dim_values = name, {"remove"}
        self.app.push(picker, on_close=lambda choice: self._chose(kid, name, choice))

    def _chose(self, kid, name, choice):
        if choice == "switch":
            switch(self.app, kid)
        elif choice == "remove":
            self.app.push(Confirm(self.app, f"Remove {name}?", "Its saved work and Time Travel go too. This can't be undone.",
                                  yes="Remove", no="Keep", danger=True),
                          on_close=lambda yes: yes is True and (remove_kid(kid), self._refresh()))
