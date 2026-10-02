"""Textual UI: the live-USB status when RAM is too small to hold the system."""
from unittest.mock import MagicMock

import purple_tui.purple_tui as tui
from purple_tui.rooms import parent_menu


def _indicator(monkeypatch, cached, needed, present):
    monkeypatch.setattr(tui, "is_usb_cached", lambda: cached)
    monkeypatch.setattr(tui, "is_usb_needed", lambda: needed)
    monkeypatch.setattr(tui, "is_usb_present", lambda: present)
    ind = tui.BootModeIndicator()
    ind.set_interval = MagicMock()
    ind._push_to_title_bar = MagicMock()
    return ind


def test_keep_state_settles_once_and_stops_the_waiting_timers(monkeypatch):
    ind = _indicator(monkeypatch, cached=False, needed=True, present=True)
    ind._waiting = [MagicMock(), MagicMock()]
    assert ind._check_cache_done()
    assert ind._keep_usb and not ind._is_cached
    assert all(t.stop.called for t in ind._waiting)
    assert ind.set_interval.call_count == 1, "one removal check, not one per tick"


def test_still_caching_keeps_waiting(monkeypatch):
    ind = _indicator(monkeypatch, cached=False, needed=False, present=True)
    assert not ind._check_cache_done() and not ind.set_interval.called


def test_parent_menu_asks_to_keep_the_usb_in(monkeypatch):
    monkeypatch.setattr(parent_menu, "is_live_boot", lambda: True)
    monkeypatch.setattr(parent_menu, "is_usb_cached", lambda: False)
    monkeypatch.setattr(parent_menu, "is_usb_needed", lambda: True)
    assert "Keep the USB in" in parent_menu._boot_mode_hint()
