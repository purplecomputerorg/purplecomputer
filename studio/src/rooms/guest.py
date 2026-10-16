# Runs in the room's Pyodide: walls off JavaScript so room code (pasted from anywhere) can't import js
# or pyodide, then serves the room exactly as runner.py does on the laptop, over the page's channel.
# The wall raises the bar; the hard boundary is the page's CSP and Purple's checks on every reply.
import sys

import runner
from room_channel import recv, send

_BLOCKED = {"js", "pyodide", "pyodide_js", "_pyodide", "_pyodide_core", "micropip", "room_channel"}


class _Wall:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _BLOCKED:
            raise ImportError(f"Rooms can't use {name}")
        return None


sys.meta_path[:] = [_Wall()] + [f for f in sys.meta_path if not type(f).__module__.split(".")[0].lstrip("_").startswith("pyodide")]
for _name in [n for n in sys.modules if n.split(".")[0] in _BLOCKED]:
    del sys.modules[_name]
del _name
runner.serve(recv, send)
