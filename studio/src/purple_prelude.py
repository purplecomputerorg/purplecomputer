"""The `pack` object and the room helpers available in Studio's Python page.

Runs in the browser under Pyodide. Every call goes straight into the pack
being edited in Studio; nothing is saved anywhere else.

    pack.word("tractor", "🚜")
    pack.synonym("tracter", "tractor")
    pack.rank("tractor", "cow")
    pack.instrument("kitchen", "marimba", wood=0.9, tube=0.4)
    pack.room("farm", "Farm",
        when_key("c", show("🐄"), say("cow"), play("C4")),
        when_any_key(add(key())),
    )
    print(pack.summary())
"""

import json

import purple_bridge as _bridge


def _value(v):
    return v


def show(text): return {"do": "show", "text": text}
def add(text): return {"do": "add", "text": text}
def say(text): return {"do": "say", "text": text}
def play(note, instrument="marimba"): return {"do": "play", "note": note, "instrument": instrument}
def drum(name): return {"do": "drum", "name": name}
def clear(): return {"do": "clear"}
def background(color): return {"do": "background", "color": color}
def wait(seconds): return {"do": "wait", "seconds": seconds}
def set_var(name, value): return {"do": "set", "var": name, "value": value}
def change(name, by=1): return {"do": "change", "var": name, "by": by}
def if_(test, then, else_=None): return {"do": "if", "test": test, "then": list(then), "else": list(else_ or [])}
def repeat(times, *body): return {"do": "repeat", "times": times, "body": list(body)}

def var(name): return {"var": name}
def key(): return {"key": True}
def pick(*items): return {"pick": list(items)}
def join(*items): return {"join": list(items)}
def random(a, b): return {"random": {"from": a, "to": b}}
def math(op, a, b): return {"math": op, "a": a, "b": b}
def compare(op, a, b): return {"compare": op, "a": a, "b": b}
def all_of(*tests): return {"and": list(tests)}
def any_of(*tests): return {"or": list(tests)}
def not_(test): return {"not": test}

def when_start(*actions): return {"when": {"event": "start"}, "do": list(actions)}
def when_key(k, *actions): return {"when": {"event": "key", "key": k}, "do": list(actions)}
def when_any_key(*actions): return {"when": {"event": "any_key"}, "do": list(actions)}
def every(seconds, *actions): return {"when": {"event": "every", "seconds": seconds}, "do": list(actions)}


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

    def room(self, name, title=None, *rules, background=None):
        program = {"name": name, "title": title or name, "rules": list(rules)}
        if background:
            program["background"] = background
        problem = _bridge.add_room(json.dumps(program))
        if problem:
            raise ValueError(problem)

    def summary(self):
        return json.loads(_bridge.summary())

    def __repr__(self):
        return "Pack(" + ", ".join(f"{k}={v}" for k, v in self.summary().items()) + ")"


pack = Pack()
