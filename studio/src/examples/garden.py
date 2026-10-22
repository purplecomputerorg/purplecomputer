from purple import *

# A garden that remembers itself, laid out like the Music room: each key from Q to / is a patch of soil. Pick a
# seed with a number key, then press a patch's key to plant it there, and again to water it. Each plant grows
# a step every time it's watered.

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

rows = ("qwertyuiop", "asdfghjkl;", "zxcvbnm,./")
spots = {key: (2 + x * 2, 4 + r * 2) for r, keys in enumerate(rows) for x, key in enumerate(keys)}
game = state(seed="1")
# keep remembers the garden for next time: patch key -> [seed, step].
plants = keep.setdefault("plots", {})


def patch(key):
    x, y = spots[key]
    grid.floor.set(x, y, SOIL[(x + y) // 2 % 2], size=2)
    if key in plants:
        kind, stage = plants[key]
        grid.set(x, y, SEEDS[kind][1][stage], size=2)
    else:
        grid.set(x, y, key.upper(), size=2)


def show_seed():
    name, looks = SEEDS[game.seed]
    status(f"Seed: {looks[-1]} {name}   1 to 5 picks a seed")


def on_key(key):
    if key in SEEDS:
        game.seed = key
        play("G4", "glockenspiel")
        show_seed()
    elif key in spots:
        tend(key)


def tend(key):
    if key not in plants:
        plants[key] = [game.seed, 0]
        drum("bongo")
    elif plants[key][1] < 2:
        plants[key][1] += 1
        play(["C4", "E4", "G4"][plants[key][1]], "glockenspiel")
    else:
        name, looks = SEEDS[plants[key][0]]
        play("C5", "glockenspiel")
        status(f"The {name} is all grown! {looks[-1]}")
    patch(key)


for key in spots:
    patch(key)
show_seed()
