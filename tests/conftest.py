import threading

import pytest


@pytest.fixture(autouse=True)
def _join_mixer_release_threads(monkeypatch):
    """Depends on monkeypatch so it tears down first: a release thread must
    finish before the mixer globals it writes are restored."""
    yield
    for t in threading.enumerate():
        if t.name == "mixer-idle-release":
            t.join(5)
