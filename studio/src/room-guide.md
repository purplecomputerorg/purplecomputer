# Making a room for Purple Computer

A **room** is a small Python program your family adds to Purple Computer: a game, a story, a toy. Your kid finds it next to Purple's own rooms and plays it with the keyboard. Rooms come in a **Purple Pack**, the file Purple Studio downloads.

You can make one on Purple Studio's Rooms page (from a form, from blocks, or by changing a starter room), or have an AI helper write it. This guide is everything either of you needs. If you are an AI helping a parent: write the room, check it with the room checker (near the end), and then tell the parent how to try it in Purple Studio and put it on Purple.

## A room

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

The top of the file runs once when your kid comes in. After that, Purple calls:

- `on_key(key)` once each time a key goes down. `key` is a lowercase letter (`"a"`), a digit, a symbol (the key itself, so `"1"` for `!` and `"/"` for `?`), or `"space"`, `"enter"`, `"backspace"`, `"up"`, `"down"`, `"left"`, `"right"`. Holding a key down does not repeat it.
- `on_key_up(key)` when that key comes back up. `held(key)` says whether a key is down right now: to keep walking while an arrow is held, check `held()` from a timer.
- The functions you gave to `every` and `after`.

Esc always belongs to Purple: it leaves the room, and your room never sees it.

## What a room can call

| Call | What happens |
| --- | --- |
| `show(thing)` | Big in the middle, replacing what was there: text, an emoji, or a picture. Long text wraps and shrinks to fit. |
| `write(text)` | A line of text under the middle. The last 5 stay, good for stories and questions. |
| `status(text)` | A line along the top, for a score or what to do next. `status()` takes it away. |
| `clear()` | Empties the screen: the middle, the lines, the top line, and the grid. |
| `background("#2a1845")` | The room's color, written as # and six letters or numbers. |
| `say(text)` | Purple says it out loud. Everything said in one key or timer is spoken in order; the next key's `say` cuts off anything still being said. Notes, drums, and sounds play at the same time as speech. |
| `play("C4", "marimba")` | A note from C2 to C6, sharps like `"F#4"`. Instruments: marimba, ukulele, accordion, glockenspiel, or one made in this pack. |
| `drum("snare")` | kick, snare, hi-hat, clap, cowbell, woodblock, triangle, tambourine, bongo, or gong. |
| `sound("meow")` | One of the pack's own sounds. |
| `ask("Your name?")` | Waits for your kid to type an answer and press Enter, then gives back what they typed. Timers wait too. |
| `grid.set(x, y, thing)` | Puts something in a square of the grid (below). `grid.set((x, y), thing)` works too. |
| `grid.get(x, y)`, `grid.erase(x, y)`, `grid.clear()` | What's in a square, empty one, or empty the whole grid, its floor and cursor too. |
| `grid.random_empty()` | An `(x, y)` with nothing in it, or `None` when the grid is full. |
| `grid.floor.set(x, y, thing)` | The floor under the grid: grass under a hero, soil under a plant. It has `get`, `erase`, and `clear` too. |
| `grid.cursor(x, y)` | A ring around a square, to show what's picked. `grid.cursor()` takes it away. |
| `picture("cat")` | One of the pack's pictures, for `grid.set` or `show`. |
| `pixels(rows, colors)` | A small picture written as letters (below). |
| `every(seconds, fn)`, `after(seconds, fn)` | Call `fn` over and over, or once, at least 0.1 seconds apart. Both give back a timer you can `.stop()`. |
| `game_over(text)` | Stops the timers and shows the text. The next key starts the room over from the top, with fresh variables; `keep` stays. |
| `keep` | A dict Purple remembers for next time: `keep["best"] = 12`. Words, numbers, lists, and dicts, up to 4 KB. Purple saves it when your kid leaves the room. |
| `images`, `sounds` | The pack's picture names (each with its size in pixels) and sound names. |

A mistake, like `drum("snar")` or a picture the pack doesn't have, stops the room with a message saying which line it's on.

## The screen

The screen is a **grid of 24 by 12 squares**. `(0, 0)` is the top left, and `grid.w` and `grid.h` are 24 and 12. Going off one edge comes back on the other, so `x = 24` is `x = 0`. A square holds one of:

- an emoji or a letter: `grid.set(3, 4, "🌻")`
- a color: `grid.set(3, 4, "#2f9e44")`
- a picture: `grid.set(3, 4, picture("cat"))`

An emoji, letter, or color can cover more than one square: `grid.set(3, 4, "🐶", size=2)` is 2 by 2 squares, from (3, 4) right and down. A picture covers as many as you ask for: `picture("cat", 4)` is 4 squares wide and as tall as its shape needs, and `picture("cat", 4, 3)` is 4 by 3. A big thing belongs to its top-left square: `grid.get` and `grid.erase` use that square, and the others stay empty. It doesn't wrap around, so keep it on the screen.

The floor sits under the grid, so a hero standing on grass is `grid.floor.set(x, y, "#4f9d4a")` and `grid.set(x, y, "🧒")`. Moving the hero only changes the grid; the grass stays.

`show()` and `write()` work with or without the grid: over the grid, they sit in a box so they're easy to read. `status()` covers the top row, so leave row 0 free in a game that uses it. When the grid is empty, `show()` is in the middle and `write()` lines are under it. `ask()` and `game_over()` show along the bottom.

Purple draws everything after each key and timer, so there's no drawing to do yourself: change the grid or the text, and it shows.

