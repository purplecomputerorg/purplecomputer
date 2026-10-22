import random

from purple import *

# Memory for one player or a few taking turns, laid out like the Music room: each card is a letter key.
# Press a card's letter to turn it over. Find a pair and you go again.

# The pictures on the cards, up to 13: emoji, or your pictures, or both. Each one makes a pair, shuffled every game.
CARDS = ["🐶", "🐱", "🦕", "🚂", "🍓", "🌈", "🚀", "🐢", "🍦"]
# How many players, 1 to 6: one plays alone, more take turns, each finding pairs in their own color.
PLAYERS = 1
# The color under a card turned over but not matched yet.
TURNED = "#7a5ac8"

# Each player's mark, and the color under the pairs they find.
players = [("🔴", "#e44444"), ("🔵", "#2e6ae1"), ("🟢", "#2e9e4f"), ("🟡", "#e0a020"), ("🟣", "#9b4dca"), ("🟠", "#ec7a1c")]
players = players[:max(1, min(int(PLAYERS), len(players)))]
rows = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
cards = CARDS[:13] * 2
random.shuffle(cards)
# As few rows as fit the cards, each about as full as the others, so the rows end together.
used = next(n for n in (1, 2, 3) if len(cards) <= sum(len(keys) for keys in rows[:n]))
per_row = []
left = len(cards)
for i, keys in enumerate(reversed(rows[:used])):
    per_row.insert(0, min(len(keys), left // (used - i)))
    left -= per_row[0]
# Each card is 2 squares wide, so the widest row sets the left edge that centers them on the grid's 24 squares.
left = 12 - max(per_row)
spots = {key: (left + x * 2, 4 + r * 2) for r, (keys, n) in enumerate(zip(rows, per_row)) for x, key in enumerate(keys[:n])}
faces = dict(zip(spots, cards))
shown = {}        # cards matched for good, and the color of who found them
up = []            # the one or two cards turned over this turn
game = state(turn=0)


def draw():
    for key, face in faces.items():
        x, y = spots[key]
        if key in shown or key in up:
            grid.floor.set(x, y, shown.get(key, TURNED), size=2)
            grid.set(x, y, face, size=2)
        else:
            grid.floor.erase(x, y)
            grid.set(x, y, key.upper(), size=2)
    status(f"{players[game.turn][0]}'s turn" if len(players) > 1 else "")


def turn_back():
    up.clear()
    game.turn = (game.turn + 1) % len(players)
    draw()


def on_key(key):
    if key in faces and len(up) < 2 and key not in shown and key not in up:
        up.append(key)
        play("E5")
        if len(up) == 2 and faces[up[0]] == faces[up[1]]:
            shown.update(dict.fromkeys(up, players[game.turn][1]))
            up.clear()
            play("G5")
        elif len(up) == 2:
            after(1.5, turn_back)
    draw()
    if len(shown) == len(faces):
        play("C5")
        game_over("All the pairs! Press a key to play again.")


draw()
