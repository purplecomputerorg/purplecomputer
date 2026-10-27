"""The code panel: the echo that writes code for what was done by hand, the
recipe cards under the line, and Blocks code."""

import asyncio

import pytest

from purple_tui.canvas.harness import make_app, press, run, type_text
from purple_tui.constants import ICON_LOOP
from purple_tui.canvas.panels import RECIPES, CodePanel, Echo, color_name
from purple_tui.keyboard import NavigationAction
from purple_tui.palette import get_key_color

KEYS = {get_key_color(k).lower(): k for k in "abcdefghijklmnopqrstuvwxyz"}


async def _room(name):
    app = make_app()
    app.action_switch_room(name)
    return app, app.rooms[name]


async def _run_code(app, room, code):
    await room.run_code([code])
    await asyncio.sleep(0)


def _rows(cells: dict) -> list:
    xs, ys = [x for x, _ in cells], [y for _, y in cells]
    return ["".join(cells.get((x, y), ".") for x in range(min(xs), max(xs) + 1)) for y in range(min(ys), max(ys) + 1)]


# ---------------------------------------------------------------- echo
def test_echo_groups_steps_letters_and_colors():
    e = Echo()
    e.color("#ED1C24")
    for _ in range(3):
        e.step("right")
    e.color("#ED1C24")
    e.step("down")
    e.letter("left", "h")
    e.letter("left", "i")
    assert e.line() == "red right 3 down 1 left hi"
    assert e.take() == "red right 3 down 1 left hi"
    assert e.take() == ""


def test_echo_leaves_out_separators_and_starts_over_after_a_pause(monkeypatch):
    e = Echo(pause=2.0)
    clock = iter([10.0, 10.5, 11.0, 20.0])
    monkeypatch.setattr("purple_tui.canvas.panels.time.monotonic", lambda: next(clock))
    for ch in "a,s":
        e.letter("", ch)
    e.letter("", "q")
    assert e.fresh == "as" and e.line() == "q"


def test_color_name_finds_the_nearest_plain_word():
    assert color_name("#ED1C24") == "red"
    assert color_name("#1F75FE") == "blue"
    assert color_name(get_key_color("e")).endswith("red")


def test_art_echo_writes_letters_then_opens_holding_them():
    async def go():
        app, art = await _room("art")
        await type_text(app, "hi")
        art.open_code_panel()
        assert art.code_panel.note[0] == "right hi"
        assert app.code_lines("art") == []          # only what runs is kept
    run(go())


def test_art_echo_writes_a_pen_trail_with_its_color():
    async def go():
        app, art = await _room("art")
        art.set_brush_color("#1F75FE")
        art._set_pen(True)
        for _ in range(4):
            await press(app, "right")
        await press(app, "down")
        art.open_code_panel()
        assert art.code_panel.note[0] == "blue right 4 down 1"
    run(go())


def test_typing_replaces_the_echo_but_editing_keeps_it():
    async def go():
        app, _ = await _room("art")
        panel = CodePanel(app, "art", "right hi")
        await panel.handle(NavigationAction(direction="left"))
        await type_text_into(panel, "yo")
        assert panel.field.value == "right yo"
        fresh = CodePanel(app, "art", "right hi")
        await type_text_into(fresh, "red")
        assert fresh.field.value == "red"
    run(go())


def test_the_echo_types_itself_in_selected_and_any_key_finishes_it():
    async def go():
        app, _ = await _room("art")
        panel = CodePanel(app, "art", "right hi")
        panel._type_in()
        assert panel.field.value == "r" and panel.field.selected == (0, 1)
        await press_control(panel, "tab")
        assert panel.field.value == "right hi" and panel.field.selected == (0, 8) and panel._typer is None
    run(go())


def test_a_mashed_over_echo_comes_back_with_enter():
    async def go():
        app, _ = await _room("art")
        panel = CodePanel(app, "art", "right hi")
        await type_text_into(panel, "x")
        await press_control(panel, "backspace")
        await press_control(panel, "enter")
        assert panel.field.value == "right hi"
    run(go())


def test_a_stale_echo_opens_code_empty(monkeypatch):
    clock = iter([10.0, 10.0 + 31])
    monkeypatch.setattr("purple_tui.canvas.panels.time.monotonic", lambda: next(clock))
    e = Echo()
    e.step("right")
    assert e.take() == ""