A world bigger than the screen: keep the whole map in a list of strings, and after each move `grid.clear()` and set the 24 by 12 part around the hero. Redrawing every square is fine; Purple only shows what changed.

### Pixel pictures

`pixels` draws 8-bit style pictures without any picture files. Each string is a row; each letter is a color from the dict, and any other character (like `.`) is see-through:

```python
HERO = pixels([
    "..HH..",
    ".HSSH.",
    "..SS..",
    ".GGGG.",
    "..G.G.",
], {"H": "#6b3e1e", "S": "#f2c49b", "G": "#2f9e44"})
grid.set(5, 5, HERO)
```

Up to 64 by 64 letters, and one color dict can serve many pictures. A letter missing from the dict is see-through too, so check the spelling when part of a picture vanishes. `pixels(rows, colors, 2)` makes it 2 squares wide. Small pictures drawn big stay crisp and blocky; big photos are smoothed.

## Pictures and sounds of your own

A photo of your pet, a recording of Grandma saying hello: in Purple Studio, add them on the Rooms page under "Pictures and sounds for your rooms", and every room in the pack can use them by name, `picture("biscuit")` and `sound("hello")`. Studio turns any photo or recording into what Purple needs.

In a pack made by hand, they are files: `content/images/<name>.png` (PNG, at most 1024 pixels a side and 1 MB) and `content/sounds/<name>.wav` (WAV, 22050 Hz, mono, 16-bit). Names are lowercase letters, digits, `-` and `_`, up to 40 characters.

To make a sound with Python's standard library:

```python
import math, struct, wave

def tone(path, freq, seconds=0.2):
    rate = 22050
    frames = [int(12000 * math.sin(2 * math.pi * freq * t / rate) * (1 - t / (rate * seconds)))
              for t in range(int(rate * seconds))]
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))
```

## How rooms run

Each room runs sealed off from the rest of the computer: no files, no internet, no other programs, and nothing can be installed. Python's own pure modules (`random`, `math`, `itertools`, `collections`, `dataclasses`, and so on) work. A room uses its pack's pictures and sounds by name; it never sees the files.

Each key or timer has to finish within 3 seconds, and starting within 8. A room that raises an error, takes too long, or draws more than 1000 things at once (a full grid with a full floor is under 600) is stopped, and your kid sees a calm "this room needs fixing" card. The rest of Purple keeps working.

Purple won't let the screen flash: a change that brightens or darkens a big part of the screen shows at most three times a second. Timers rest after three minutes without a key, and while a menu is open.

## Making it good for kids

- Many kids playing can't read yet. Use emoji, colors, and pictures, and `say()` anything important.
- Every key should do something friendly, or nothing. Don't punish a wrong key.
- Keep goals short. When a round ends, say so warmly, and start again on a key.
- No timers that make a kid lose by being slow, unless the game is about being quick and your kid asked for it.
- Arrows to move, Space or Enter to act, letters and numbers as themselves: those are the keys kids know.
- Calm beats busy. Purple is a quiet place.

## Starter rooms

Studio's Rooms page has these to start from, each one a different kind of room: a world to walk around, a garden, a beat maker, memory for two players, a story with choices, and Snake, the smallest game. Their Python is at the end of this guide; reading one is the quickest way to see how the calls fit together.

## A Purple Pack made by hand

Studio makes the pack for you. To make one without Studio, make a folder:

```
my-pack/
  manifest.json
  content/
    rooms/
      garden.py          one file per room
    images/
      biscuit.png        pictures the rooms draw (optional)
    sounds/
      hello.wav          sounds the rooms play (optional)
```

`manifest.json`:

```json
{"id": "pack-garden", "name": "Our Garden", "version": "1.0.0", "type": "emoji", "format": 1}
```

`id` is a plain name (letters, digits, dashes); a pack with the same `id` replaces the old one. `version` is like `1.0.0`. Keep `"type": "emoji"`.

Room files are `content/rooms/<name>.py`: lowercase letters, digits, and dashes, never `purple`. Purple shows the name with capitals, so `space-rescue` is "Space Rescue". Each is UTF-8 text, at most 64 KB. Purple refuses a pack with any other code in it, so leave out `__pycache__` folders.

A `.purplepack` is the folder's contents as a gzipped tar, with `manifest.json` and `content/` at the top:

```
tar czf garden.purplepack --exclude=__pycache__ -C my-pack manifest.json content
```

## Trying it before it goes on Purple

- **In Purple Studio:** on the Rooms page, choose "Open it here" and pick the `.purplepack`. Its rooms run on the real Purple right there in your browser, with their pictures and sounds, and you can change them and download the pack again.
- **With the room checker:** download `https://studio.purplecomputer.org/purple/purple-room-check.pyz` and run `python3 purple-room-check.pyz my-pack` (a folder or a `.purplepack`; Python 3.10 or newer). It checks the pack the way Purple does, then plays each room with a few hundred keys on a fast clock, and says what would stop it and on which line. `--show --keys "right right space"` prints the screen as text after each key, with the sounds and speech it made; each picture shows as a letter, named under the grid. `--room garden` tries just one room. The checker finds what would stop a room, not whether the game can be won: walk through the important parts yourself with `--show`.

## Putting it on Purple Computer

Copy the `.purplepack` file to the top folder of any USB drive (your Purple Key works too) and plug it into Purple Computer. Purple checks the pack and asks to add it: choose Add. Then, in the Parent Menu's Family Rooms list, turn the room on, and it shows in your kid's room picker.
