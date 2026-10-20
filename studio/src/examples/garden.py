from purple import *

# A garden that remembers itself. Pick a seed with a number key, move with the arrows, and press
# Space to plant, then to water. Each plant grows a step every time it's watered.

# The seeds: the number key that picks each one, its name, and how it looks as it grows.
# Labels: number key, name, how it grows
SEEDS = {
    "1": ("sunflower", ["🌱", "🌿", "🌻"]),
    "2": ("tulip", ["🌱", "🌿", "🌷"]),
    "3": ("carrot", ["🌱", "🌿", "🥕"]),
    "4": ("strawberry", ["🌱", "🌿", "🍓"]),
    "5": ("tree", ["🌱", "🌿", "🌳"]),
}
# The soil's two colors, laid like a checkerboard.
SOIL = ("#7a5230", "#6f4a2b")

seed = "1"
x, y = 12, 6
moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
# keep remembers the garden for next time: (x, y) squares can't be saved, so it's "x,y" -> [seed, step].
plants = keep.setdefault("plants", {})

for gx in range(grid.w):
    for gy in range(1, grid.h):
        grid.floor.set(gx, gy, SOIL[(gx + gy) % 2])
for spot, (kind, stage) in plants.items():
    grid.set(*map(int, spot.split(",")), SEEDS[kind][1][stage])


def show_seed():
    status(f"Seed: {SEEDS[seed][1][-1]} {SEEDS[seed][0]}   1 to 5 picks a seed")
    grid.cursor(x, y)


def on_key(key):
    global seed, x, y
    if key in SEEDS:
        seed = key
        play("G4", "glockenspiel")
    elif key in moves:
        dx, dy = moves[key]
        x, y = (x + dx) % grid.w, max(1, min(grid.h - 1, y + dy))
    elif key == "space":
        return tend()
    show_seed()


def tend():
    spot = f"{x},{y}"
    if spot not in plants:
        plants[spot] = [seed, 0]
        drum("bongo")
    elif plants[spot][1] < 2:
        plants[spot][1] += 1
        play(["C4", "E4", "G4"][plants[spot][1]], "glockenspiel")
    else:
        name, looks = SEEDS[plants[spot][0]]
        play("C5", "glockenspiel")
        status(f"The {name} is all grown! {looks[-1]}")
    kind, stage = plants[spot]
    grid.set(x, y, SEEDS[kind][1][stage])


show_seed()
