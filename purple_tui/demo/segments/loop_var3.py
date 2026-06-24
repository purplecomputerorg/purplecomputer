"""Loop variant 3: syncopated with rests (mixed rows)."""

from ._loop_common import build_loop_session

SEGMENT = build_loop_session(
    riff=['t', None, 'y', 't', None, 'u'],
    layer=['e', None, 'r'],
    riff_spacing=0.2,
    layer_spacing=0.3,
)
