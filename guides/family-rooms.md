# Family rooms

A family room is a Python file in a pack (`content/rooms/<name>.py`) that runs as a guest: Purple sends it events, it answers each with what to draw and play, and Purple decides what actually happens. Families make them in Purple Studio; Purple shows them in a row of their own in the room picker once a parent turns them on.

The design goal is that how rooms get built (blocks, forms, Python, sprites, whatever comes next) can change in Studio for years without a new Purple Key. So Purple's side is a small fixed protocol, and everything that makes a room a room lives in the guest library, `purple_tui/roomkit/purple.py`, which each pack carries. Reasoning and the decisions behind it: `docs/PLAN-room-interface.md`.

## Writing one

Everything a room can call, with the starter rooms, is Studio's Room guide: `studio/src/room-guide.md`, which Studio shows as a page and copies whole for a parent to hand to an AI helper. It is the one description of the room language; keep it in step with `roomkit/purple.py` (`studio/tests/guide.test.ts` checks the drums, keys, grid size, and starters). The starters are `studio/src/examples/*.py`, each a kind of room families asked for in the 2.0 survey: a world to walk around, a garden, a beat maker, memory for two, a story with choices, and Snake.

## The protocol

One JSON line each way, strictly in turn: Purple sends an event, the room sends exactly one reply, and only then does Purple send the next event. The host is `purple_tui/canvas/rooms/family_room.py`; the guest side is `roomkit/runner.py` (which loads the library) and `roomkit/purple.py`.

Purple to room:

| Event | Fields |
| --- | --- |
| `start` | `api` (2), `size` (`[240, 120]`), `keep`, `lib` (the library's source), `source` (the room's), `images` (each pack picture's `[width, height]`), `sounds` (the pack's sound names) |
| `key` | `key` as above; `char`, the character as typed, for letters and symbols |
| `keyup` | `key`, for every `key` Purple sent; when something covers the room, every held key goes up |
| `tick` | nothing more |

Every event also carries `t`, the room's clock in seconds, which stops while the room is paused.

Room to Purple, every field optional:

