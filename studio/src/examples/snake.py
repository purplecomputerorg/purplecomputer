from purple import *

# A snake that keeps moving. Arrow keys turn it; it comes back on the other side of the screen.
snake = [(12, 6), (11, 6), (10, 6), (9, 6)]
heading = (1, 0)
TURNS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

for square in snake:
    grid.set(square, "#5ec46a")


def on_key(key):
    global heading
    heading = TURNS.get(key, heading)


def step():
    x, y = snake[0]
    head = ((x + heading[0]) % grid.w, (y + heading[1]) % grid.h)
    grid.erase(snake.pop())
    snake.insert(0, head)
    grid.set(head, "#5ec46a")


every(0.2, step)
