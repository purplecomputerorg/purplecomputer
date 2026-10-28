from purple import *

# A snake that wanders where the arrows point, a square each press, and leaves flowers behind it.
# Space takes another step the same way. Off one edge, it comes back on the other.

# The snake's color.
SNAKE = "#5ec46a"
# How many squares long the snake is, 2 to 20.
LENGTH = 4
# The flowers it leaves behind, one after another.
TRAIL = ["🌼", "🌸", "🌷"]

snake = [(13 - i, 6) for i in range(LENGTH)]
game = state(heading=(1, 0), steps=0)
turns = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

for square in snake:
    grid.set(square, SNAKE)


def on_key(key):
    if key in turns:
        game.heading = turns[key]
    if key in turns or key == "space":
        step()


def step():
    x, y = snake[0]
    dx, dy = game.heading
    head = ((x + dx) % grid.w, (y + dy) % grid.h)
    snake.insert(0, head)
    grid.set(head, SNAKE)
    tail = snake.pop()
    if tail not in snake:
        grid.set(tail, TRAIL[game.steps % len(TRAIL)])
    game.steps += 1
