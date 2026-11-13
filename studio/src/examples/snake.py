import random

from purple import *

# A snake that eats letters to spell words. Purple says a word and lights up its first letter, laid out like the
# keyboard. Press that key and the snake crawls over and eats it, then the next letter lights up. Spell the whole
# word and its picture shows. The top line says which key to press. Any other key sends the snake there too, and
# the arrows nudge it a square.

# The words to spell, each with its picture. Purple says each word out loud.
# Labels: word, picture
WORDS = {"cat": "🐱", "dog": "🐶", "sun": "☀️", "bus": "🚌", "pig": "🐷", "fish": "🐟"}
# The snake's colors, from its head back, repeated down its length.
BODY = ["#5ec46a", "#3e9e4c"]
# How many squares a second the snake crawls, 2 to 15.
SPEED = 7
# How long the snake can grow, 3 to 40 squares.
LONGEST = 20

spots = grid.keyboard(KEY_ROWS[1:])
keys = {spot: key for key, spot in spots.items()}
words = list(WORDS)
random.shuffle(words)
snake = [(13 - i, 10) for i in range(3)]
game = state(word="", got=0, target=None, steer=None, wait=0)
head = pixels([
    "..SSSSSS..",
    ".SSSSSSSS.",
    "SSSSSSSSSS",
    "SWWSSSSWWS",
    "SWKSSSSWKS",
    "SSSSSSSSSS",
    "SSSSSSSSSS",
    "SSSSSSSSSS",
    ".SSSSSSSS.",
    "..SSSSSS..",
], {"S": BODY[0], "W": "#ffffff", "K": "#1b1b1b"})


def letters():
    return [c for c in game.word.lower() if c in spots]


def wanted():
    left = letters()[game.got:]
    return left[0] if left else None


def light():
    for key, spot in spots.items():
        grid.floor.set(spot, "primary" if key == wanted() else "tile")
    spelled = " ".join(c.upper() if i < game.got else "_" for i, c in enumerate(letters()))
    press = f"   Press {{{wanted().upper()}}}" if wanted() else ""
    status(f"{WORDS[game.word]}  {spelled}{press}")


def new_word():
    show("")
    game.word, game.got = words[0], 0
    words.append(words.pop(0))
    light()
    say(game.word)


def draw():
    for i in range(len(snake) - 1, 0, -1):
        grid.set(snake[i], BODY[(i - 1) % len(BODY)])
    grid.set(snake[0], head)


def on_key(key):
    if key in ARROWS:
        game.target, game.steer, game.wait = None, key, 3
        step(*ARROWS[key])
    elif key in spots:
        game.target, game.steer = spots[key], None


def toward(a, b):
    return (a < b) - (a > b)


def arrive(key):
    if key != wanted():
        return
    play(KEY_NOTES[key], "glockenspiel")
    game.got += 1
    if len(snake) < LONGEST:
        snake.append(snake[-1])
    light()
    if wanted():
        return
    show(WORDS[game.word])
    say(game.word)
    after(2.5, new_word)


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
        # A tap is one step; holding keeps it going after a moment.
        game.wait -= 1
        if game.wait < 0:
            step(*ARROWS[game.steer])


for key, spot in spots.items():
    grid.set(spot, key.upper())
draw()
new_word()
every(1 / SPEED, crawl)