def test_arrows_pick_a_word_to_retype_or_remove():
    async def go():
        app, _ = await _room("art")
        panel = CodePanel(app, "art", "red repeat 4 forward 6 turn")
        f = panel.field
        for _ in range(9):
            await panel.handle(NavigationAction(direction="left"))
        assert f.selected == (0, 3)                     # stops at the first word
        await type_text_into(panel, "blue")
        assert f.value == "blue repeat 4 forward 6 turn" and f.selected is None
        await panel.handle(NavigationAction(direction="right"))
        await panel.handle(NavigationAction(direction="right"))
        await panel.handle(NavigationAction(direction="right"))
        assert f.value[slice(*f.selected)] == "forward"
        await panel.handle(NavigationAction(direction="right"))
        await type_text_into(panel, "10")
        assert f.value == "blue repeat 4 forward 10 turn"
        await panel.handle(NavigationAction(direction="right"))
        await panel.handle(NavigationAction(direction="right"))
        assert f.selected is None and f.cursor == len(f.value)
        await panel.handle(NavigationAction(direction="left"))
        await press_control(panel, "backspace")
        assert f.value == "blue repeat 4 forward 10 "
    run(go())


async def press_control(panel, name):
    from purple_tui.keyboard import ControlAction
    await panel.handle(ControlAction(action=name, is_down=True))


async def type_text_into(panel, text):
    from purple_tui.keyboard import CharacterAction
    for ch in text:
        await panel.handle(CharacterAction(char=ch))


def test_music_echo_writes_notes_and_instrument():
    async def go():
        app, music = await _room("music")
        await type_text(app, "qwer")
        music.open_code_panel()
        assert music.code_panel.note[0] == "qwer"
    run(go())


def test_blocks_echo_writes_typing_and_space():
    async def go():
        app, blocks = await _room("blocks")
        await type_text(app, "ab")
        await press(app, "enter")       # turns typing upward, ending the stroke
        blocks.set_brush_color("#48D370")
        blocks._control("space")
        blocks._control("space")
        assert blocks.echo.fresh == "right ab"
        blocks.open_code_panel()
        assert blocks.code_panel.note[0] == "green up 2"
    run(go())


# ---------------------------------------------------------------- cards
def test_down_steps_into_the_cards_and_enter_runs_one_and_keeps_it():
    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        panel = art.code_panel
        await press(app, "down")
        await press(app, "right")
        assert panel.card == 1 and panel.field.value == RECIPES["art"][1][0]
        await press(app, "enter")
        await asyncio.sleep(1)
        assert panel.card is None
        assert panel.field.value == RECIPES["art"][1][0]
        assert app.code_lines("art") == [RECIPES["art"][1][0]]
        assert art.has_content()
    run(go())


def test_up_leaves_the_cards_and_typing_edits_the_recipe():
    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        panel = art.code_panel
        await press(app, "down")
        await press(app, "up")
        assert panel.card is None and panel.field.value == RECIPES["art"][0][0]
        await press(app, "down")
        await press(app, "backspace")
        assert panel.card is None and panel.field.value == RECIPES["art"][0][0][:-1]
    run(go())


def test_left_of_the_first_card_is_close_and_enter_closes():
    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        panel = art.code_panel
        await press(app, "down")
        await press(app, "left")
        await press(app, "left")
        assert panel.card == CodePanel.CLOSE
        await press(app, "right")
        assert panel.card == 0
        await press(app, "left")
        await press(app, "enter")
        assert art.code_panel is None and not app.code_lines("art")
    run(go())


def test_open_code_hides_the_color_legend_and_names_its_arrows(monkeypatch):
    async def go():
        app, art = await _room("art")
        drawn = []
        monkeypatch.setattr(app, "_draw_legend", lambda *a: drawn.append(True))
        app._draw()
        assert drawn
        art.open_code_panel()
        drawn.clear()
        app._draw()
        assert not drawn
        assert "Examples" in art.code_panel.arrow_hint()
        await press(app, "down")
        assert "pick" in art.code_panel.arrow_hint()
        art.close_code_panel()
        app._draw()
        assert drawn
    run(go())


@pytest.mark.parametrize("name", ["art", "music"])
def test_open_code_hides_the_room_header_key_chips(name, monkeypatch):
    async def go():
        app, room = await _room(name)
        drawn = []
        monkeypatch.setattr(room, "_draw_header", lambda *a: drawn.append(True))
        app._draw()
        assert drawn
        room.open_code_panel()
        drawn.clear()
        app._draw()
        assert not drawn
    run(go())


