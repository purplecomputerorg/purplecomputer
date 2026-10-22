# Plan: a room interface that outlives the 2.0 Key

Goal: after 2.0 ships, how families build rooms (Blockly, forms, Python, sprites, whatever comes next) changes in Studio alone, and no Key needs reflashing. Linear: PUR-38. The protocol and the safety rules as built are in `guides/family-rooms.md`; this page is why they look the way they do, and what's left.

## The idea

Purple keeps only what a sandboxed process can't do itself: a screen, a speaker, a voice, a keyboard, a clock, and a small notebook (`keep`). Everything that makes a room a *room* (the grid, `show`, `ask`, timers, `game_over`, a Pygame Zero layer later) lives in the guest library, `purple_tui/roomkit/purple.py`, and every pack carries its own copy as `content/rooms/purple.py`. The Key freezes a protocol with nothing left to grow: four events in, one reply out with five optional fields, three shapes, four sounds.

Two rules keep it simple:

1. **One message each way, in turn.** Purple sends an event; the room answers with exactly one reply. The old protocol was already lockstep (Purple waited for `done`), so this folds a stream into one message and drops `done`, timer ids, and flood counting. A room can't speak unprompted, which is what lets Purple pause it completely.
2. **The reply is the whole scene.** Purple keeps no room state, so it can't drift out of step with a library it has never seen; a library sends `scene` only when it changed.

## Decisions

- **Drawing shapes, not pixels or widgets.** Widgets (the old `show`, `grid`) put room ideas in the OS. Pixels would need a second text and emoji renderer in the guest and heavy frames through a pipe on old laptops, and Purple couldn't apply its text rules. `rect` and `text` are enough to build the rest in the library, and Purple still draws every glyph.
- **`keyup`, `image`, and `clip`, from the 2.0 survey.** Families asked for a Zelda-like dungeon, a garden, a text adventure, card games, and a game about their late cat. Five games written blind in plain Pygame Zero ran unchanged on Purple's host through a Pygame Zero layer in the library, and what they couldn't do without the host was hold a key down (3 of 5), play their own sounds (5 of 5), and draw their own pictures (3 of 5). So `key` names the physical key and a `keyup` follows it, and a pack's `images/*.png` and `sounds/*.wav` are drawn and played by name, Purple opening the files and telling the room only each picture's size. An `image` can instead carry small inline pixels (64 by 64 at most), the fallback for a library that wants to draw something itself. What remains for the library: polygons.
- **The surface is 240 by 120** and fills the 48 by 24 unit viewport exactly, so a grid cell is 10 units.
- **Every event carries `t`**, the room's clock, which stops while the room is paused, so timers don't jump after a menu or a rest. **Key events carry `char`**, the character as typed, so `ask()` keeps capitals; `key` stays lowercase.
- **Purple lays out text.** The library can't measure text in Purple's font, so a text shape says where it goes and how much room it has (an anchor, a width to wrap at, a height to shrink into, a box behind it) and Purple fits it with `Gfx.layout`. That replaced guessing character widths (what the Pygame Zero layer did) and a measuring call in the protocol.
- **A second blind test, written from the author doc alone (2026-10-19).** Six agents built the survey's games (a dungeon, a garden, a beat sequencer, a text adventure, card games, a pet game) from a one-page doc without seeing Purple's code. All six installed and ran 3,200 random keys with no faults. What they hit: no way to try a room before the USB step (6 of 6), no text beside a grid game (5), one thing per square (4), pictures always one square, and a few unclear doc points. So: the room checker and Studio opening hand-made packs; `status()` and boxed `show()`/`write()` over the grid; `grid.floor`, `grid.cursor`, and `size=`; pictures any number of squares and `show(picture)`; clear errors for an unknown drum, note, or sound; a reply's `say`s spoken in order; and the doc became Studio's Room guide with five starter rooms, one per kind of room asked for.
- **`keep` stays.** It's the one thing no library could add later, since rooms can't write files. 4 KB of JSON per room, written by Purple when the room closes, beside the kid's saves.
- **Approval by hash.** A parent turns each room on in the Parent Menu; Purple stores a hash of the room and its library, so a changed room, or another pack's room with the same name, waits again. This replaced the single "Show Family Rooms" switch.
- **The sealed launcher is a script** (`scripts/purple-room-run.sh`, installed as `/usr/local/bin/purple-room-run`), so the sudoers rule allows one command with no arguments and the sandbox lives in one readable place. Two findings while building it, both checked on systemd 258: `RestrictAddressFamilies=none` is refused for transient units, so sockets are blocked with `SystemCallFilter=~@network-io` (returning EPERM, so a room gets a clear error instead of dying) and `/run` is an empty tmpfs (hiding it with `InaccessiblePaths` fails the namespace with status 226 on the live ISO); and killing `systemd-run` does not stop the unit, so `runner.py` forks and its parent ends the room when Purple closes stdin.
- **Flashes are judged on the drawn result**, 16 by 8 tiles of luminance, at most three big changes a second. It replaces the old background-only limit and covers any shape a future library sends.
- **Identical scenes are skipped after decoding, not before.** Comparing raw reply text would also drop a repeated sound (pressing the same soundboard key twice), so Purple compares the decoded scene with the one on screen and skips the redraw.
- **One host.** Studio's Rooms page runs Purple's own `FamilyRoom` in the live preview, with the room in a Web Worker; Studio's separate host (`host.ts`) and stage drawing are gone.

