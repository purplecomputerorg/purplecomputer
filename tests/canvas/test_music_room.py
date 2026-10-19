from purple_tui.canvas.harness import make_app, run, type_text


def test_music_shows_the_sticker_keyboard_and_pops_the_last_key():
    async def go():
        app = make_app()
        app.action_switch_room("music")
        assert app._legend_visible and app._legend_key is None
        await type_text(app, "a")
        assert app._legend_key == "a"
    run(go())
