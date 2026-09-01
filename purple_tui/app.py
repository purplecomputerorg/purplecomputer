"""Purple Computer: the app shell.

One asyncio loop runs everything: the evdev readers, the timers, the demo
player, and a render task that repaints the whole screen whenever something
invalidated it (at most 60 times a second, usually zero). Input arrives as
KeyActions from KeyboardStateMachine and is dispatched to the top overlay if
any, else to the active room. Rooms and overlays are plain objects with
``handle(action)`` and ``draw(g, rect)``; there is no widget tree.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import pygame

from . import boot_log
from . import palette as P
from .constants import (
    CANVAS_COLS, CANVAS_ROWS, ESCAPE_HOLD_THRESHOLD, ICON_CHAT, ICON_MUSIC, ICON_PALETTE, LIVE_AUDIO_MARKER,
    ROOM_ART, ROOM_MUSIC, ROOM_PLAY, STICKY_SHIFT_GRACE,
    SYSTEM_VOLUME_MAX, UI_READY_MARKER, VOLUME_DEFAULT, VOLUME_LEVELS, is_debug, is_live_boot,
    is_usb_cached, is_usb_present,
)
from .gfx import Gfx, rgb
from .input import EvdevReader, LidSwitchReader, PowerButtonReader, RawKeyEvent, check_evdev_available
from .keyboard import (
    CharacterAction, ControlAction, InputFloodGuard, KeyboardStateMachine, NavigationAction, RoomAction,
    detect_keyboard_mode,
)
from .palette import ROW_LEGEND_COLORS
from .timeline import RoomTimeline
from .ui import TRACK, Overlay, Timers, Toast, draw_hold_bar, draw_keycap, draw_label

ROOMS = (ROOM_PLAY, ROOM_MUSIC, ROOM_ART)
ROOM_ICONS = {"play": ICON_CHAT, "music": ICON_MUSIC, "art": ICON_PALETTE}
ARROW_HINTS = {"play": "Arrows scroll  ↑ ↓", "music": "Arrows change key  ← →", "art": "Arrows move  ← ↑ ↓ →"}
_KID_MATH_REMAP = {'=': '+', '/': '÷', '*': '×'}
BACKSLASH_HOLD = 3.0
FRAME_GAP_VH = 0.8            # gap between the viewport units and the frame line
TIMELINE_DEBOUNCE_S = 3.0
TIMELINE_MAX_WAIT_S = 15.0


def _volume_badge(vol: int):
    steps = [(0, "Sound Off"), (15, "Whisper"), (35, "Quiet"), (60, "Medium"), (85, "Loud"), (100, "Full")]
    label = next(lbl for lvl, lbl in steps if vol <= lvl)
    filled = 0 if vol <= 0 else next(i for i, (lvl, _) in enumerate(steps) if vol <= lvl) * 2
    return "🔇" if vol == 0 else "🔊", "█" * filled + "░" * (10 - filled), label


class PurpleApp:
    def __init__(self, headless=False, windowed=False, size=None):
        boot_log.heartbeat("PurpleApp.__init__ begin")
        self.g = Gfx(size=size, headless=headless, windowed=windowed)
        self.timers = Timers()
        self.running = True
        self.headless = headless
        self.audio_ok = None
        self.volume_level = VOLUME_DEFAULT
        self._volume_before_mute = VOLUME_DEFAULT
        self._volume_lock = None
        self._brightness_hint_showing = False
        self._toasts: list[Toast] = []
        self._overlays: list[Overlay] = []
        self._littles_mode = None
        self._code_panel_enabled = True
        self._code_panel_active = False
        self._music_looping_enabled = True
        self._music_key_switching_enabled = True
        self._escape_consumed_by_mode = False
        self._escape_triggered_long_hold = False
        self._escape_hold_timer = None
        self._escape_down_at = None
        self._backslash_hold_timer = None
        self._sticky_shift_timer = None
        self._evdev_reader = self._power_button_reader = self._lid_switch_reader = None
        self._lid_close_time = None
        self._lid_was_closed_for = 0
        self._bye_screen_active = False
        self._app_suspended = False
        self._idle_inhibitors: set = set()
        self._idle_timer = self._audio_idle_timer = None
        self._demo_player = self._demo_task = None
        self._code_task = None
        self._timelines = {r: RoomTimeline(r) for r in ("play", "music", "art")}
        self._timeline_pending: dict = {}
        self._timeline_timer = None
        self._timeline_restored: set = set()
        self._time_travel = None
        self._last_evdev_time = time.monotonic()
        self._keyboard_state_machine = KeyboardStateMachine()
        self._keyboard_state_machine.on_sticky_shift_change(self._on_sticky_shift_change)
        self._input_flood_guard = InputFloodGuard()
        if os.environ.get("PURPLE_NO_EVDEV") != "1":
            detect_keyboard_mode()
        from .secret import SecretKnock
        self._secret_knock = SecretKnock()
        from .rooms.play_room import PlayRoom
        from .rooms.music_room import MusicRoom
        from .rooms.art_room import ArtRoom
        self.rooms = {"play": PlayRoom(self), "music": MusicRoom(self), "art": ArtRoom(self)}
        self.active_room = "play"
        self._panel = None          # bottom panel drawn inside the viewport: code / loop / time
        self._legend_row = -1
        self._legend_visible = True
        self._computer_name = None
        self._load_settings()
        boot_log.heartbeat("PurpleApp.__init__ complete")

    # ------------------------------------------------------------------ settings
    def _load_settings(self):
        from .settings import (get_all_caps, get_code_panel, get_littles_mode, get_music_key_switching,
                               get_music_looping, get_volume_level, get_volume_lock)
        self.g.all_caps = get_all_caps()
        self.volume_level = get_volume_level()
        self._volume_lock = get_volume_lock()
        saved = get_littles_mode()
        if saved:
            self._littles_mode = saved
            self._code_panel_enabled = self._music_looping_enabled = self._music_key_switching_enabled = False
            self.active_room = {"music": "music", "music_noscreen": "music", "art": "art"}.get(saved, "music")
        else:
            self._code_panel_enabled = get_code_panel()
            self._music_looping_enabled = get_music_looping()
            self._music_key_switching_enabled = get_music_key_switching()

    # ------------------------------------------------------------------ lifecycle
    def run(self):
        asyncio.run(self._main())

    async def _main(self):
        self.timers.bind(asyncio.get_running_loop())
        boot_log.heartbeat("main loop begin")
        from .power_manager import set_logind_power_key
        set_logind_power_key("ignore")
        self.room.on_enter()
        self.timeline_restore(self.active_room)
        self._apply_volume_system()
        from . import tts
        tts.set_muted(self._effective_volume() == 0)
        await self._start_readers()
        if os.environ.get("PURPLE_DEV_MODE") != "1":
            demo = os.environ.get("PURPLE_SLEEP_DEMO")
            self._idle_timer = self.timers.every(1.0 if demo else 5.0, self._check_idle_state)
            if demo:
                from .power_manager import (BATTERY_IDLE_SHUTDOWN, BATTERY_IDLE_SLEEP, CHARGER_IDLE_SHUTDOWN,
                                            CHARGER_IDLE_SLEEP)
                self.notify(f"Demo: sleep@{BATTERY_IDLE_SLEEP}s/{CHARGER_IDLE_SLEEP}s, "
                            f"shutdown@{BATTERY_IDLE_SHUTDOWN}s/{CHARGER_IDLE_SHUTDOWN}s", timeout=5)
        self._arm_audio_idle_timer()
        if "purple.inputtest=1" in _read("/proc/cmdline"):
            self._debug_no_input_received = False
            self.timers.after(60.0, self._debug_exit_on_no_input)
        if os.environ.get("PURPLE_DEMO_AUTOSTART"):
            default_preroll = "0" if os.environ.get("PURPLE_RECORD_GO_FILE") else "5"
            self.timers.after(float(os.environ.get("PURPLE_DEMO_PREROLL", default_preroll)), self.start_demo)
        if os.environ.get("PURPLE_DEV_MODE") != "1" and is_live_boot():
            from .rooms.sleep_screen import LiveBootSplash
            self.push(LiveBootSplash(self))
        self._screenshot_timer = None
        if os.environ.get("PURPLE_DEV_MODE") == "1":
            self._screenshot_timer = self.timers.every(0.2, self._check_screenshot_trigger)
        if os.environ.get("PURPLE_NO_AUDIO") == "1":
            self.audio_ok = False
        else:
            self._start_mixer_warmup()
        if not is_live_boot() and os.path.exists(LIVE_AUDIO_MARKER):
            self.timers.after(30.0, self._check_first_boot_audio)
        self._usb_timer = self.timers.every(1.0, self._tick_usb) if is_live_boot() else None
        self._battery_timer = self.timers.every(30.0, self.invalidate)
        boot_log.heartbeat("main loop ready")
        try:
            await self._render_loop()
        finally:
            await self._shutdown()

    async def _start_readers(self):
        if os.environ.get("PURPLE_NO_EVDEV") == "1":
            return
        from .power_manager import POWER_HOLD_SHUTDOWN, _power_diag
        self._evdev_reader = EvdevReader(callback=self._handle_raw_key_event, grab=not is_debug())
        await self._evdev_reader.start()
        try:
            self._power_button_reader = PowerButtonReader(callback=self._handle_power_button_event,
                                                          hold_seconds=POWER_HOLD_SHUTDOWN)
            await self._power_button_reader.start()
            for dev in self._power_button_reader._devices:
                _power_diag(f"POWER BUTTON INIT: listening on {dev.path} ({dev.name})")
        except Exception as e:
            _power_diag(f"POWER BUTTON INIT: start failed: {e}")
            self._power_button_reader = None
        try:
            self._lid_switch_reader = LidSwitchReader(callback=self._handle_lid_switch_event)
            await self._lid_switch_reader.start()
        except Exception:
            self._lid_switch_reader = None

    async def _render_loop(self):
        from .sdl_input import pump
        first = True
        while self.running:
            for raw in pump(self.g):
                if raw is None:
                    self.exit()
                elif self._evdev_reader is None:
                    await self._handle_raw_key_event(raw)
            now = time.monotonic()
            live = [t for t in self._toasts if t.expires > now]
            if len(live) != len(self._toasts):
                self._toasts = live
                self.g.dirty = True
            if self.g.dirty:
                self._draw()
                self.g.present()
                if first:
                    first = False
                    self._mark_ui_ready()
            await asyncio.sleep(1 / 60)

    def _mark_ui_ready(self):
        boot_log.mark_first_render()
        try:
            Path(UI_READY_MARKER).touch()
        except OSError:
            pass
        ready_file = os.environ.get("PURPLE_RECORD_READY_FILE")
        if ready_file:
            try:
                Path(ready_file).write_text("ready")
            except OSError:
                pass
        from .rooms.parent_menu import apply_saved_display_settings
        self.timers.after(0.5, apply_saved_display_settings)

    def exit(self):
        self.running = False

    async def _shutdown(self):
        self._timeline_flush()
        for reader in (self._evdev_reader, self._power_button_reader, self._lid_switch_reader):
            if reader:
                try:
                    await reader.stop()
                except Exception:
                    pass
        try:
            import threading
            if pygame.mixer.get_init():
                t = threading.Thread(target=pygame.mixer.quit, daemon=True)
                t.start()
                t.join(timeout=1.0)
        except Exception:
            pass
        pygame.display.quit()

    def invalidate(self, *_):
        self.g.dirty = True

    def call_from_thread(self, fn, *args):
        self.timers.call_from_thread(fn, *args)

    # ------------------------------------------------------------------ overlays / toasts
    @property
    def top(self):
        return self._overlays[-1] if self._overlays else None

    def push(self, overlay: Overlay, on_close=None):
        overlay._on_close = on_close
        self._overlays.append(overlay)
        overlay.on_open()
        self.invalidate()

    def pop(self, overlay: Overlay, result=None):
        if overlay in self._overlays:
            self._overlays.remove(overlay)
            overlay.on_close()
            if overlay._on_close:
                overlay._on_close(result)
            self.invalidate()

    def has_overlay(self, cls) -> bool:
        return any(isinstance(o, cls) for o in self._overlays)

    def notify(self, text: str, timeout: float = 1.5, title: str = ""):
        self._toasts.append(Toast(text, timeout))
        self.invalidate()

    def clear_notifications(self):
        self._toasts.clear()
        self.invalidate()

    # ------------------------------------------------------------------ rooms
    @property
    def room(self):
        return self.rooms[self.active_room]

    def action_switch_room(self, room_name: str):
        if room_name not in self.rooms:
            room_name = "play"
        if self._time_travel is not None:
            self._cancel_time_travel()
        if room_name == self.active_room:
            return
        self._timeline_flush()
        self._silence_music()
        self.room.on_leave()
        self.clear_notifications()
        self.active_room = room_name
        self._panel = None
        self.room.on_enter()
        self.timeline_restore(room_name)
        if self._code_panel_active:
            if room_name in ("music", "art"):
                self.room.open_code_panel()
            else:
                self._code_panel_active = False
        self._legend_row = -1
        self._legend_visible = room_name != "music"
        self._update_shift_indicator()
        self.invalidate()

    def set_panel(self, panel):
        """Bottom-of-viewport panel (code line, loop station, time travel) or None."""
        self._panel = panel
        self._code_panel_active = panel is not None and getattr(panel, "kind", "") == "code"
        self.invalidate()

    def set_legend(self, color: str | None, visible: bool = True):
        from .palette import get_legend_row_from_color
        self._legend_visible = visible
        self._legend_row = get_legend_row_from_color(color) if color else -1
        self.invalidate()

    def _silence_music(self):
        self._stop_code_execution()
        if self.active_room == "music":
            self.rooms["music"].stop_sound()

    def _stop_code_execution(self) -> bool:
        if self._code_task and not self._code_task.done():
            self._code_task.cancel()
            self._code_task = None
            return True
        return False

    def run_code(self, room: str, lines: list):
        """Run code-panel lines against a room; the last correction lands in the panel's recall hint."""
        self._stop_code_execution()
        self._code_task = asyncio.create_task(self.rooms[room].run_code(lines))

    def _start_fresh(self, room: str | None = None):
        for r in ([room] if room else list(self.rooms)):
            self.timeline_capture_now(r)
            self.rooms[r].clear()
            self.timeline_capture_now(r)
        self.invalidate()

    def clear_all_state(self):
        self._start_fresh()

    # ------------------------------------------------------------------ input
    async def _handle_raw_key_event(self, event: RawKeyEvent):
        self._debug_no_input_received = True
        self._record_user_activity()
        now = time.monotonic()
        if now - self._last_evdev_time > 5.0:
            from . import tts
            tts.stop()
            self._input_flood_guard.reset()
        self._last_evdev_time = now
        for action in self._keyboard_state_machine.process(event):
            if self._input_flood_guard.should_drop(action):
                continue
            await self._dispatch_keyboard_action(action)
        sm = self._keyboard_state_machine
        if sm.backslash_held and self._backslash_hold_timer is None:
            self._backslash_hold_timer = self.timers.after(BACKSLASH_HOLD, self._check_backslash_hold)
        elif not sm.backslash_held and self._backslash_hold_timer is not None:
            self._backslash_hold_timer.stop()
            self._backslash_hold_timer = None

    async def _dispatch_keyboard_action(self, action):
        self._record_user_activity()
        self.invalidate()
        if isinstance(action, RoomAction):
            if action.room == "parent":
                self.action_parent_menu()
            else:
                self.action_switch_room(action.room)
            return
        if isinstance(action, CharacterAction):
            if self._secret_knock.feed(action):
                self._unlock_secret_menu()
            if action.ctrl_held:
                return
        if isinstance(action, ControlAction) and action.action == "escape":
            if action.is_down and not action.is_repeat:
                self._escape_triggered_long_hold = False
                self._escape_consumed_by_mode = False
                if self.demo_running and not action.synthetic:
                    self.cancel_demo()
                    self._escape_consumed_by_mode = True
                if self._stop_code_execution():
                    self._escape_consumed_by_mode = True
                self._modal_open_at_escape_press = bool(self._overlays)
                self._start_escape_hold_timer()
            elif not action.is_down:
                self._cancel_escape_hold_timer()
                consumed = self._escape_consumed_by_mode
                self._escape_consumed_by_mode = False
                if not self._escape_triggered_long_hold and not self._modal_open_at_escape_press and not consumed:
                    if not self._overlays and not self._littles_mode:
                        self._show_room_picker()
                        return
        if isinstance(action, ControlAction) and action.is_down and not self._littles_mode:
            handler = {"volume_mute": self.action_volume_mute, "volume_down": self.action_volume_down,
                       "volume_up": self.action_volume_up, "brightness_hint": self._show_brightness_hint}.get(action.action)
            if handler:
                handler()
                return
        if isinstance(action, CharacterAction) and action.char in _KID_MATH_REMAP:
            action = CharacterAction(char=_KID_MATH_REMAP[action.char], shifted=action.shifted,
                                     shift_held=action.shift_held, is_repeat=action.is_repeat,
                                     arrow_held=action.arrow_held)
        if self._overlays:
            await self.top.handle(action)
            return
        if self._time_travel is not None:
            await self._handle_time_travel_action(action)
            return
        if self._littles_mode and isinstance(action, ControlAction) and action.action == "tab":
            return
        await self.room.handle(action)
        self._timeline_touch()

    def _start_escape_hold_timer(self):
        self._cancel_escape_hold_timer()
        self._escape_down_at = time.monotonic()
        self._escape_hold_timer = self.timers.after(ESCAPE_HOLD_THRESHOLD, self._check_escape_hold)

    def _cancel_escape_hold_timer(self):
        if self._escape_hold_timer:
            self._escape_hold_timer.stop()
            self._escape_hold_timer = None
        self._escape_down_at = None

    def _check_escape_hold(self):
        self._escape_hold_timer = None
        if self._keyboard_state_machine.check_escape_hold():
            self._escape_triggered_long_hold = True
            self._cancel_escape_hold_timer()
            from .room_picker import RoomPicker
            for o in list(self._overlays):
                if isinstance(o, RoomPicker):
                    o.close(None)
            self.action_parent_menu()

    def _check_backslash_hold(self):
        self._backslash_hold_timer = None
        if self._keyboard_state_machine.check_backslash_hold():
            self.action_parent_menu()

    def hold_progress(self):
        """(fraction, label) for the room's hold gesture in flight, else None.
        The Esc hold (Parent Menu) shows nothing on purpose: no affordance for kids."""
        return self.room.hold_progress()

    # ------------------------------------------------------------------ room picker / parent menu
    def _show_room_picker(self):
        from .room_picker import RoomPicker
        self.push(RoomPicker(self), on_close=self._on_room_picked)

    def _on_room_picked(self, result):
        if not result:
            return
        if "room" in result:
            self.action_switch_room(result["room"])
        elif result.get("close_code"):
            self.room.close_code_panel()
        elif result.get("open_code"):
            self.room.open_code_panel()
        elif "clear_room" in result:
            self._start_fresh(result["clear_room"])
        elif result.get("time_travel"):
            self._start_time_travel()

    def action_parent_menu(self):
        self._cancel_escape_hold_timer()
        self._keyboard_state_machine.reset()
        self.clear_notifications()
        from .settings import get_parent_pin
        pin = get_parent_pin()
        if pin:
            from .rooms.parent_menu import PinEntry
            self.push(PinEntry(self, "Enter Parent PIN", verify=lambda p: p == pin),
                      on_close=lambda ok: ok is not None and self._open_parent_menu_after_pin())
            return
        self._open_parent_menu_after_pin()

    def _open_parent_menu_after_pin(self):
        from .rooms.parent_menu import LittlesExitScreen, ParentMenu
        if self._littles_mode:
            self.push(LittlesExitScreen(self), on_close=self._on_littles_exit_dismissed)
        else:
            self.push(ParentMenu(self), on_close=self._on_parent_menu_dismissed)

    def _on_littles_exit_dismissed(self, result):
        from .rooms.parent_menu import LittlesModeScreen, ParentMenu
        if result == "exit":
            from .settings import set_littles_mode
            set_littles_mode(None)
            self._apply_littles_mode(None)
        elif result == "switch":
            from .ui import CANCELLED
            self.push(LittlesModeScreen(self), on_close=lambda m: m is not CANCELLED and self._apply_littles_mode(m))
        elif result == "parent":
            self.push(ParentMenu(self), on_close=self._on_parent_menu_dismissed)

    def _on_parent_menu_dismissed(self, result):
        self.clear_notifications()
        if isinstance(result, dict) and "littles_mode" in result:
            self._apply_littles_mode(result["littles_mode"])

    def _apply_littles_mode(self, mode):
        self._littles_mode = mode
        if mode:
            self._code_panel_enabled = self._music_looping_enabled = self._music_key_switching_enabled = False
            self._code_panel_active = False
            room = {"music": "music", "music_noscreen": "music", "art": "art"}.get(mode, "music")
            self.action_switch_room(room)
            self.room.close_code_panel()
        else:
            from .settings import get_code_panel, get_music_key_switching, get_music_looping
            self._code_panel_enabled = get_code_panel()
            self._music_looping_enabled = get_music_looping()
            self._music_key_switching_enabled = get_music_key_switching()
        self.rooms["music"].on_littles_change()
        self.invalidate()

    def _unlock_secret_menu(self):
        from .settings import get_secret_unlocked, set_secret_unlocked
        if not get_secret_unlocked():
            set_secret_unlocked(True)

    # ------------------------------------------------------------------ timeline / time travel
    def timeline_restore(self, room: str):
        if room in self._timeline_restored:
            return
        self._timeline_restored.add(room)
        try:
            tip = self._timelines[room].tip()
            if tip:
                self.rooms[room].restore_timeline_state(tip)
            else:
                self._timelines[room].record(self.rooms[room].timeline_state())
        except Exception:
            pass

    def timeline_capture_now(self, room: str):
        self._timeline_pending.pop(room, None)
        if self._time_travel is not None:
            return
        try:
            self._timelines[room].record(self.rooms[room].timeline_state())
        except Exception:
            pass

    def _timeline_touch(self):
        if self._time_travel is not None:
            return
        now = time.monotonic()
        first, _ = self._timeline_pending.get(self.active_room, (now, now))
        self._timeline_pending[self.active_room] = (first, now)
        if self._timeline_timer is None:
            self._timeline_timer = self.timers.every(1.0, self._timeline_tick)

    def _timeline_tick(self):
        now = time.monotonic()
        for room, (first, last) in list(self._timeline_pending.items()):
            if now - last >= TIMELINE_DEBOUNCE_S or now - first >= TIMELINE_MAX_WAIT_S:
                self.timeline_capture_now(room)
        if not self._timeline_pending and self._timeline_timer is not None:
            self._timeline_timer.stop()
            self._timeline_timer = None

    def _timeline_flush(self):
        for room in list(self._timeline_pending):
            self.timeline_capture_now(room)

    def _start_time_travel(self):
        room = self.active_room
        self.room.close_code_panel()
        self._silence_music()
        self._timeline_flush()
        self.timeline_capture_now(room)
        tl = self._timelines[room]
        if len(tl) == 0:
            return
        from .panels import TimeTravelBar
        self._time_travel = {"room": room, "index": len(tl) - 1}
        self.set_panel(TimeTravelBar(self))
        self.invalidate()

    def _end_time_travel(self):
        self._time_travel = None
        self.set_panel(None)

    def _cancel_time_travel(self):
        tt = self._time_travel
        tl = self._timelines[tt["room"]]
        if tt["index"] != len(tl) - 1:
            try:
                self.rooms[tt["room"]].restore_timeline_state(tl.tip())
            except Exception:
                pass
        self._end_time_travel()

    def _land_time_travel(self):
        room = self._time_travel["room"]
        self._end_time_travel()
        self.timeline_capture_now(room)

    def _step_time_travel(self, delta: int):
        tt = self._time_travel
        tl = self._timelines[tt["room"]]
        index = max(0, min(len(tl) - 1, tt["index"] + delta))
        if index == tt["index"]:
            return
        tt["index"] = index
        try:
            self.rooms[tt["room"]].restore_timeline_state(tl.state_at(index))
        except Exception:
            pass
        self.invalidate()

    def time_travel_position(self):
        tt = self._time_travel
        return (tt["index"], len(self._timelines[tt["room"]])) if tt else (0, 0)

    async def _handle_time_travel_action(self, action):
        if isinstance(action, NavigationAction):
            if action.direction == "left":
                self._step_time_travel(-1)
            elif action.direction == "right":
                self._step_time_travel(1)
        elif isinstance(action, ControlAction) and action.is_down and not action.is_repeat:
            if action.action == "enter":
                self._land_time_travel()
            elif action.action == "escape":
                self._escape_consumed_by_mode = True
                self._cancel_time_travel()

    # ------------------------------------------------------------------ volume
    def _effective_volume(self) -> int:
        return self._volume_lock if self._volume_lock is not None else self.volume_level

    @property
    def volume_locked(self) -> bool:
        return self.audio_ok is False or self._volume_lock is not None

    def _apply_volume_system(self):
        try:
            import subprocess
            vol = round(self._effective_volume() * SYSTEM_VOLUME_MAX / 100)
            subprocess.Popen(["amixer", "sset", "Master", f"{vol}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _apply_volume(self):
        from . import tts
        from .settings import set_volume_level
        set_volume_level(self.volume_level)
        vol = self._effective_volume()
        tts.set_muted(vol == 0)
        self._apply_volume_system()
        icon, bars, label = _volume_badge(vol)
        self.clear_notifications()
        self.notify(f"{icon}  {bars}  {label}")

    def _notify_volume_lock_blocked(self) -> bool:
        if self._volume_lock is not None:
            icon, bars, _ = _volume_badge(self._volume_lock)
            self.clear_notifications()
            self.notify(f"{icon}  {bars}  {'Silent Mode' if self._volume_lock == 0 else 'Locked'}")
            return True
        return False

    def action_volume_mute(self):
        if self._notify_volume_lock_blocked():
            return
        if self.volume_level > 0:
            self._volume_before_mute = self.volume_level
            self.volume_level = 0
        else:
            self.volume_level = self._volume_before_mute if self._volume_before_mute > 0 else VOLUME_DEFAULT
        self._apply_volume()

    def action_volume_down(self):
        if self._notify_volume_lock_blocked():
            return
        idx = max(i for i, lvl in enumerate(VOLUME_LEVELS) if self.volume_level >= lvl)
        if idx > 0:
            self.volume_level = VOLUME_LEVELS[idx - 1]
        self._apply_volume()

    def action_volume_up(self):
        if self._notify_volume_lock_blocked():
            return
        idx = next((i for i, lvl in enumerate(VOLUME_LEVELS) if self.volume_level <= lvl), len(VOLUME_LEVELS) - 1)
        if idx < len(VOLUME_LEVELS) - 1:
            self.volume_level = VOLUME_LEVELS[idx + 1]
        self._apply_volume()

    def _show_brightness_hint(self):
        if self._brightness_hint_showing:
            return
        self._brightness_hint_showing = True
        self.notify("Go to the Parent Menu to change brightness", timeout=3)
        self.timers.after(3, lambda: setattr(self, "_brightness_hint_showing", False))

    # ------------------------------------------------------------------ shift indicator
    def _update_shift_indicator(self):
        self.invalidate()

    def _on_sticky_shift_change(self, active: bool):
        if self._sticky_shift_timer:
            self._sticky_shift_timer.stop()
            self._sticky_shift_timer = None
        self.invalidate()
        if active:
            self._sticky_shift_timer = self.timers.after(STICKY_SHIFT_GRACE, self.invalidate)

    # ------------------------------------------------------------------ power / idle
    def inhibit_idle(self, reason: str):
        self._idle_inhibitors.add(reason)

    def uninhibit_idle(self, reason: str):
        self._idle_inhibitors.discard(reason)

    def _record_user_activity(self):
        try:
            from .power_manager import get_power_manager
            get_power_manager().record_activity()
        except Exception:
            pass
        self._arm_audio_idle_timer()

    def _is_sleep_or_bye_active(self) -> bool:
        from .rooms.sleep_screen import ByeScreen, ShutdownConfirmScreen, SleepScreen
        return self._bye_screen_active or self.has_overlay((SleepScreen, ShutdownConfirmScreen, ByeScreen))

    def _check_idle_state(self):
        try:
            from .power_manager import LID_SHUTDOWN_DELAY, _power_log, get_power_manager
            pm = get_power_manager()
            charger = pm.is_on_charger()
            if self._lid_switch_reader is None:
                lid_open = pm.get_lid_state()
                if lid_open is False and self._lid_close_time is None:
                    _power_log("LID CLOSED (polled /proc/acpi fallback)")
                    self._lid_close_time = time.time()
                    if not self._is_sleep_or_bye_active():
                        self._show_sleep_screen()
                elif lid_open is not False and self._lid_close_time is not None:
                    self._lid_was_closed_for = time.time() - self._lid_close_time
                    _power_log(f"LID OPENED (polled /proc/acpi fallback), was closed for {self._lid_was_closed_for:.1f}s")
                    self._lid_close_time = None
                    self._record_user_activity()
            if self._lid_close_time is not None:
                elapsed = time.time() - self._lid_close_time
                if elapsed >= LID_SHUTDOWN_DELAY:
                    _power_log(f"LID SHUTDOWN: lid closed for {elapsed:.0f}s >= {LID_SHUTDOWN_DELAY}s, shutting down")
                    self._show_bye_screen()
                elif int(elapsed) % 30 == 0:
                    _power_log(f"TICK: lid closed {elapsed:.0f}s/{LID_SHUTDOWN_DELAY}s, charger={charger}")
                return
            if self._is_sleep_or_bye_active() or self._idle_inhibitors:
                return
            idle = pm.get_idle_seconds()
            if idle >= pm.get_idle_sleep_threshold():
                _power_log(f"IDLE SLEEP: idle {idle:.0f}s >= {pm.get_idle_sleep_threshold()}s, charger={charger}")
                self._show_sleep_screen()
                return
            if idle >= pm.get_idle_shutdown_threshold():
                _power_log(f"IDLE SHUTDOWN: idle {idle:.0f}s >= {pm.get_idle_shutdown_threshold()}s, charger={charger}")
                self._show_bye_screen()
        except Exception:
            pass

    def _show_sleep_screen(self):
        if self._is_sleep_or_bye_active():
            return
        self._silence_music()
        from .rooms.sleep_screen import SleepScreen
        self.push(SleepScreen(self))

    def _show_shutdown_confirm(self):
        if self._is_sleep_or_bye_active():
            return
        self._silence_music()
        from .rooms.sleep_screen import ShutdownConfirmScreen
        self.push(ShutdownConfirmScreen(self))

    def _show_bye_screen(self):
        if self._bye_screen_active:
            return
        from .rooms.sleep_screen import ByeScreen, ShutdownConfirmScreen, SleepScreen
        for o in list(self._overlays):
            if isinstance(o, (SleepScreen, ShutdownConfirmScreen)):
                o.close()
        if self._evdev_reader:
            self._evdev_reader.release_grab()
        self._silence_music()
        self._bye_screen_active = True
        self.push(ByeScreen(self))

    async def _handle_lid_switch_event(self, event):
        from .power_manager import _power_log
        if self._bye_screen_active:
            _power_log(f"LID EVENT ignored: bye screen active, is_open={event.is_open}")
            return
        if not event.is_open:
            _power_log("LID CLOSED (evdev)")
            self._lid_close_time = time.time()
            if not self._is_sleep_or_bye_active():
                self._show_sleep_screen()
        else:
            self._lid_was_closed_for = time.time() - self._lid_close_time if self._lid_close_time else 0
            _power_log(f"LID OPENED (evdev), was closed for {self._lid_was_closed_for:.1f}s")
            self._lid_close_time = None
            self._record_user_activity()
        self.invalidate()

    async def _handle_power_button_event(self, event):
        from .power_manager import _power_log
        _power_log(f"POWER BUTTON: action={event.action}, suspended={self._app_suspended}, bye_active={self._bye_screen_active}")
        if self._app_suspended or self._bye_screen_active:
            return
        if event.action == "tap":
            from .rooms.sleep_screen import ShutdownConfirmScreen
            if self.has_overlay(ShutdownConfirmScreen):
                self._show_bye_screen()
            else:
                self._show_shutdown_confirm()
        elif event.action == "hold":
            self._show_bye_screen()

    def _debug_exit_on_no_input(self):
        if not self._debug_no_input_received:
            self.exit()

    # ------------------------------------------------------------------ audio lifecycle
    def _start_mixer_warmup(self):
        import threading

        def _warm():
            from .mixer import _reset_mixer_state, warm_mixer
            ok = False
            try:
                if warm_mixer():
                    ok = True
                    boot_log.heartbeat("mixer ok (attempt 1)")
                else:
                    for delay in [0.5, 1, 2]:
                        if not _reset_mixer_state():
                            boot_log.heartbeat("mixer unusable, not retrying (hw broken or silent codec)")
                            break
                        boot_log.heartbeat(f"mixer probe failed, retrying in {delay}s")
                        time.sleep(delay)
                        if warm_mixer():
                            ok = True
                            boot_log.heartbeat("mixer ok (retry)")
                            break
                    else:
                        boot_log.heartbeat("mixer warmup failed")
            except Exception as e:
                boot_log.heartbeat(f"mixer warmup error: {e!r}")
            self.audio_ok = ok
            self.call_from_thread(self.invalidate)
            self._start_audio_hotplug()
            self._start_audio_retry_poll()
        threading.Thread(target=_warm, daemon=True, name="mixer-warmup").start()

    def _check_first_boot_audio(self):
        from .rooms.sleep_screen import FirstBootPowerCycleScreen, first_boot_power_cycle_needed
        if self.audio_ok is None:
            self.timers.after(10.0, self._check_first_boot_audio)
            return
        offer = first_boot_power_cycle_needed(self.audio_ok)
        if self.audio_ok or offer:
            try:
                os.unlink(LIVE_AUDIO_MARKER)
            except OSError:
                pass
        if offer:
            boot_log.heartbeat("first boot: no sound card, offering power cycle")
            self.push(FirstBootPowerCycleScreen(self))

    def _start_audio_hotplug(self):
        from . import audio_hotplug

        def _on_event(action: str):
            boot_log.heartbeat(f"audio hotplug: {action}")
            from .mixer import reinit_mixer_after_hotplug
            from .tts import _dbg
            _dbg(f"audio hotplug event: {action}")
            ok = reinit_mixer_after_hotplug()
            self.call_from_thread(setattr, self, "audio_ok", ok)
            self.call_from_thread(self.invalidate)
            boot_log.heartbeat(f"audio hotplug reinit -> ok={ok}")
        audio_hotplug.start(_on_event)

    def _arm_audio_idle_timer(self):
        if self._audio_idle_timer is None and self.audio_ok is not False and self.timers.loop:
            self._audio_idle_timer = self.timers.every(30.0, self._check_audio_idle)

    def _check_audio_idle(self):
        from . import tts
        from .mixer import AUDIO_IDLE_SECONDS, mixer_is_open, request_idle_release
        from .power_manager import get_power_manager
        if not mixer_is_open():
            if self._audio_idle_timer is not None:
                self._audio_idle_timer.stop()
                self._audio_idle_timer = None
            return
        if self.active_room == "music" or tts._current_channel is not None \
                or get_power_manager().get_idle_seconds() < AUDIO_IDLE_SECONDS:
            return
        request_idle_release()

    def _start_audio_retry_poll(self):
        import threading

        def _poll():
            from .mixer import reinit_mixer_after_hotplug
            from .power_manager import get_power_manager
            from .tts import _dbg
            delay = 5
            deadline = time.monotonic() + 600
            while delay <= 80 and time.monotonic() < deadline:
                time.sleep(delay)
                if self.audio_ok:
                    return
                try:
                    if get_power_manager().get_idle_seconds() < 10:
                        continue
                except Exception:
                    pass
                _dbg(f"audio retry poll: probing (next delay {delay * 2}s)")
                if reinit_mixer_after_hotplug():
                    self.call_from_thread(setattr, self, "audio_ok", True)
                    boot_log.heartbeat("audio retry poll: mixer came up")
                    return
                delay *= 2
            _dbg("audio retry poll: giving up until an audio hotplug event")
        threading.Thread(target=_poll, daemon=True, name="audio-retry-poll").start()

    # ------------------------------------------------------------------ demo
    def start_demo(self):
        from .demo import DemoPlayer, get_demo_script, get_speed_multiplier
        self.cancel_demo()
        self._demo_player = DemoPlayer(
            dispatch_action=self._dispatch_keyboard_action,
            speed_multiplier=get_speed_multiplier(),
            clear_all=self.clear_all_state,
            clear_art=self.rooms["art"].clear,
            set_music_key_color=self.rooms["music"].set_color_index,
            is_art_paint_mode=lambda: self.rooms["art"].paint_mode,
            set_art_pen=self.rooms["art"].set_pen,
            get_selected_menu_label=self._selected_menu_label,
            get_cursor_position=self._get_cursor_position,
            zoom_events_file=os.environ.get("PURPLE_ZOOM_EVENTS"),
        )
        exit_after = os.environ.get("PURPLE_DEMO_AUTOSTART")

        async def run_demo():
            await self._demo_player.play(get_demo_script())
            self._demo_player = self._demo_task = None
            if exit_after:
                await asyncio.sleep(2.0)
                self.exit()
        self._demo_task = asyncio.create_task(run_demo())

    def _selected_menu_label(self):
        return self.top.selected_item_label() if self.top else None

    def _get_cursor_position(self):
        return self.room.cursor_fraction(self._viewport_rect())

    def cancel_demo(self):
        if self._demo_player:
            self._demo_player.cancel()
            self._demo_player = None
        if self._demo_task:
            self._demo_task.cancel()
            self._demo_task = None

    @property
    def demo_running(self) -> bool:
        return self._demo_player is not None and self._demo_player.is_running

    # ------------------------------------------------------------------ dev
    def _check_screenshot_trigger(self):
        d = os.environ.get("PURPLE_SCREENSHOT_DIR")
        if not d:
            return
        trigger = Path(d) / "trigger"
        if trigger.exists():
            try:
                trigger.unlink()
                n = len(list(Path(d).glob("screenshot_*.png")))
                path = Path(d) / f"screenshot_{n:04d}.png"
                self._draw()
                self.g.save(str(path))
                (Path(d) / "latest.txt").write_text(str(path))
            except OSError:
                pass

    def screenshot(self, path: str):
        self._draw()
        self.g.save(path)

    # ------------------------------------------------------------------ USB / title
    def _tick_usb(self):
        self.invalidate()

    def computer_name(self) -> str:
        if self._computer_name is None:
            self._computer_name = _read(str(Path.home() / ".purple/computer_name.txt")).strip() \
                or _read("/opt/purple/computer_name.txt").strip() or "My Purple Computer"
        return self._computer_name

    def set_computer_name(self, name: str):
        self._computer_name = name
        self.invalidate()

    def _boot_mode_text(self) -> str:
        if not is_live_boot():
            return f"💾 {self.computer_name()}"
        if not is_usb_cached():
            return "🔌 USB" if int(time.monotonic()) % 2 else "USB"
        return "🔌 USB  OK to remove • If restart, reinsert" if is_usb_present() else "🔌 USB  If restart, reinsert"

    def _battery_text(self) -> str:
        from .power_manager import get_power_manager
        pm = get_power_manager()
        if not pm.battery_available:
            return ""
        status = pm.get_battery_status()
        if not status:
            return ""
        pct, charging = status
        return f"⚡{pct}%" if charging else f"🔋{pct}%"

    # ------------------------------------------------------------------ drawing
    def _viewport_rect(self) -> pygame.Rect:
        """The room area: CANVAS_COLS x CANVAS_ROWS square units, as large as
        fit between the title and status strips, so every machine shows the
        same shape and the Art grid fills it edge to edge."""
        g = self.g
        pad, title_h, status_h, legend_w = g.vh(1.2 + FRAME_GAP_VH), g.vh(5), g.vh(6), g.vw(3)
        unit = max(4, min((g.w - 2 * pad - legend_w) // CANVAS_COLS, (g.h - 2 * pad - title_h - status_h) // CANVAS_ROWS))
        vp = pygame.Rect(0, 0, unit * CANVAS_COLS, unit * CANVAS_ROWS)
        vp.center = ((g.w - legend_w) // 2, (title_h - status_h + g.h) // 2)
        return vp

    @property
    def unit(self) -> int:
        """One viewport unit in pixels (an Art cell); panels size themselves in it."""
        return self._viewport_rect().w // CANVAS_COLS

    def _frame_rect(self, vp: pygame.Rect) -> pygame.Rect:
        return vp.inflate(2 * self.g.vh(FRAME_GAP_VH), 2 * self.g.vh(FRAME_GAP_VH))

    def content_rect(self, vp: pygame.Rect) -> pygame.Rect:
        """Room drawing area: the viewport minus any bottom panel."""
        inner = vp.copy()
        if self._panel is not None:
            inner.height -= self._panel.height(self.g)
        return inner

    def _draw(self):
        g = self.g
        g.fill(P.BG)
        vp = self._viewport_rect()
        frame = self._frame_rect(vp)
        self._draw_title(frame)
        g.rect(P.SURFACE, frame)
        g.rect(P.LINE, frame, width=2)
        content = self.content_rect(vp)
        g.surface.set_clip(frame.inflate(-4, -4))
        self.room.draw(g, content)
        if self._panel is not None:
            self._panel.draw(g, pygame.Rect(content.x, content.bottom, content.w, self._panel.height(g)))
        hold = self.hold_progress()
        if hold and hold[0] > 0.12:
            strip_h = g.vh(4.5)
            draw_hold_bar(g, pygame.Rect(content.x, content.bottom - strip_h, content.w, strip_h), hold[0], hold[1])
        g.surface.set_clip(None)
        self._draw_legend(frame)
        self._draw_status(frame)
        for o in self._overlays:
            o.draw(g)
        self._draw_toasts()

    def _draw_title(self, frame):
        g = self.g
        y = frame.y - g.vh(5) // 2
        px = g.vh(1.9)
        g.draw_text(self._boot_mode_text().upper(), px, frame.x, y, "mono-bold", P.MUTED, anchor="midleft", track=TRACK / 2)
        title = f"{ROOM_ICONS[self.active_room]}  {dict(ROOMS)[self.active_room].upper()}"
        g.draw_text(title, g.vh(2.3), frame.centerx, y, "mono-heavy", P.PRIMARY, anchor="center", track=TRACK)
        right = self._battery_text()
        if self._keyboard_state_machine._sticky_shift_active:
            right = "⇧  " + right
        if right:
            g.draw_text(right.upper(), px, frame.right, y, "mono-bold", P.MUTED, anchor="midright", track=TRACK / 2)

    def _draw_legend(self, frame):
        """Sticker colors per keyboard row beside the viewport; a triangle
        points at the row of the last key."""
        if not self._legend_visible:
            return
        g = self.g
        sw, sh = g.vw(0.7), g.vh(2.2)
        x = frame.right + g.vw(0.5)
        y = frame.bottom - 4 * sh
        for r, shades in enumerate(ROW_LEGEND_COLORS):
            for i, color in enumerate(shades):
                g.rect(color, (x + i * sw, y + r * sh, sw, sh))
        if self._legend_row >= 0:
            tx, ty, t = x + 3 * sw + g.vw(0.25), y + self._legend_row * sh + sh // 2, g.vh(0.7)
            pygame.draw.polygon(g.surface, rgb(P.TEXT), [(tx, ty), (tx + t, ty - t), (tx + t, ty + t)])

    def _draw_status(self, frame):
        """The strip under the viewport: keyboard note, Esc and the room
        names (active one in inverse video), arrow hint."""
        g = self.g
        y = frame.bottom + g.vh(6) // 2
        px = g.vh(1.9)
        if self._littles_mode:
            g.draw_text("Littles Mode · Hold Esc to exit", px, frame.centerx, y, "mono", P.MUTED, anchor="center")
            return
        g.draw_text("⌨ Purple is always keyboard only", px, frame.x, y, "mono", P.DIM, anchor="midleft")
        gap = g.vw(1.4)
        tabs = [(label.upper(), rid) for rid, label in ROOMS]
        widths = [g.measure(t, px, "mono-bold", TRACK)[0] + px for t, _ in tabs]
        esc_w = g.measure("ESC", px, "mono-bold", TRACK)[0] + int(px * 0.9)
        x = frame.centerx - (esc_w + gap + sum(widths) + gap * (len(tabs) - 1)) // 2
        x = draw_keycap(g, "Esc", px, x, y).right + gap
        for (label, rid), w in zip(tabs, widths):
            draw_label(g, label, px, x + w // 2, y, P.MUTED, anchor="center", on=rid == self.active_room)
            x += w + gap
        right = ARROW_HINTS[self.active_room]
        if self._effective_volume() == 0:
            right = "🔇  " + right
        g.draw_text(right, px, frame.right, y, "mono", P.DIM, anchor="midright")

    def _draw_toasts(self):
        """A calm centered pill above the status strip, stacking upward, so a
        transient message never lands on top of the room's content."""
        g = self.g
        pad = g.vh(1.1)
        y = g.h - g.vh(11)
        for t in reversed(self._toasts[-3:]):
            r = g.draw_text(t.text, g.vh(2.4), g.w // 2, y, "mono-bold", P.TEXT, anchor="midbottom", bg=P.SURFACE, pad=pad)
            g.rect(P.LINE, r.inflate(pad * 2, pad * 2), width=1)
            y = r.top - pad * 2 - g.vh(1.4)


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


_CRASH_LOG_PATHS = ("/var/log/purple/crash.log", "/tmp/purple-crash.log")


def _write_crash(header: str, exc_type, exc_value, exc_tb):
    import traceback
    from datetime import datetime
    body = f"\n===== {datetime.now().isoformat(timespec='seconds')} {header} =====\n" \
           + "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    for path in _CRASH_LOG_PATHS:
        try:
            with open(path, "a") as f:
                f.write(body)
            return
        except OSError:
            continue


def _install_crash_logger():
    import threading
    prev = sys.excepthook
    sys.excepthook = lambda t, v, tb: (_write_crash("uncaught exception", t, v, tb), prev(t, v, tb))
    prev_thread = threading.excepthook

    def _thread_hook(args):
        _write_crash(f"thread {args.thread.name if args.thread else '?'}", args.exc_type, args.exc_value, args.exc_traceback)
        prev_thread(args)
    threading.excepthook = _thread_hook


def main():
    import signal
    _install_crash_logger()
    if os.environ.get("PURPLE_NO_EVDEV") != "1":
        try:
            check_evdev_available()
        except RuntimeError as e:
            print(f"\n  Purple Computer cannot start:\n  {e}\n", file=sys.stderr)
            sys.exit(1)
    app = PurpleApp(windowed=os.environ.get("PURPLE_WINDOWED") == "1",
                    size=_env_size())
    signal.signal(signal.SIGTERM, lambda s, f: app.exit())
    signal.signal(signal.SIGINT, lambda s, f: app.exit())
    app.run()


def _env_size():
    v = os.environ.get("PURPLE_WINDOW_SIZE", "")
    if "x" in v:
        w, h = v.split("x", 1)
        return int(w), int(h)
    return None


if __name__ == "__main__":
    main()