## Performance

Each scene is drawn once into a picture and copied each frame after, so a full grid costs the same as an empty one. Measured on a Ryzen 6600U, JSON for a reply: a 40-cell snake is 1.9 KB and 0.02 ms each way, a full grid 13.5 KB and 0.15 ms, the 1000-shape cap about 47 KB and 0.5 ms (scaled from a 3000-shape run). Plan on 5 to 10 times that on the oldest laptops.

## Status (2026-10-13)

Built on the purplestudio branch, all tests passing (Python, Studio's vitest, and the Rooms page checked in a headless browser):

1. The library, runner, and host on the new protocol, with the render-once drawing, flash limit, `keep`, and caps (1000 shapes, 256 KB replies, 8 sounds, wake at least 1/30 s).
2. Pack rules: `content/rooms/purple.py` allowed and checked; `purple` reserved as a room name; Studio's SDK writes the library into every pack with rooms.
3. Studio's Rooms page on the live Purple.
4. Parent approval (A): the Parent Menu's Family Rooms list.
5. The sealed process (B), smoke-tested in user mode here (no root, so without `User=`).
6. `just room-compat [ref]`: this checkout's library and rooms (`tests/rooms/`, Studio's examples) on another ref's host. Run it against `release/2.x` once that branch exists, and before every Studio release after.
7. Docs: `guides/family-rooms.md`, `studio/PACK_FORMAT.md`, the SDK and Studio READMEs, Studio's Room guide.

Still to do, before 2.0:

- **On real hardware:** time a room's start through `purple-room-run` on the slowest supported laptop against `START_TIMEOUT_S` (8 s), and a full-grid scene plus the flash check at 10 updates a second. Confirm the i386 image's systemd accepts every property in `purple-room-run.sh` (a refused property shows "needs fixing", never anything worse).
- **D, an outside review:** someone outside tries to get out of a room, with a write-up, before any "completely safe" claim. The scoped wording to use then: "Rooms are completely safe: a room can't go online, can't change anything on the computer, and only rooms you've added yourself will ever run."

## Keeping the promise after 2.0

- Never change what an existing protocol field means; only add fields Purple can ignore.
- The pack format stays `format: 1`. Only add optional files.
- Studio versions its `.studio.json` (rules and forms) and migrates old ones when they change, so parents' rooms reopen.
