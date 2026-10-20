import random

from purple import *

# Memory for two players taking turns. Arrows pick a card, Space turns it over. Find a pair and
# you go again. Change CARDS to your family's favorite things.
CARDS = ["🐶", "🐱", "🦕", "🚂", "🍓", "🌈", "🚀", "🐢", "🍦"]
PLAYERS = [("🔴", "Red"), ("🔵", "Blue")]
BACK = "🟪"
SPOTS = [(3 + c * 3, 2 + r * 3) for r in range(3) for c in range(6)][:len(CARDS) * 2]

faces = CARDS * 2
random.shuffle(faces)
shown = set()      # cards matched for good
up = []            # the one or two cards turned over this turn
pick, turn = 0, 0
score = [0, 0]


def draw():
    for i, spot in enumerate(SPOTS):
        grid.set(spot, faces[i] if i in shown or i in up else BACK, size=2)
    grid.cursor(SPOTS[pick])
    mark, name = PLAYERS[turn]
    status(f"{mark} {name}'s turn   {PLAYERS[0][0]} {score[0]}  {PLAYERS[1][0]} {score[1]}")


def turn_back():
    global turn
    up.clear()
    turn = 1 - turn
    say(f"{PLAYERS[turn][1]}'s turn")
    draw()


def on_key(key):
    global pick
    if key in ("left", "right", "up", "down") and len(up) < 2:
        step = {"left": -1, "right": 1, "up": -6, "down": 6}[key]
        pick = (pick + step) % len(SPOTS)
    elif key in ("space", "enter") and len(up) < 2 and pick not in shown and pick not in up:
        up.append(pick)
        play("E5")
        if len(up) == 2 and faces[up[0]] == faces[up[1]]:
            shown.update(up)
            up.clear()
            score[turn] += 1
            play("G5")
            say("A pair! Go again.")
        elif len(up) == 2:
            after(1.5, turn_back)
    if len(shown) == len(SPOTS):
        winner = "It's a tie!" if score[0] == score[1] else f"{PLAYERS[score[1] > score[0]][1]} wins!"
        say(winner)
        game_over(f"{winner} Press a key to play again.")
    draw()


draw()
say("Memory! Red goes first.")
