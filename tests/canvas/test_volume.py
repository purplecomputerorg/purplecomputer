"""The canvas volume keys, badge and parent limit follow the shared step table in purple_tui.audio."""
import pytest

from purple_tui import settings
from purple_tui.audio import VOLUME_TOP, volume_badge
from purple_tui.canvas.harness import make_app, run
from purple_tui.constants import VOLUME_DEFAULT, VOLUME_LEVELS


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")


def _last_toast(app):
    return app._toasts[-1].text


def test_volume_keys_walk_the_shared_steps_and_show_the_number():
    async def go():
        app = make_app()
        assert app.volume_level == VOLUME_DEFAULT
        app.action_volume_up()
        assert app.volume_level == VOLUME_LEVELS[VOLUME_LEVELS.index(VOLUME_DEFAULT) + 1]
        icon, bars, label = volume_badge(app.volume_level)
        assert label == str(VOLUME_LEVELS.index(app.volume_level))
        assert _last_toast(app) == f"{icon}  {bars}  {label}"
        for _ in range(VOLUME_TOP + 2):
            app.action_volume_up()
        assert app.volume_level == VOLUME_LEVELS[-1]
        assert _last_toast(app).endswith(str(VOLUME_TOP))
    run(go())


def test_saved_volume_from_an_older_step_table_snaps_to_a_current_step():
    settings.set_volume_level(60)  # a level from the old six-step table
    async def go():
        app = make_app()
        assert app.volume_level in VOLUME_LEVELS
        assert abs(app.volume_level - 60) == min(abs(v - 60) for v in VOLUME_LEVELS)
    run(go())
