import random

from purple import *

# Memory for two players taking turns, laid out like the Music room: each card is a letter key. Press a
# card's letter to turn it over. Find a pair and you go again.

# The pictures on the cards, two of each: your family's favorite things. Up to 13 fit, and every game shuffles them onto the letter keys, so their order here doesn't matter.
CARDS = ["🐶", "🐱", "🦕", "🚂", "🍓", "🌈", "🚀", "🐢", "🍦"]
# The two players: each one's mark and name.
# Labels: mark, name
PLAYERS = (("🔴", "Red"), ("🔵", "Blue"))

# Each row of keys and its color, the same as the Music room's.
rows = (("qwertyuiop", "#e44444"), ("asdfghjkl", "#e2c63a"), ("zxcvbnm", "#2e6ae1"))
spots = {key: (2 + x * 2, 4 + r * 2, color) for r, (keys, color) in enumerate(rows) for x, key in enumerate(keys)}
cards = CARDS[:13] * 2
random.shuffle(cards)
faces = dict(zip(spots, cards))
shown = set()      # cards matched for good
up = []            # the one or two cards turned over this turn
game = state(turn=0)


def draw():
    for key, face in faces.items():
        x, y, color = spots[key]
        if key in shown or key in up:
            grid.floor.set(x, y, color, size=2)
            grid.set(x, y, face, size=2)
        else:
            grid.floor.erase(x, y)
            grid.set(x, y, key.upper(), size=2)
    mark, name = PLAYERS[game.turn]
    status(f"{mark} {name}'s turn")


def turn_back():
    up.clear()
    game.turn = 1 - game.turn
    draw()


def on_key(key):
    if key in faces and len(up) < 2 and key not in shown and key not in up:
        up.append(key)
        play("E5")
        if len(up) == 2 and faces[up[0]] == faces[up[1]]:
            shown.update(up)
            up.clear()
            play("G5")
        elif len(up) == 2:
            after(1.5, turn_back)
    draw()
    if len(shown) == len(faces):
        play("C5")
        game_over("All the pairs! Press a key to play again.")


draw()
