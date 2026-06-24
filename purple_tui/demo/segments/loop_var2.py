"""Loop variant 2: a flowing run (home row, quick)."""

from ._loop_common import build_loop_session

SEGMENT = build_loop_session(
    riff=['a', 's', 'd', 'f', 'g'],
    layer=['h', 'j'],
    riff_spacing=0.16,
    layer_spacing=0.25,
)
