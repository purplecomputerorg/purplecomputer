from purple import *

# A snake that crawls to whichever key you press, on keys laid out like the keyboard. Each key it reaches
# lights up and plays its note. Press another key on the way and it heads there instead.

# The snake's color.
SNAKE = "#5ec46a"
# How many squares long the snake is, 2 to 20.
LENGTH = 4
# Seconds between each square it crawls.
SPEED = 0.15
# The note each column of keys plays, left to right.
NOTES = ["C4", "D4", "E4", "G4", "A4", "C5", "D5", "E5", "G5", "A5"]

spots = grid.keyboard()
keys = {spot: key for key, spot in spots.items()}
head = pixels([
    ".SSSSSS.",
    "SWWSSWWS",
    "SWKSSWKS",
    "SSSSSSSS",
    "SSSSSSSS",
    "SSSSSSSS",
    "SSSSSSSS",
    ".SSSSSS.",
], {"S": SNAKE, "W": "#ffffff", "K": "#1b1b1b"})
snake = [(13 - i, 10) for i in range(LENGTH)]
game = state(target=None)

for key, spot in spots.items():
    grid.floor.set(spot, "tile")
    grid.set(spot, key.upper())
for square in snake[1:]:
    grid.set(square, SNAKE)
grid.set(snake[0], head)


def on_key(key):
    if key in spots:
        game.target = spots[key]


def toward(a, b):
    return (a < b) - (a > b)


def arrive(key):
    grid.floor.set(spots[key], "primary")
    column = next(row.index(key) for row in KEY_ROWS if key in row)
    play(NOTES[column], "glockenspiel")


def crawl():
    if game.target is None:
        return
    (x, y), (tx, ty) = snake[0], game.target
    grid.set(snake[0], SNAKE)
    snake.insert(0, (x + toward(x, tx), y) if x != tx else (x, y + toward(y, ty)))
    grid.set(snake[0], head)
    tail = snake.pop()
    if tail not in snake:
        grid.erase(tail)
        if tail in keys:
            grid.set(tail, keys[tail].upper())
    if snake[0] == game.target:
        game.target = None
        arrive(keys[snake[0]])


every(SPEED, crawl)
