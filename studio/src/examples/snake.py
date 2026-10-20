from purple import *

# A snake that wanders where the arrows point, a square each press, and leaves flowers behind it.
# Space takes another step the same way. Off one edge, it comes back on the other.

# The snake's color.
SNAKE = "#5ec46a"
# How many squares long the snake is.
LENGTH = 4
# The flowers it leaves behind, one after another.
TRAIL = ["🌼", "🌸", "🌷"]

snake = [(12 - i, 6) for i in range(LENGTH)]
heading = (1, 0)
steps = 0
turns = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

for square in snake:
    grid.set(square, SNAKE)


def on_key(key):
    global heading
    if key in turns:
        heading = turns[key]
    if key in turns or key == "space":
        step()


def step():
    global steps
    x, y = snake[0]
    head = ((x + heading[0]) % grid.w, (y + heading[1]) % grid.h)
    snake.insert(0, head)
    grid.set(head, SNAKE)
    tail = snake.pop()
    if tail not in snake:
        grid.set(tail, TRAIL[steps % len(TRAIL)])
    steps += 1
