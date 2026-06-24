"""Loop variant 1: sparse and bright (top row, spaced out)."""

from ._loop_common import build_loop_session

SEGMENT = build_loop_session(
    riff=['q', 'e', 't'],
    layer=['y', None, 'u'],
    riff_spacing=0.28,
    layer_spacing=0.3,
)
