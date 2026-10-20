import random

from purple import *

# Memory for two players taking turns. The cards sit where their keys are on the keyboard: press a
# card's letter to turn it over. Find a pair and you go again.

# The pictures on the cards, two of each: your family's favorite things. Up to 13 fit.
CARDS = ["🐶", "🐱", "🦕", "🚂", "🍓", "🌈", "🚀", "🐢", "🍦"]
# The two players: each one's mark and name.
PLAYERS = (("🔴", "Red"), ("🔵", "Blue"))

KEYS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
spots = {key: (2 + x * 2 + r, 2 + r * 3) for r, row in enumerate(KEYS) for x, key in enumerate(row)}
cards = CARDS[:13] * 2
random.shuffle(cards)
faces = dict(zip(spots, cards))
shown = set()      # cards matched for good
up = []            # the one or two cards turned over this turn
game = state(turn=0)


def draw():
    for key, face in faces.items():
        face_up = key in shown or key in up
        grid.floor.set(spots[key], "primary" if face_up else "tile", size=2)
        grid.set(spots[key], face if face_up else key.upper(), size=2)
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
