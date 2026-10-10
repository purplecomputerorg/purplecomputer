# Runs in the room's Pyodide just before the room: wires the purple module to the page, then
# walls off JavaScript so room code (pasted from anywhere) can't import js or pyodide. The wall
# raises the bar; the hard boundary is the page's CSP and its checks on every message.
import json
import sys

import purple


def _wire():
    from room_channel import recv, send
    purple._send = lambda message: send(json.dumps(message))
    purple._recv = lambda: json.loads(recv())


_wire()

_BLOCKED = {"js", "pyodide", "pyodide_js", "_pyodide", "_pyodide_core", "micropip", "room_channel"}


class _Wall:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _BLOCKED:
            raise ImportError(f"Rooms can't use {name}")
        return None


sys.meta_path[:] = [_Wall()] + [f for f in sys.meta_path if not type(f).__module__.split(".")[0].lstrip("_").startswith("pyodide")]
for _name in [n for n in sys.modules if n.split(".")[0] in _BLOCKED]:
    del sys.modules[_name]
del _name, _wire
