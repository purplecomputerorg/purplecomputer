"""ChromeOS audio server (CRAS) glue. A no-op wherever cras_test_client is absent.

Chrome normally tells CRAS which output node is active. With Chrome never
started, CRAS lists the speaker but marks nothing active, and streams play
into nothing while every call succeeds. So Purple picks the node itself, at
startup and whenever the node list changes (headphones in or out).
guides/chromebook-dev-mode-plan.md, probe run 4.
"""

import functools
import math
import re
import shutil
import subprocess

CLIENT = "cras_test_client"
_NODE_RE = re.compile(r"\s(\d+:\d+)\s.*?\s(yes|no)\s.*\s(HEADPHONE|INTERNAL_SPEAKER)\s")
_NODES_CHANGED = ["dbus-monitor", "--system",
                  "type='signal',interface='org.chromium.cras.Control',member='NodesChanged'"]


@functools.cache
def available() -> bool:
    return shutil.which(CLIENT) is not None


def _client(*args: str) -> str:
    try:
        return subprocess.run([CLIENT, *args], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def pick_output(dump: str) -> str | None:
    """Node id to play through: plugged headphones, else the internal speaker."""
    nodes = {kind: node for node, plugged, kind in _NODE_RE.findall(dump)
             if plugged == "yes" or kind == "INTERNAL_SPEAKER"}
    return nodes.get("HEADPHONE") or nodes.get("INTERNAL_SPEAKER")


def select_output(*_) -> None:
    from .audio import _log
    node = pick_output(_client("--dump_server_info"))
    _log(f"cras: output node {node}")
    if node:
        _client("--select_output", node)


def volume_argv(level: int) -> list[list[str]]:
    """CRAS steps are 0.5 dB each; `level` is a pactl-style cubic percent
    (60*log10 dB), which is what VOLUME_LEVELS was tuned on."""
    steps = max(1, round(100 + 120 * math.log10(level / 100))) if level else 0
    mute = "0" if level else "1"
    return [[CLIENT, "--mute", mute], [CLIENT, "--user_mute", mute], [CLIENT, "--volume", str(steps)]]


def start() -> None:
    if not available():
        return
    select_output()
    from . import audio_hotplug
    audio_hotplug.start(select_output, parse=lambda line: "nodes" if "NodesChanged" in line else None,
                        _monitor_cmd=_NODES_CHANGED)
