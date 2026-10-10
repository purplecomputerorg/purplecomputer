"""The `pack` object available in Studio's Python page.

Runs in the browser under Pyodide. Every call goes straight into the pack
being edited in Studio; nothing is saved anywhere else.

    pack.word("tractor", "🚜")
    pack.synonym("tracter", "tractor")
    pack.rank("tractor", "cow")
    pack.instrument("kitchen", "marimba", wood=0.9, tube=0.4)
    pack.room("hello", '''
    from purple import *
    show("👋")
    def on_key(key):
        show(key)
    ''')
    print(pack.summary())
"""

import json
import textwrap

import purple_bridge as _bridge


class Pack:
    """The pack open in Studio. Each method changes it at once."""

    def word(self, word, emoji):
        _bridge.add_word(str(word), str(emoji))

    def synonym(self, alias, word):
        _bridge.add_synonym(str(alias), str(word))

    def rank(self, *words):
        for w in words:
            _bridge.rank(str(w))

    def instrument(self, name, base="marimba", **params):
        problem = _bridge.add_instrument(str(name), str(base), json.dumps(params))
        if problem:
            raise ValueError(problem)

    def room(self, name, source):
        """A room from its Python source; see the Rooms page for what it can call."""
        problem = _bridge.add_room(str(name), textwrap.dedent(str(source)).strip() + "\n")
        if problem:
            raise ValueError(problem)

    def summary(self):
        return json.loads(_bridge.summary())

    def __repr__(self):
        return "Pack(" + ", ".join(f"{k}={v}" for k, v in self.summary().items()) + ")"


pack = Pack()
