from purple import *

# A beat maker: each row is a drum, each column a beat. Arrows move, Space turns a beat on or off,
# Enter starts and stops the music.

# The drums, top to bottom: the picture beside each row and the drum it plays.
ROWS = [("🐘", "kick"), ("🐸", "snare"), ("🐝", "hi-hat"), ("👏", "clap")]
# How many beats before the music comes round again.
STEPS = 16
# Seconds from one beat to the next: smaller is faster.
SPEED = 0.2
# The color of a beat that's off.
OFF = "#3a2f5c"
# The color of a beat that's on.
ON = "#f2b134"
# The color above the beat playing now.
NOW = "#5c4c8f"

top, left = 3, 4
beats = [[False] * STEPS for _ in ROWS]
row, col, at = 0, 0, -1
loop = None


def square(r, c):
    grid.set(left + c, top + r * 2, ON if beats[r][c] else OFF)


for r, (animal, _) in enumerate(ROWS):
    grid.set(left - 2, top + r * 2, animal)
    for c in range(STEPS):
        square(r, c)
grid.cursor(left, top)
status("Space adds a beat. Enter plays.")


def tick():
    global at
    if at >= 0:
        grid.floor.erase(left + at, top - 1)
    at = (at + 1) % STEPS
    grid.floor.set(left + at, top - 1, NOW)
    for r, (_, name) in enumerate(ROWS):
        if beats[r][at]:
            drum(name)


def on_key(key):
    global row, col, loop, at
    if key in ("up", "down"):
        row = (row + (1 if key == "down" else -1)) % len(ROWS)
    elif key in ("left", "right"):
        col = (col + (1 if key == "right" else -1)) % STEPS
    elif key == "space":
        beats[row][col] = not beats[row][col]
        square(row, col)
        if beats[row][col]:
            drum(ROWS[row][1])
    elif key == "enter" and loop:
        loop.stop()
        loop = None
        grid.floor.erase(left + at, top - 1)
        at = -1
    elif key == "enter":
        loop = every(SPEED, tick)
    grid.cursor(left + col, top + row * 2)
