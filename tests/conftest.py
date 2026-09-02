import pytest

from purple_tui import mixer


@pytest.fixture(autouse=True)
def mixer_frontend():
    """Tests here run against the Textual UI, whose mixer copy lives in rooms.music_room."""
    from purple_tui.rooms import music_room
    mixer.bind_frontend_copy(music_room)
    yield
    mixer.bind_frontend_copy(None)
