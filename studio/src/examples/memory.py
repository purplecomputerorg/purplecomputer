import random

from purple import *

# Memory for one player or a few taking turns, laid out like the Music room: each card is a letter key.
# Press a card's letter to turn it over. Find a pair and you go again.

# The pictures on the cards, up to 13: emoji, or your pictures, or both. Each one makes a pair, shuffled every game.
CARDS = ["🐶", "🐱", "🦕", "🚂", "🍓", "🌈", "🚀", "🐢", "🍦"]
# The players, taking turns in this order: each one's mark and name.
# Labels: mark, name
PLAYERS = [("🔴", "Red"), ("🔵", "Blue")]

# Each row of keys and its color, the same as the Music room's.
rows = (("qwertyuiop", "#e44444"), ("asdfghjkl", "#e2c63a"), ("zxcvbnm", "#2e6ae1"))
cards = CARDS[:13] * 2
random.shuffle(cards)
# As few rows as fit the cards, each about as full as the others, so the rows end together.
used = next(n for n in (1, 2, 3) if len(cards) <= sum(len(keys) for keys, _ in rows[:n]))
per_row = []
left = len(cards)
for i, (keys, _) in enumerate(reversed(rows[:used])):
    per_row.insert(0, min(len(keys), left // (used - i)))
    left -= per_row[0]
spots = {key: (2 + x * 2, 4 + r * 2, color)
         for r, ((keys, color), n) in enumerate(zip(rows, per_row)) for x, key in enumerate(keys[:n])}
faces = dict(zip(spots, cards))
shown = set()      # cards matched for good
up = []            # the one or two cards turned over this turn
game = state(turn=0)


def face_up(x, y, face):
    if face not in images:
        return grid.set(x, y, face, size=2)
    w, h = images[face]
    grid.set(x, y, picture(face, 2) if w >= h else picture(face, max(1, round(2 * w / h)), 2))


def draw():
    for key, face in faces.items():
        x, y, color = spots[key]
        if key in shown or key in up:
            grid.floor.set(x, y, color, size=2)
            face_up(x, y, face)
        else:
            grid.floor.erase(x, y)
            grid.set(x, y, key.upper(), size=2)
    mark, name = PLAYERS[game.turn]
    status(f"{mark} {name}'s turn" if len(PLAYERS) > 1 else "")


def turn_back():
    up.clear()
    game.turn = (game.turn + 1) % len(PLAYERS)
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