| Field | Meaning |
| --- | --- |
| `scene` | The whole screen as a list of shapes; absent means unchanged |
| `sounds` | `["say", text]`, `["note", "C4", instrument]`, `["drum", name]`, `["clip", name]` (the pack's `sounds/<name>.wav`), at most 8; a reply's `say`s are spoken in order, cutting off speech from before |
| `wake` | Seconds until the room wants a `tick`; absent or null means no ticks |
| `keep` | The object to remember; absent means unchanged |
| `error` | `{text, line}`; the room has stopped |

Shapes are on a 240 by 120 surface that fills the room's viewport, floats allowed: `["rect", x, y, w, h, color, radius, line]` (`line` above 0 draws only an outline that thick), `["text", x, y, size, text, color, how]`, and `["image", x, y, w, h, source]`. A text's optional `how` is `{anchor, width, height, box, pad, radius}`: `anchor` says which point of the text sits at (x, y) (`center`, the default, `left`, `right`, `top`, `bottom`, `topleft`, `topright`, `bottomleft`, `bottomright`); with `width` Purple wraps it at that width, without one a line too wide for the surface shrinks to fit; with `height` it shrinks until it fits that tall; `box` is a color drawn behind it, `pad` beyond the text, with rounded corners of `radius`. Purple lays text out in its own font, so the library never measures, and draws it as typed (markup like `[bold]` stays text). An image's source is a pack picture's name or `{"rows": [...], "palette": {char: color}}`, at most 64 by 64; Purple stretches it to the box, blocky when it grows at least twice, smooth otherwise. A color is `#rrggbb` or a palette role (`text`, `accent`, `muted`, `surface`, and the rest of `canvas/theme.ROLES`), so rooms follow the family's theme.

Purple skips fields, shapes, and sounds it doesn't know, so a newer library still runs on an older Purple; the library reads `api` to know what it can ask for. Never change what an existing field means: rooms on Keys already out there depend on it. `just room-compat` runs this checkout's library and rooms on a release's host to catch that.

## How the library ships

Studio writes `content/rooms/purple.py` into every pack with rooms: the library as it was when the pack was built. Purple sends that file as `lib`, or its own built-in copy for a pack without one, and the runner execs it as the `purple` module. Each pack runs on its own library, so packs never affect each other, and `purple` is not a room name. New room features (sprites, a Blockly runtime, a quiz engine) are library changes and reach every Key with the next pack.

## What keeps it safe

The worry is a room that hangs, breaks the laptop, gets around the parent's settings, or shows something the parent didn't choose. Purple handles each without the room's cooperation.

- **Only rooms a parent turned on.** A room shows in the picker only after a parent turns it on in the Parent Menu's Family Rooms list. Purple remembers a hash of the room and its library (`Room.digest`), so a changed room, or another pack with the same name, is off until turned on again. Studio's live preview turns on what the parent made there.
- **A sealed process.** On the ISO, `family_room.py` runs `sudo -n /usr/local/bin/purple-room-run` (`scripts/purple-room-run.sh`, the only command the sudoers rule allows), which starts `runner.py` with `systemd-run` as the `purple-room` user: no network or sockets, no devices, no home folders or USB drives, nothing under `/run`, a read-only system, a 1 MB `/tmp`, 256 MB of memory, 16 processes, and the system calls a plain Python program needs. The runner adds rlimits as a second layer. Off the ISO the runner starts as the current user, for development.
- **Purple lets go, the room ends.** Killing `sudo` or `systemd-run` doesn't reach a process in its own unit, so the runner forks: the parent waits for Purple's end of stdin to close and then kills the room.
- **A time limit per event.** If a reply doesn't come within a few seconds, Purple ends the room and shows a calm "this room needs fixing" card. So does an `error`, a reply over 256 KB or with more than 1000 shapes, anything that isn't a reply, or a reply nobody asked for.
- **No flashing.** After drawing a scene, Purple shrinks it to 16 by 8 tiles; a scene that changes the brightness of a quarter of them shows at most three times a second, and in between the newest scene waits. Small changes are never held back. This is on the drawn result, so no combination of shapes gets around it.
- **Purple draws and plays.** Text goes through `Gfx`, so ALL CAPS and the emoji fallbacks apply; sound goes through Purple's volume and speech through its speech filter. Ticks stop while a menu covers the room, after three minutes without a key, and while the screen sleeps.
- **Esc always leaves.** The room never sees it.
- **Packs are checked on install.** `pack_manager.py` refuses paths that leave the pack, links, and code anywhere but `rooms/<name>.py` and `rooms/purple.py`. Those are source text that only ever run as above. A room draws and plays only its own pack's `images/` and `sounds/`, which Purple reads; the room never sees a file.

## Performance

Each scene is drawn once into a picture when it arrives, and every frame after just copies it, so a full grid costs the same as an empty one. Pictures are decoded and scaled once per size, so a screen of 300 sprites redrawn 30 times a second costs about 1.5 ms a frame on a current laptop. A full 24 by 12 grid is about 14 KB of JSON and a fraction of a millisecond to decode on a current laptop. The library sends `scene` only when it changed, so a room waiting for a key sends almost nothing, and ticks wait for the reply, so a slow room slows only itself.

## Studio

Studio's Rooms page runs the room on the real Purple in its preview: `FamilyRoom` itself, with the room in a Web Worker in place of a process (`studio/src/rooms/guests.ts`, swapped in by `studio/src/live/browser.py`). The worker runs `runner.serve` behind an import wall (`studio/src/rooms/guest.py`) and the page's CSP keeps it off the network. What a parent sees there is what the kid gets, limits included. The room being tried draws and plays its pack's pictures and sounds (`live.py` links them beside it). Studio opens a pack it didn't make (no `studio.json`), by hand or by an AI helper, as its rooms with their pictures and sounds, so a hand-made room can be tried before it goes on a USB drive.

## The room checker

`purple_tui/roomkit/check.py` plays a pack's rooms the way Purple does, without Purple: `check_pack` first, then each room in its own process with the real library, on a clock it moves itself, through arrows, typing, a few hundred random keys, and 20 seconds of timers. It reports what would put up the "needs fixing" card (an error and its line, a slow answer, too many shapes, a picture the pack lacks) and `--show` prints the screen as text. It holds rooms to the same numbers Purple does, `roomkit/limits.py`. `just studio-bundle` builds it with the pack rules and the library into one file anyone with Python 3.10 can run, served by Studio at `/purple/purple-room-check.pyz`; the Room guide points AI helpers at it. In this repo: `just python -m purple_tui.roomkit.check <pack>`.
