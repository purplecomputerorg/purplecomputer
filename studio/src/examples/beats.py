from purple import *

# A beat maker on the keyboard: each row of keys is a drum, and each key in it a beat. Press a key to
# turn its beat on or off, and Space to start and stop the music.

# The drums, top row of keys to bottom: the picture for each and the drum it plays.
ROWS = (("🐘", "kick"), ("🐸", "snare"), ("🐝", "hi-hat"), ("👏", "clap"))
# Seconds from one beat to the next: smaller is faster.
SPEED = 0.2

KEYS = ("12345678", "qwertyui", "asdfghjk", "zxcvbnm,")
spots = {key: (r, c, (4 + c * 2 + r, 1 + r * 3)) for r, row in enumerate(KEYS) for c, key in enumerate(row)}
beats = set()
game = state(at=-1, loop=None)


def square(key):
    r, c, spot = spots[key]
    grid.floor.set(spot, "line" if c == game.at else "tile", size=2)
    grid.set(spot, ROWS[r][0] if key in beats else key.upper(), size=2)


def draw():
    for key in spots:
        square(key)


def tick():
    game.at = (game.at + 1) % len(KEYS[0])
    draw()
    for key in beats:
        r, c, _ = spots[key]
        if c == game.at:
            drum(ROWS[r][1])


def on_key(key):
    if key in spots:
        if key in beats:
            beats.remove(key)
        else:
            beats.add(key)
            drum(ROWS[spots[key][0]][1])
        square(key)
    elif key == "space" and game.loop:
        game.loop.stop()
        game.loop, game.at = None, -1
        draw()
    elif key == "space":
        game.loop = every(SPEED, tick)


for r, (animal, _) in enumerate(ROWS):
    grid.set(1 + r, 1 + r * 3, animal, size=2)
draw()
status("Press a key for a beat. Space plays.")