@pytest.mark.parametrize("name, code, shown", [
    ("music", ["letters on", "key g"], ["Letters on", "Key of G"]),
    ("art", ["write on"], ["Write"]),
    ("art", ["brush up"], ["Paint", "Brush up"]),
])
def test_code_status_row_shows_what_code_changed(name, code, shown):
    async def go():
        app, room = await _room(name)
        room.open_code_panel()
        await room.run_code(code)
        texts = [t for _, t in room._code_status(app.g)]
        assert all(s in texts for s in shown)
    run(go())


def test_tab_on_an_empty_code_line_does_not_crash():
    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        paint = art.paint_mode
        await press(app, "tab")
        assert art.paint_mode != paint      # falls through to the room
    run(go())


@pytest.mark.parametrize("code, color, rows", RECIPES["art"])
def test_art_recipe_pictures_match_what_they_paint(code, color, rows):
    async def go():
        app, art = await _room("art")
        art._cursor_x, art._cursor_y = 20, 10
        await _run_code(app, art, code)
        cells = {p: KEYS.get(c[2].lower(), "#") for p, c in art._grid.items() if art._painted(c)}
        assert _rows(cells) == rows
    run(go())


@pytest.mark.parametrize("code, color, rows", RECIPES["blocks"])
def test_blocks_recipe_pictures_match_what_they_build(code, color, rows):
    async def go():
        app, blocks = await _room("blocks")
        blocks._x, blocks._z = 5, 5
        await _run_code(app, blocks, code)
        cells = {(x, -y): KEYS.get(c.lower(), "#") for (x, z, y), c in blocks._blocks.items()}
        assert _rows(cells) == rows
    run(go())


# ---------------------------------------------------------------- blocks code
def test_blocks_code_builds_a_tower_then_a_row_from_its_top():
    async def go():
        app, blocks = await _room("blocks")
        x, z = blocks._x, blocks._z
        await _run_code(app, blocks, "red up 3 blue right 2")
        assert {p for p, c in blocks._blocks.items() if c == "#ED1C24"} == {(x, z, 0), (x, z, 1), (x, z, 2)}
        assert {p for p, c in blocks._blocks.items() if c == "#1F75FE"} == {(x, z, 3), (x + 1, z, 3)}
    run(go())


def test_blocks_code_back_and_front_go_in_depth():
    async def go():
        app, blocks = await _room("blocks")
        x, z = blocks._x, blocks._z
        await _run_code(app, blocks, "back 2")
        assert set(blocks._blocks) == {(x, z, 0), (x, z + 1, 0)}
    run(go())


def test_blocks_esc_then_space_opens_code_and_tab_still_turns():
    async def go():
        app, blocks = await _room("blocks")
        await press(app, "escape")
        await press(app, "space")
        assert blocks.code_panel is not None and app._panel is blocks.code_panel
        await press(app, "tab")
        assert blocks._back
    run(go())


@pytest.mark.parametrize("name", ["art", "music"])
def test_demo_scripts_toggle_code_through_the_esc_menu(name):
    from purple_tui.playback import PlaybackPlayer, ToggleCode

    async def go():
        app, room = await _room(name)
        player = PlaybackPlayer(dispatch_action=app._dispatch_keyboard_action, speed_multiplier=50, code_via_menu=True)
        await player.play([ToggleCode()])
        assert room.code_panel is not None and not app._overlays
        await player.play([ToggleCode()])
        assert room.code_panel is None and not app._overlays
    run(go())


def test_color_name_keeps_grays_gray():
    assert [color_name(c) for c in ("#F5F5F5", "#808080", "#1A1A1A")] == ["white", "gray", "black"]


@pytest.mark.parametrize("name", ["art", "music", "blocks"])
def test_code_opens_a_word_guide_beside_the_room(name):
    async def go():
        app, room = await _room(name)
        vp = app._viewport_rect()
        full = app.content_rect(vp)
        room.open_code_panel()
        narrowed = app.content_rect(vp)
        assert narrowed.w == full.w - room.code_panel.side_width(app.g)
        app._draw()
    run(go())


@pytest.mark.parametrize("name", ["art", "music", "blocks"])
def test_holding_space_never_opens_code(name):
    async def go():
        app, room = await _room(name)
        await press(app, "space", hold=1.2)
        assert room.code_panel is None and room.hold_progress() is None and app._hold_nudge is None
    run(go())


