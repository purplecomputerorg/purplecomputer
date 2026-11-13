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
# The drum when a seed is planted: one of Purple's drums, one of your sounds, or none.
PLANT_SOUND = ""
# The drum when a plant grows a step, or none.
GROW_SOUND = ""

spots = grid.keyboard(KEY_ROWS[1:])
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
        show_seed()
    elif key in spots:
        tend(key)


def tend(key):
    if key not in plants:
        plants[key] = [game.seed, 0]
        if PLANT_SOUND:
            drum(PLANT_SOUND)
    elif plants[key][1] < len(SEEDS[plants[key][0]][1]) - 1:
        plants[key][1] += 1
        if GROW_SOUND:
            drum(GROW_SOUND)
    else:
        name, looks = SEEDS[plants[key][0]]
        status(f"The {name} is all grown! {looks[-1]}")
    patch(key)


for key in spots:
    patch(key)
show_seed()
