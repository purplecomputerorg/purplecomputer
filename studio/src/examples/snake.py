from purple import *

# A snake that crawls to whichever key you press, on keys laid out like the keyboard. Each key it reaches
# lights up in its sticker color and plays its note. Press another key on the way and it heads there instead,
# or hold an arrow to steer it yourself.

# The snake's body, square by square back from its head: colors, emoji, or both, repeated down its length.
BODY = ["#5ec46a", "#3e9e4c"]
# Seconds between each square it crawls.
SPEED = 0.15
# The snake grows a square longer at each key it reaches.
GROWS = False

scale = ["C4", "D4", "E4", "G4", "A4", "C5", "D5", "E5", "G5", "A5"]
spots = grid.keyboard()
keys = {spot: key for key, spot in spots.items()}


def head(color):
    return pixels([
        ".SSSSSS.",
        "SWWSSWWS",
        "SWKSSWKS",
        "SSSSSSSS",
        "SSSSSSSS",
        "SSSSSSSS",
        "SSSSSSSS",
        ".SSSSSS.",
    ], {"S": color, "W": "#ffffff", "K": "#1b1b1b"})


snake = [(13 - i, 10) for i in range(3)]
game = state(target=None, steer=None, head=head(BODY[0] if str(BODY[0]).startswith("#") else "#5ec46a"))

for key, spot in spots.items():
    grid.floor.set(spot, "tile")
    grid.set(spot, key.upper())


def draw():
    for i in range(len(snake) - 1, 0, -1):
        grid.set(snake[i], BODY[(i - 1) % len(BODY)])
    grid.set(snake[0], game.head)


draw()


def on_key(key):
    if key in ARROWS:
        game.target, game.steer = None, key
        step(*ARROWS[key])
    elif key in spots:
        game.target, game.steer = spots[key], None


def toward(a, b):
    return (a < b) - (a > b)


def arrive(key):
    color = KEY_COLORS[key]
    grid.floor.set(spots[key], color)
    game.head = head(color)
    column = next(row.index(key) for row in KEY_ROWS if key in row)
    play(scale[column], "glockenspiel")
    if GROWS and len(snake) < 20:
        snake.append(snake[-1])


def step(dx, dy):
    x, y = snake[0]
    snake.insert(0, ((x + dx) % grid.w, (y + dy) % grid.h))
    tail = snake.pop()
    if tail not in snake:
        grid.erase(tail)
        if tail in keys:
            grid.set(tail, keys[tail].upper())
    if snake[0] in keys and game.target in (None, snake[0]):
        game.target = None
        arrive(keys[snake[0]])
    draw()


def crawl():
    if game.target is not None:
        (x, y), (tx, ty) = snake[0], game.target
        step(*((toward(x, tx), 0) if x != tx else (0, toward(y, ty))))
    elif game.steer and held(game.steer):
        step(*ARROWS[game.steer])


every(SPEED, crawl)