def test_holding_space_in_code_types_one_space():
    from purple_tui.keyboard import ControlAction

    async def go():
        app, art = await _room("art")
        art.open_code_panel()
        await type_text(app, "red")
        for is_repeat in (False, True, True):
            await app._dispatch_keyboard_action(ControlAction(action="space", is_down=True, is_repeat=is_repeat))
        await app._dispatch_keyboard_action(ControlAction(action="space", is_down=False))
        assert art.code_panel.field.value == "red "
    run(go())


def test_letting_go_of_a_shown_hold_leaves_a_hint_a_tap_does_not():
    from purple_tui.keyboard import ControlAction

    async def go():
        app, music = await _room("music")
        app._music_looping_enabled = True
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=True))
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=False))
        assert app._hold_nudge is None
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=True))
        await asyncio.sleep(0.5)
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=False))
        assert app._hold_nudge == "Hold Enter longer to record a loop"
        app._draw()
    run(go())


def test_holding_enter_in_music_names_the_loop_only_when_looping_is_allowed():
    from purple_tui.keyboard import ControlAction

    async def go():
        app, music = await _room("music")
        app._music_looping_enabled = True
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=True))
        await asyncio.sleep(0.3)
        assert music.hold_progress()[1] == f"{ICON_LOOP} Record a loop"
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=False))
        app._music_looping_enabled = False
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=True))
        await asyncio.sleep(0.3)
        assert music.hold_progress() is None
        await app._dispatch_keyboard_action(ControlAction(action="enter", is_down=False))
    run(go())


def test_music_recipe_pictures_light_the_grid_keys():
    from purple_tui.canvas.panels import _keys
    assert _keys("asd") == ["-" * 10, "-" * 10, "asd-------", "-" * 10]


@pytest.mark.parametrize("room, text, heading", [
    ("art", "", None), ("art", "red right 5 turn", "Turn and go"), ("art", "right 2 brush up", "Brush"),
    ("art", "mint", "Colors"), ("art", "dark", "Colors"), ("art", "hello", None),
    ("music", "key", "Key"), ("music", "choose uke", "Sound"), ("blocks", "up 3 repeat", "Again"),
])
def test_the_guide_shows_the_last_code_word_typed(room, text, heading):
    from purple_tui.canvas.panels import guide_topic
    topic = guide_topic(room, text)
    assert (topic and topic[0]) == heading if heading else topic is None


@pytest.mark.parametrize("name", ["art", "music", "blocks"])
def test_the_guide_never_shows_a_heading_with_nothing_under_it(name, monkeypatch):
    import pygame
    from purple_tui.canvas import panels

    async def go():
        app, room = await _room(name)
        room.open_code_panel()
        drawn = []
        for fn in ("draw_text", "draw_markup"):
            real = getattr(app.g, fn)
            monkeypatch.setattr(app.g, fn, lambda s, *a, real=real, **k: drawn.append(s) or real(s, *a, **k))
        monkeypatch.setattr(panels, "_draw_example", lambda g, code, *a, **k: drawn.append(code))
        headings = {h for h, _ in panels.GUIDE[name]}
        for h in range(app.g.em(4), app.g.em(30), 3):
            drawn.clear()
            room.code_panel.draw_side(app.g, pygame.Rect(0, 0, app.g.em(14), h))
            assert not drawn or drawn[-1] not in headings, f"empty {drawn[-1]} at height {h}"
    run(go())


@pytest.mark.parametrize("name", ["art", "blocks"])
def test_colors_in_code_opens_the_wheel_and_writes_the_color_picked(name):
    from purple_tui.canvas.color_wheel import ColorWheel
    from purple_tui.content import get_content

    async def go():
        app, room = await _room(name)
        room.open_code_panel()
        field = room.code_panel.field
        field.set("up 3 colors")
        await press(app, "enter")
        assert isinstance(app.top, ColorWheel)
        for way in ("down", "down", "left"):
            await press(app, way)
        await press(app, "space")
        assert app.top is None and field.value.startswith("up 3 ") and field.value.endswith(" ")
        word = field.value[len("up 3 "):].strip()
        picked = room.brush_color
        content = get_content()
        assert picked == (content.exact_color(word) or content.get_modified_color(word)[0])
        await press(app, "d")
        assert field.value == f"up 3 {word} d"
    run(go())


def test_escape_from_the_code_wheel_puts_the_line_back():
    async def go():
        app, room = await _room("blocks")
        before = room.brush_color
        room.open_code_panel()
        room.code_panel.field.set("right 2 wheel")
        await press(app, "enter")
        await press(app, "up")
        await press(app, "escape")
        assert app.top is None and room.code_panel.field.value == "right 2 wheel" and room.brush_color == before
    run(go())
