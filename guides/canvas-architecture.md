# Canvas architecture

Purple draws its own screen. Since the `ux-experiments` branch (August 2026)
the UI is a pygame window rendered in software; the Textual terminal UI and
Alacritty are gone. This guide is the map for anyone working on the screen.

## Why a canvas

The terminal gave us one cell size for the whole screen, emoji at text
height, and a render path that went Python, ANSI, PTY, Alacritty, llvmpipe,
compositor. It also read as sparse: a large dark box with small type. The
canvas keeps the interaction model exactly (keyboard only, type and things
happen, three rooms, hold gestures) and changes only how big and how physical
the response is.

Design rules, in priority order:

1. Motion only in response to a key. Nothing moves on an idle screen.
2. Text and emoji render smoothly at native resolution, any size per element.
3. A grid exists only where the grid is the content: Music tiles, Art cells.
4. The prompt stays monospace with a block caret. That is the DOS memory.
5. Blockiness is a per-element choice: Art cells and Music tiles have hard
   edges, and a letter written in an Art cell is a block letter (Press
   Start 2P, one glyph per square); everything else is smooth type.
6. Hints sit near the thing they describe and fade after a room has been used.

## Layers

```
purple_tui/gfx.py       Gfx: the surface, fonts, text and emoji caches, markup layout
purple_tui/ui.py        Timers, TextField, Overlay/Dialog/Picker, Toast, draw_ring
purple_tui/app.py       PurpleApp: asyncio loop, readers, dispatch, overlays, frame
purple_tui/panels.py    CodePanel, LoopPanel, TimeTravelBar, SpaceHold
purple_tui/rooms/       PlayRoom, MusicRoom, ArtRoom, parent flows, system screens
purple_tui/play_eval.py The Play evaluator (engine; emits markup strings)
purple_tui/mixer.py     Audio mixer lifecycle (engine)
purple_tui/palette.py   Theme colors and the sticker palette
purple_tui/harness.py   Headless app for previews and tests
purple_tui/sdl_input.py Keyboard from the SDL window when evdev is absent (dev)
```

Engine modules (`keyboard`, `input`, `content`, `color_mixing`, `fuzzy`,
`tts`, `loop_station`, `code_runner`, `timeline`, `power_manager`, ...) are
unchanged from the terminal era and know nothing about drawing.

## Frame model

One asyncio loop. A render task wakes at most 60 times a second and, when
`app.g.dirty` is set, redraws the entire screen and flips. Everything that
changes state calls `app.invalidate()`. There is no dirty-rect tracking:
a full 1366x768 frame costs 1.5 to 3 ms warm on a modern machine and stays
under a keystroke's worth of time on 2006 hardware, because every glyph and
emoji is rasterized once and blitted from a cache (`Gfx.text`, `Gfx.emoji`).

Animations (hold rings, the Music key-change wave, note flashes) are timers
that invalidate at their own rate and stop themselves. `Timers.intervals()`
lists what is armed; `tests/test_performance.py` asserts nothing under one
second ticks while idle in Play.

Sizes come from `g.vh(percent)` and `g.vw(percent)` so a 1024x768 netbook and
a 1440x900 MacBook get the same proportions. The Art grid is a fixed logical
64x36 with `cell = floor(available / rows)` so cells are square everywhere;
unpainted cells alternate two near-identical purples so the grid shows as a
checkerboard rather than lines.

## Text

`Gfx.text(s, px, face, color)` renders one line into a cached surface. Runs
of emoji go through Noto Color Emoji (a bitmap font; rendered at its 109 px
strike and scaled per size). Characters the primary face lacks (arrows,
shapes) fall through to DejaVu Sans, decided per character by a FreeType
coverage probe. ALL CAPS is applied here, so every caller inherits it.

`Gfx.layout` / `Gfx.draw_markup` understand the Rich-style markup the rooms
already speak: `[bold]`, `[dim]`, `[#hex]`, `[on #hex]`, `[/]`, `\[`.
Whitespace-only spans with a background are drawn as square color swatches.
Unknown tags stay literal, so kid input never breaks rendering
(`tests/test_play_markup_safety.py`).

## Input

Unchanged: evdev events go through `KeyboardStateMachine` into
`app._dispatch_keyboard_action`, which the demo player also feeds. When there
is no evdev (`PURPLE_NO_EVDEV=1`, macOS), `sdl_input.pump` turns the window's
key events into the same `RawKeyEvent`s.

Hold gestures show a ring (`ui.draw_ring`): Esc for the Parent Menu, Space for
the code panel, Enter for the loop station. `panels.SpaceHold` holds the tap
versus hold policy Music and Art share.

## Overlays

`app.push(overlay, on_close)` stacks an `Overlay`; the top one owns the
keyboard. `Dialog` is a centered box, `Picker` an up/down option list,
`FullScreen` (in `rooms/sleep_screen.py`) a whole-screen message. Escape in a
picker closes with `escape_value`; `ui.CANCELLED` is the sentinel for "closed
without choosing" where `None` is itself a valid choice.

## Boot

`xinitrc` starts X, matchbox, picom, then `/usr/local/bin/purple`, which execs
`python3 -m purple_tui`. The app opens a fullscreen SDL window on the X
session. `LIBGL_ALWAYS_SOFTWARE=1` stays exported so nothing touches a GPU
driver that lies; the app itself never asks for GL. The UI-ready marker
(`/tmp/purple-ui-ready`) is touched after the first frame, which is what
gates the compositor start.

Terminal mode from the Parent Menu is a VT switch to tty2 (the same path as
Ctrl+Alt+F2); the install flow ends on an in-app "All done" screen and
execs `purple-reboot` on Enter.

## Working on it

- `just run-dev` opens a window on a dev machine (SDL keyboard, no evdev).
- `just preview art type:hello key:tab type:hi` renders a PNG headlessly.
- `purple_tui.harness.make_app()` gives tests a headless app; `press` and
  `type_text` drive it through the real dispatcher.
- `tests/test_render_smoke.py` draws every screen at three sizes.
