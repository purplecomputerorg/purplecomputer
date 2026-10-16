from purple import *

# Remembers a score across visits, uses the grid and timers, and ends with game_over.
keep["visits"] = keep.get("visits", 0) + 1
show(keep["visits"])
dot = [0]


def step():
    grid.erase(dot[0], 0)
    dot[0] += 1
    grid.set(dot[0], 0, "#ffcc00")
    if dot[0] > 3:
        game_over("Again?")


def on_key(key):
    write(key)


every(0.1, step)
