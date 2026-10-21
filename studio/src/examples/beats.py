from purple import *

# A beat maker laid out like the Music room: each row of keys is a drum, and each key in it a beat. Press
# a key to turn its beat on or off, and Space to start and stop the music.

# The drums, top row of keys to bottom: the picture for each, the drum it plays (Purple's or one of your sounds), and its color.
# Labels: picture, drum, color
DRUMS = (("🐘", "kick", "#a0a0a0"), ("🐸", "snare", "#e44444"), ("🐝", "hi-hat", "#e2c63a"), ("👏", "clap", "#2e6ae1"))
# Seconds from one beat to the next: smaller is faster.
SPEED = 0.2

keys = ("12345678", "qwertyui", "asdfghjk", "zxcvbnm,")
spots = {key: (r, c, (5 + c * 2, 2 + r * 2)) for r, row in enumerate(keys) for c, key in enumerate(row)}
beats = set()
game = state(at=-1, loop=None)


def square(key):
    r, c, spot = spots[key]
    if key in beats:
        grid.floor.set(spot, DRUMS[r][2], size=2)
        grid.set(spot, DRUMS[r][0], size=2)
        return
    grid.floor.erase(spot)
    if c == game.at:
        grid.floor.set(spot, "line", size=2)
    grid.set(spot, key.upper(), size=2)


def draw():
    for key in spots:
        square(key)


def tick():
    game.at = (game.at + 1) % len(keys[0])
    draw()
    for key in beats:
        r, c, _ = spots[key]
        if c == game.at:
            drum(DRUMS[r][1])


def on_key(key):
    if key in spots:
        if key in beats:
            beats.remove(key)
        else:
            beats.add(key)
            drum(DRUMS[spots[key][0]][1])
        square(key)
    elif key == "space" and game.loop:
        game.loop.stop()
        game.loop, game.at = None, -1
        draw()
    elif key == "space":
        game.loop = every(SPEED, tick)


for r, (picture, _, _) in enumerate(DRUMS):
    grid.set(2, 2 + r * 2, picture, size=2)
draw()
status("Press a key for a beat. Space plays.")
