from purple import *

# A beat maker: each row is a drum, each column a beat. Arrows move, Space turns a beat on or off,
# Enter starts and stops the music. Change ROWS for other drums, or STEPS for a longer loop.
ROWS = [("🐘", "kick"), ("🐸", "snare"), ("🐝", "hi-hat"), ("👏", "clap")]
STEPS = 16
TOP, LEFT = 3, 4
OFF, ON, NOW = "#3a2f5c", "#f2b134", "#5c4c8f"

beats = [[False] * STEPS for _ in ROWS]
row, col, at = 0, 0, -1
loop = None


def square(r, c):
    grid.set(LEFT + c, TOP + r * 2, ON if beats[r][c] else OFF)


for r, (animal, _) in enumerate(ROWS):
    grid.set(LEFT - 2, TOP + r * 2, animal)
    for c in range(STEPS):
        square(r, c)
grid.cursor(LEFT, TOP)
status("Space adds a beat. Enter plays.")


def tick():
    global at
    if at >= 0:
        grid.floor.erase(LEFT + at, TOP - 1)
    at = (at + 1) % STEPS
    grid.floor.set(LEFT + at, TOP - 1, NOW)
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
        grid.floor.erase(LEFT + at, TOP - 1)
        at = -1
    elif key == "enter":
        loop = every(0.2, tick)
    grid.cursor(LEFT + col, TOP + row * 2)
