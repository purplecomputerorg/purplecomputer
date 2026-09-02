import pytest

from purple_tui import mixer


@pytest.fixture(autouse=True)
def mixer_frontend():
    """The canvas UI uses purple_tui.mixer directly."""
    mixer.bind_frontend_copy(None)
    yield
