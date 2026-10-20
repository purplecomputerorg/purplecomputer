import random

from purple import *

# Memory for two players taking turns. Arrows pick a card, Space turns it over. Find a pair and
# you go again.

# The pictures on the cards, two of each: your family's favorite things.
CARDS = ["🐶", "🐱", "🦕", "🚂", "🍓", "🌈", "🚀", "🐢", "🍦"]
# The two players: each one's mark and name.
PLAYERS = [("🔴", "Red"), ("🔵", "Blue")]
# The back of a card.
BACK = "🟪"

spots = [(3 + c * 3, 2 + r * 3) for r in range(3) for c in range(6)][:len(CARDS) * 2]
faces = CARDS * 2
random.shuffle(faces)
shown = set()      # cards matched for good
up = []            # the one or two cards turned over this turn
pick, turn = 0, 0


def draw():
    for i, spot in enumerate(spots):
        grid.set(spot, faces[i] if i in shown or i in up else BACK, size=2)
    grid.cursor(spots[pick])
    mark, name = PLAYERS[turn]
    status(f"{mark} {name}'s turn")


def turn_back():
    global turn
    up.clear()
    turn = 1 - turn
    draw()


def on_key(key):
    global pick
    if key in ("left", "right", "up", "down") and len(up) < 2:
        step = {"left": -1, "right": 1, "up": -6, "down": 6}[key]
        pick = (pick + step) % len(spots)
    elif key in ("space", "enter") and len(up) < 2 and pick not in shown and pick not in up:
        up.append(pick)
        play("E5")
        if len(up) == 2 and faces[up[0]] == faces[up[1]]:
            shown.update(up)
            up.clear()
            play("G5")
        elif len(up) == 2:
            after(1.5, turn_back)
    draw()
    if len(shown) == len(spots):
        play("C5")
        game_over("All the pairs! Press a key to play again.")


draw()
