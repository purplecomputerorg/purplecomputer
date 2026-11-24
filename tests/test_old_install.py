"""Live boots on a laptop that may already have Purple: what the probe found decides the screens,
and the parent's choice decides what the install brings. Every permutation: guides/updating-purple.md.
What install.sh then copies is tests/test_install_keep.py."""
import asyncio
import functools
import json
import subprocess

import pytest

from purplecomputer import old_install, settings
from purplecomputer.audio import snap_volume
from purplecomputer.harness import make_app, press, run, type_text
from purplecomputer.rooms import parent_menu as pm
from purplecomputer.rooms.sleep_screen import LiveBootSplash

NAME = "Sam's Computer"


@pytest.fixture(autouse=True)
def laptop(tmp_path, monkeypatch):
    """A live boot whose probe found nothing yet; the laptop's old settings wait in KEEP_DIR."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / ".config/purple/settings.json")
    monkeypatch.setattr(old_install, "KEEP_DIR", tmp_path / "keep")
    monkeypatch.setattr(old_install, "_result", old_install.NONE)
    monkeypatch.setattr(pm, "is_live_boot", lambda: True)
    (tmp_path / "keep/config").mkdir(parents=True)
    (tmp_path / "keep/config/settings.json").write_text(
        json.dumps({"parent_pin": "2222", "littles_mode": "art", "kid_letters": True}))
    return tmp_path


@pytest.fixture
def installs(monkeypatch):
    started = []
    monkeypatch.setattr(pm, "InstallProgressScreen", lambda app, **k: started.append(k) or pm.Overlay(app))
    return started


def found(monkeypatch, state):
    monkeypatch.setattr(old_install, "_result", (state, NAME if state in old_install.UPDATES else "") if state else old_install.NONE)


async def name_screen(app):
    """The name screen the install asks next (the probe answers on a thread), or None."""
    for _ in range(100):
        if isinstance(app.top, pm.ComputerNameScreen):
            return app.top
        await asyncio.sleep(0.01)
    return None


# --- the probe ---------------------------------------------------------------

def test_probe_runs_once_and_retries_when_it_could_not_run(monkeypatch):
    calls = []
    results = iter([None, ("found", "Sam")])
    monkeypatch.setattr(old_install, "_result", None)
    monkeypatch.setattr(old_install, "_run", lambda: calls.append(1) or next(results))
    assert old_install.probe() == old_install.NONE and old_install.known() == old_install.NONE
    assert old_install.probe() == ("found", "Sam") == old_install.probe()
    assert len(calls) == 2


@pytest.mark.parametrize("out,result", [
    ("[PURPLE-FOUND] Sam\n", ("found", "Sam")),
    ("[PURPLE-EMPTY] Sam\n", ("empty", "Sam")),
    ("[PURPLE-EMPTY] \n", ("empty", "")),
    ("[PURPLE-FOUND-UNREADABLE]\n", ("unreadable", "")),
    ("", old_install.NONE),
])
def test_reads_what_the_probe_found(monkeypatch, tmp_path, out, result):
    monkeypatch.setattr(old_install, "PAYLOAD_PATH", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert old_install._run() == result


# --- new or different version ------------------------------------------------

@pytest.mark.parametrize("key,old,newer", [
    ("v2026.03.30-1430", "v1.2", True),                    # v1 laptop
    ("build-abc1234-20260330", "build-def5678-20260101", True),
    ("build-abc1234-20260101", "build-def5678-20260330", False),
    ("build-abc1234-20260330", "build-abc1234-20260330", False),
    ("build-abc1234-20260330", "build-def5678-20260330", False),  # same day, another build
    ("v2026.03.30-1430", "v2026.03.30-0900", True),
    ("v2026.03.30-0900", "v2026.03.30-1430", False),
    ("v2026.03.30-1430", "build-abc1234-20260330", True),  # same day, can't tell
    ("v2026.04.01-0900", "build-abc1234-20260330", True),
    ("v1.3", "v1.2", True),                                # no dates to compare
    ("", "v2026.03.30-1430", True),
])
def test_key_is_newer_unless_the_versions_show_otherwise(key, old, newer):
    assert old_install.key_is_newer(key, old) is newer


@pytest.mark.parametrize("key,old,word", [
    ("build-a-20260330", None, "new"),            # laptop had no version file
    ("build-a-20260330", "build-b-20260101", "new"),
    ("build-a-20260101", "build-b-20260330", "different"),
    ("build-a-20260330", "build-a-20260330", "different"),
])
def test_update_screens_say_new_or_different(laptop, key, old, word):
    (laptop / "key-version").write_text(key)
    if old:
        (laptop / "keep/purple-version").write_text(old)
    assert old_install.key_has(laptop / "key-version") == f"This Key has a {word} version of Purple."


@pytest.mark.parametrize("screen", [pm.ReinstallConfirmScreen, pm.InstallOverScreen, pm.EmptyUpdateScreen, pm.EmptyInstallOverScreen])
def test_every_update_screen_opens_with_the_version_line(laptop, monkeypatch, screen):
    (laptop / "key-version").write_text("build-a-20260101")
    (laptop / "keep/purple-version").write_text("build-b-20260330")
    monkeypatch.setattr(old_install, "key_has", functools.partial(old_install.key_has, laptop / "key-version"))

    async def go():
        assert screen(make_app()).DESCRIPTION.startswith("This Key has a different version of Purple.\n")
    run(go())


# --- the welcome screen and its pop-up ---------------------------------------

@pytest.mark.parametrize("state,note,popup", [
    (None, "To install Purple and keep it", None),
    ("unreadable", "To install Purple and keep it", None),
    ("found", "This Key can update the Purple on this laptop, keeping your kid's work.", pm.InstallOverScreen),
    ("empty", "This Key can update the Purple on this laptop.", pm.EmptyInstallOverScreen),
])
def test_welcome_screen_offers_an_update_only_over_purple_it_could_read(monkeypatch, state, note, popup):
    found(monkeypatch, state)

    async def go():
        app = make_app()
        splash = LiveBootSplash(app)
        app.push(splash)
        splash.tick()
        assert splash._UPDATE_NOTES.get(splash._old_purple, splash._NOTES[-1])[1].startswith(note)
        app._draw()
        await press(app, "space")
        if popup is None:
            assert app.top is None
        else:
            assert type(app.top) is popup and app.top.options[app.top.selected][1] == "Just play for now"
    run(go())


def test_just_play_says_what_is_made_now_wont_be_kept_only_when_the_laptop_has_work():
    assert pm.InstallOverScreen.OPTIONS[-1] == (False, "Just play for now", "What's made now won't be kept when you update")
    assert pm.EmptyInstallOverScreen.OPTIONS[-1] == (False, "Just play for now")


# Pop-up options: found = keep, fresh, Just play; empty = Update, Just play. Just play starts selected.
@pytest.mark.parametrize("state,keys,keep", [
    ("found", ["enter"], None),                        # Just play
    ("found", ["escape"], None),
    ("empty", ["enter"], None),
    ("empty", ["escape"], None),
    ("found", ["up", "up", "enter"], True),            # Update and keep everything
    ("found", ["up", "enter", "up", "enter"], False),  # Update and start fresh, then Erase and update
    ("found", ["up", "enter", "enter"], None),         # Update and start fresh, then Go back
    ("empty", ["up", "enter"], False),                 # Update
])
def test_popup_choices(monkeypatch, installs, state, keys, keep):
    found(monkeypatch, state)

    async def go():
        app = make_app()
        app.push(LiveBootSplash(app))
        await press(app, "space")
        for key in keys:
            await press(app, key)
        if keep is None:
            await asyncio.sleep(0.05)
            assert installs == [] and not isinstance(app.top, pm.ComputerNameScreen)
            return
        screen = await name_screen(app)
        assert screen._name == NAME
        screen.close(NAME)
        assert installs == [{"computer_name": NAME, "keep": keep}]
    run(go())


def test_popup_fresh_then_go_back_returns_to_the_popup(monkeypatch, installs):
    found(monkeypatch, "found")

    async def go():
        app = make_app()
        app.push(LiveBootSplash(app))
        await press(app, "space")
        for key in ["up", "enter", "enter"]:
            await press(app, key)
        assert isinstance(app.top, pm.InstallOverScreen)
    run(go())


@pytest.mark.parametrize("state", ["found", "empty"])
def test_popup_asks_for_the_keys_parent_pin_before_updating(monkeypatch, installs, state):
    found(monkeypatch, state)
    settings.set_parent_pin("1234")

    async def go():
        app = make_app()
        for pin in ("", "1234"):
            app.push(LiveBootSplash(app))
            await press(app, "space")
            app.top.close("keep" if state == "found" else True)
            assert isinstance(app.top, pm.PinEntry)
            if pin:
                await type_text(app, pin)
            else:
                await press(app, "escape")  # PinEntry lets go of an Esc that may still be held
                await press(app, "escape")
            screen = await name_screen(app)
            assert (screen is not None) is bool(pin)
            if screen:
                screen.close(NAME)
        assert len(installs) == 1
    run(go())


# --- the Parent Menu ---------------------------------------------------------

@pytest.mark.parametrize("state,update", [(None, False), ("unreadable", False), ("found", True), ("empty", True)])
def test_parent_menu_says_update_over_purple_it_could_read(monkeypatch, state, update):
    found(monkeypatch, state)
    assert ("Purple is also on this laptop.\nThis Key can update it." in pm._boot_mode_hint()) is update
    verb = "Update Purple" if update else "Install"
    assert pm._install_label(True) == f"{verb} on this Computer"
    assert pm._install_label(False) == f"{verb} (Reinsert USB)"


@pytest.mark.parametrize("state", [None, "found", "empty"])
@pytest.mark.parametrize("available", [True, False])
def test_install_row_is_off_only_until_the_usb_is_back(monkeypatch, state, available):
    found(monkeypatch, state)
    monkeypatch.setattr(pm, "_is_usb_payload_available", lambda: available)

    async def go():
        assert pm.ParentMenu(make_app())._disabled("menu-install") is not available
    run(go())


# After the name screen: which screen, its default, and what each answer installs (None = nothing).
@pytest.mark.parametrize("state,screen,default,choice,keep", [
    (None, pm.InstallConfirmScreen, False, True, False),
    (None, pm.InstallConfirmScreen, False, False, None),
    ("unreadable", pm.UnreadableReinstallScreen, False, True, False),
    ("unreadable", pm.UnreadableReinstallScreen, False, False, None),
    ("found", pm.ReinstallConfirmScreen, "keep", "keep", True),
    ("found", pm.ReinstallConfirmScreen, "keep", True, False),   # fresh, once its Erase is confirmed
    ("found", pm.ReinstallConfirmScreen, "keep", False, None),
    ("empty", pm.EmptyUpdateScreen, True, True, False),
    ("empty", pm.EmptyUpdateScreen, True, False, None),
])
def test_menu_install_choices(monkeypatch, installs, state, screen, default, choice, keep):
    found(monkeypatch, state)

    async def go():
        app = make_app()
        menu = pm.ParentMenu(app)
        app.push(menu)
        menu._install_to_disk()
        name = await name_screen(app)
        assert name._name == (NAME if state in old_install.UPDATES else "")
        name.close(NAME)
        assert type(app.top) is screen and app.top.options[app.top.selected][0] == default
        app.top.close(choice)
        assert installs == ([] if keep is None else [{"computer_name": NAME, "keep": keep}])
    run(go())


def test_menu_fresh_asks_again_before_erasing(monkeypatch):
    found(monkeypatch, "found")

    async def go():
        app = make_app()
        results = []
        app.push(pm.ReinstallConfirmScreen(app), on_close=results.append)
        assert [o[1] for o in app.top.options] == ["Update and keep everything", "No, go back", "Update and start fresh"]
        await press(app, "down")
        await press(app, "down")
        await press(app, "enter")
        assert isinstance(app.top, pm.StartFreshConfirmScreen) and app.top.options[app.top.selected][1] == "Go back"
        await press(app, "up")
        await press(app, "enter")
        assert results == [True]
    run(go())


# --- settings: whose win -----------------------------------------------------

@pytest.mark.parametrize("state,choice,pin,littles", [
    ("empty", True, "2222", "art"),      # the laptop's settings and PIN come onto the Key
    ("found", "keep", None, None),       # install.sh copies the laptop's; the Key's stay as they were
    ("found", True, None, None),         # fresh: the Key's
    (None, True, None, None),
])
def test_only_an_update_with_no_work_adopts_the_laptops_settings(monkeypatch, installs, state, choice, pin, littles):
    found(monkeypatch, state)

    async def go():
        app = make_app()
        menu = pm.ParentMenu(app)
        app.push(menu)
        menu._install_to_disk(choice)
        (await name_screen(app)).close(NAME)
        assert installs and settings.get_parent_pin() == pin and settings.get_littles_mode() == littles
    run(go())


def test_adopt_takes_known_settings_and_leaves_the_keys_others(laptop):
    settings.set_all_caps(True)
    settings.adopt(laptop / "keep/config/settings.json")
    data = json.loads(settings.SETTINGS_FILE.read_text())
    assert data["parent_pin"] == "2222" and data["littles_mode"] == "art" and data["all_caps"] is True
    assert "kid_letters" not in data  # a v1 setting v2 doesn't have


def test_adopt_without_old_settings_changes_nothing(laptop):
    settings.set_all_caps(True)
    before = settings.load_settings()
    settings.adopt(laptop / "missing.json")
    assert settings.load_settings() == before


# --- edges -------------------------------------------------------------------

@pytest.mark.parametrize("kwargs,result", [
    ({}, ("found", "Sam's Computer")),
    ({"work": []}, ("empty", "Sam's Computer")),
    ({"work": [], "config": False, "home_name": None}, ("empty", "Sam's Purple")),  # v1: name only in /opt
    ({"mount_ok": False}, ("unreadable", "")),
    ({"label": "Windows"}, old_install.NONE),
])
def test_what_install_sh_prints_is_what_the_app_reads(monkeypatch, tmp_path, kwargs, result):
    from tests.test_install_keep import _save
    out = _save(tmp_path, probe=True, **kwargs)[0]
    monkeypatch.setattr(old_install, "PAYLOAD_PATH", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    assert old_install._run() == result


def test_a_key_pressed_before_the_probe_finishes_skips_the_popup_but_the_menu_still_updates(monkeypatch, installs):
    monkeypatch.setattr(old_install, "_result", None)
    monkeypatch.setattr(old_install, "_run", lambda: ("found", NAME))

    async def go():
        app = make_app()
        app.push(LiveBootSplash(app))
        await press(app, "space")
        assert app.top is None
        menu = pm.ParentMenu(app)
        app.push(menu)
        assert pm._install_label(True) == "Install on this Computer"
        menu._install_to_disk()
        (await name_screen(app)).close(NAME)
        assert isinstance(app.top, pm.ReinstallConfirmScreen)
    run(go())


@pytest.mark.parametrize("state", ["found", "empty"])
def test_welcome_note_changes_when_the_probe_finishes(monkeypatch, state):
    async def go():
        app = make_app()
        splash = LiveBootSplash(app)
        app.push(splash)
        splash.tick()
        assert splash._old_purple is None
        found(monkeypatch, state)
        app.g.dirty = False
        splash.tick()
        assert splash._old_purple == state and app.g.dirty
        app._draw()
    run(go())


@pytest.mark.parametrize("keep", [True, False])
def test_only_keep_hands_install_sh_the_laptops_data(keep):
    async def go():
        env = pm.InstallProgressScreen(make_app(), computer_name=NAME, keep=keep).install_env()
        assert env.get("PURPLE_KEEP_DIR") == (str(old_install.KEEP_DIR) if keep else None)
        assert env["PURPLE_COMPUTER_NAME"] == NAME and env["PURPLE_LIVE_CONFIG"] == str(settings.SETTINGS_FILE.parent)
    run(go())


def test_a_v1_laptop_in_silent_mode_stays_silent(laptop):
    (laptop / "v1.json").write_text(json.dumps({"silent_mode": True}))
    settings.adopt(laptop / "v1.json")
    assert settings.get_volume_lock() == 0
    (laptop / "v1.json").write_text(json.dumps({"silent_mode": True, "volume_lock": 40}))
    settings.adopt(laptop / "v1.json")
    assert settings.get_volume_lock() == snap_volume(40)


def test_a_v1_laptop_without_silent_mode_keeps_the_keys_limit(laptop):
    settings.set_volume_lock(60)
    (laptop / "v1.json").write_text(json.dumps({"parent_pin": "2222"}))
    settings.adopt(laptop / "v1.json")
    assert settings.get_volume_lock() == snap_volume(60)


@pytest.mark.parametrize("text", ["not json", "[1, 2]", ""])
def test_adopt_ignores_settings_it_cannot_read(laptop, text):
    settings.set_all_caps(True)
    before = settings.load_settings()
    (laptop / "bad.json").write_text(text)
    settings.adopt(laptop / "bad.json")
    assert settings.load_settings() == before


def test_adopt_while_a_second_kid_plays_on_the_key(laptop):
    leo = settings.add_kid()
    settings.set_kid(leo)
    settings.adopt(laptop / "keep/config/settings.json")
    assert settings.get_parent_pin() == "2222" and settings.get_littles_mode() == "art"
    settings.set_kid("")
    assert settings.get_parent_pin() == "2222" and settings.get_littles_mode() is None  # the PIN is shared, Littles is Leo's


def test_version_files_with_a_trailing_newline(laptop):
    (laptop / "key-version").write_text("build-a-20260330\n")
    (laptop / "keep/purple-version").write_text("build-a-20260330\n")
    assert "different" in old_install.key_has(laptop / "key-version")


# --- copy and fit --------------------------------------------------------------

UPDATE_SCREENS = [pm.ReinstallConfirmScreen, pm.InstallOverScreen, pm.EmptyUpdateScreen, pm.EmptyInstallOverScreen,
                  pm.StartFreshConfirmScreen, pm.UnreadableReinstallScreen, pm.InstallConfirmScreen]
SMALL_TO_WIDE = [(1024, 600), (1024, 768), (1280, 800), (1366, 768), (1920, 1080), (3440, 1440)]


@pytest.mark.parametrize("state", [None, "unreadable", "found", "empty"])
def test_update_copy_follows_purples_writing_rules(monkeypatch, state):
    found(monkeypatch, state)

    async def go():
        app = make_app()
        texts = [pm._boot_mode_hint(), pm._install_label(True), pm._install_label(False),
                 *(text for _, text in LiveBootSplash._UPDATE_NOTES.values())]
        for screen in UPDATE_SCREENS:
            s = screen(app)
            texts += [s.title, s.DESCRIPTION, *(t for opt in s.options for t in opt[1:])]
        for text in texts:
            assert "—" not in text and " - " not in text and "USB stick" not in text, text
    run(go())


@pytest.mark.parametrize("size", SMALL_TO_WIDE, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("screen", UPDATE_SCREENS, ids=lambda s: s.__name__)
def test_update_screens_fit_every_screen(size, screen):
    from tests.test_dialog_layout import _body_bottom_and_hint_top

    async def go():
        app = make_app(size)
        dialog = screen(app)
        dialog.selected = len(dialog.options) - 1
        bottom, hint_top = _body_bottom_and_hint_top(app, dialog)
        assert bottom <= hint_top < app.g.h
        assert dialog._shown(app.g) == len(dialog.options), "every choice shows without scrolling"
    run(go())


@pytest.mark.parametrize("size", SMALL_TO_WIDE, ids=lambda s: f"{s[0]}x{s[1]}")
@pytest.mark.parametrize("state", [None, "found", "empty"])
def test_welcome_screen_fits_with_the_update_note_and_a_sound_warning(monkeypatch, size, state):
    found(monkeypatch, state)

    async def go():
        app = make_app(size)
        app.audio_ok = False
        splash = LiveBootSplash(app)
        app.push(splash)
        splash.tick()
        g, notes_bottom, hint = app.g, [], []
        markup, text = g.draw_markup, g.draw_text

        def spy_markup(m, px, x, y, *a, **k):
            h = markup(m, px, x, y, *a, **k)
            notes_bottom.append(y + h)
            return h

        def spy_text(t, px, x, y, *a, **k):
            if t == splash.hint:
                hint.append((y, y + g.line_height(px, "sans")))
            return text(t, px, x, y, *a, **k)
        g.draw_markup, g.draw_text = spy_markup, spy_text
        splash.draw(g)
        assert len(notes_bottom) == 4  # keyboard, Key, install or update, sound
        assert max(notes_bottom) < hint[0][0] and hint[0][1] <= g.h
    run(go())


# --- doing it twice, or not at all ----------------------------------------------

def test_two_presses_on_install_ask_once(monkeypatch, installs):
    import time
    calls = []
    monkeypatch.setattr(old_install, "_result", None)
    monkeypatch.setattr(old_install, "_run", lambda: calls.append(1) or time.sleep(0.1) or ("found", NAME))

    async def go():
        app = make_app()
        menu = pm.ParentMenu(app)
        app.push(menu)
        menu._install_to_disk()
        menu._install_to_disk()
        await name_screen(app)
        await asyncio.sleep(0.15)
        assert calls == [1] and sum(isinstance(o, pm.ComputerNameScreen) for o in app._overlays) == 1
    run(go())


def test_probes_from_two_threads_run_once(monkeypatch):
    import threading
    import time
    calls = []
    monkeypatch.setattr(old_install, "_result", None)
    monkeypatch.setattr(old_install, "_run", lambda: calls.append(1) or time.sleep(0.05) or ("empty", NAME))
    threads = [threading.Thread(target=old_install.probe) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls == [1] and old_install.known() == ("empty", NAME)


@pytest.mark.parametrize("state", ["found", "empty"])
def test_cancelling_the_name_screen_installs_and_adopts_nothing(monkeypatch, installs, state):
    found(monkeypatch, state)

    async def go():
        app = make_app()
        menu = pm.ParentMenu(app)
        app.push(menu)
        menu._install_to_disk(True)
        await name_screen(app)
        await press(app, "escape")
        assert installs == [] and settings.get_parent_pin() is None and app.top is menu
    run(go())


def test_going_back_from_the_v1_update_adopts_nothing(monkeypatch, installs):
    found(monkeypatch, "empty")

    async def go():
        app = make_app()
        menu = pm.ParentMenu(app)
        app.push(menu)
        menu._install_to_disk()
        (await name_screen(app)).close(NAME)
        app.top.close(False)
        assert installs == [] and settings.get_parent_pin() is None and settings.get_littles_mode() is None
    run(go())
