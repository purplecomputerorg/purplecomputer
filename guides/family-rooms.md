# Family rooms

A family room is a Python file in a pack (`content/rooms/<name>.py`) that runs as a guest: it asks Purple to draw, speak, and play over a pipe, and Purple decides what actually happens. Families make them in Purple Studio; Purple shows them in a row of their own in the room picker.

## Writing one

```python
from purple import *

snake, heading = [(12, 6)], (1, 0)
TURNS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

def on_key(key):
    global heading
    heading = TURNS.get(key, heading)

def step():
    x, y = snake[0]
    head = ((x + heading[0]) % grid.w, (y + heading[1]) % grid.h)
    snake.insert(0, head)
    grid.erase(snake.pop())
    grid.set(head, "🟩")

every(0.25, step)
```

The top level runs once when the kid comes in. `on_key(key)` runs for every key: a lowercase letter, digit, or symbol, or `space`, `enter`, `backspace`, `up`, `down`, `left`, `right`. Esc always belongs to Purple.

| Call | What happens |
| --- | --- |
| `show(text)` | Big in the middle, replacing what was there |
| `write(text)` | A line of text under the middle; the last few stay |
| `clear()` | Empties the middle, the lines, and the grid |
| `background("#rrggbb")` | The room's color |
| `say(text)` | Purple's voice |
| `play("C4", "marimba")` | A note on marimba, ukulele, accordion, or glockenspiel |
| `drum("snare")` | One of the number-row percussion sounds |
| `ask(prompt)` | Waits for a typed answer and Enter, returns it |
| `grid.set(x, y, thing)` | A square of the 24 by 12 grid holds an emoji, a letter, or a `#rrggbb` color; positions wrap around |
| `grid.get`, `grid.erase`, `grid.clear`, `grid.random_empty` | |
| `every(seconds, fn)`, `after(seconds, fn)` | Timers; `.stop()` on what they return |
| `game_over(text)` | Stops the timers and shows text; the next key starts the room over |

The grid draws when it has anything in it; otherwise the middle text and lines do.

## How it runs

`purple_tui/roomkit/purple.py` is the module rooms import, and the one source of truth: Studio loads the same file into Pyodide. Each host sets `purple._send` and `purple._recv` and calls `purple.run(source)`.

Messages are JSON, one per line.

- Host to room: `{"source": ...}` first (laptop only), then `{"ev": "key", "key": k}`, `{"ev": "tick", "id": n}`, `{"ev": "answer", "text": t}`.
- Room to host: `show`, `write`, `clear`, `background`, `say`, `play`, `drum`, `cell` (`x`, `y`, `thing` or null), `grid_clear`, `every` and `after` (`id`, `seconds`), `stop` (`id`), `ask` (`prompt`), `game_over` (`text`), `done` after the top level and after each event, and `error` (`text`, `line`) as its last word.

The host keeps the time: timers are ticks it sends, so it can pause them when the screen sleeps, when the kid stops pressing keys, and after `game_over`.

## What keeps it safe

The laptop has no network, so the worry is a room that hangs, breaks the laptop, or gets around the parent's settings. Purple handles each without the room's cooperation.

- **Its own process, as its own user.** `canvas/rooms/program_room.py` starts `runner.py` with `sudo -n -u purple-room /usr/bin/python3 -I -S`. `purple-room` has no sudo, no input or audio groups, and no home to write to; the source arrives over stdin, so the room needs to read nothing. The runner caps memory, file size, open files, and processes. Off the ISO (no `purple-room` user) the runner starts as the current user, for development.
- **A time limit per event.** If `done` (or `ask`) doesn't come back within a few seconds, Purple ends the process and shows a calm "this room needs fixing" card. So does an `error`, and so does a flood of messages.
- **Purple draws.** Text goes through `Gfx`, so ALL CAPS and the emoji fallbacks apply. The background can change only a few times a second, sound goes through Purple's volume, and nothing animates once timers pause.
- **Esc always leaves.** The room never sees it.
- **Packs are checked on install.** `pack_manager.py` refuses paths that leave the pack, links, and anything outside the known content layout. A room file is source text; it only ever runs as above.
