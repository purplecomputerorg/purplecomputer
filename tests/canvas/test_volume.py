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


def test_parent_limit_caps_the_keys_and_reads_max():
    settings.set_volume_level(VOLUME_LEVELS[8])
    settings.set_volume_lock(VOLUME_LEVELS[6])
    async def go():
        app = make_app()
        assert app._effective_volume() == VOLUME_LEVELS[6]
        assert app.volume_disabled is False
        app.action_volume_up()
        assert app._effective_volume() == VOLUME_LEVELS[6]
        assert _last_toast(app).endswith("Max 6")
        app.action_volume_down()
        assert app._effective_volume() == VOLUME_LEVELS[5]
        assert _last_toast(app).endswith(" 5")
    run(go())


def test_silent_mode_blocks_the_keys():
    settings.set_volume_lock(0)
    async def go():
        app = make_app()
        assert app.volume_disabled is True
        before = app.volume_level
        app.action_volume_up()
        assert app.volume_level == before
        assert _last_toast(app).endswith("Silent Mode")
    run(go())


def test_mixer_recovery_reapplies_volume_and_preloads_speech(monkeypatch):
    from purple_tui import tts
    from purple_tui.canvas.app import PurpleApp
    calls = []
    monkeypatch.setattr(tts, "preload", lambda: calls.append("preload"))

    class _App:
        audio_ok = None
        _apply_volume_system = lambda self: calls.append("volume")
        call_from_thread = lambda self, fn, *a: fn(*a)
        invalidate = lambda self: None

    app = _App()
    PurpleApp._mixer_recovered(app, True)
    assert calls == ["volume", "preload"] and app.audio_ok is True
    calls.clear()
    PurpleApp._mixer_recovered(app, False)
    assert calls == [] and app.audio_ok is False
