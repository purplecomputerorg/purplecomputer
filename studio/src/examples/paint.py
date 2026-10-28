from purple import *

# A paint pot. Each paint's key drops a dab of it in, and the pot mixes them like real paint: yellow and blue
# make green. Purple says the color it made. Backspace takes the last dab out, Space empties the pot, and
# Enter keeps the color on the shelf along the bottom.

# The paints: the key for each one, its color, and its name, said out loud.
# Labels: key, color, name
PAINTS = {
    "r": ("#e8352b", "red"),
    "y": ("#ffd400", "yellow"),
    "b": ("#1e5bd6", "blue"),
    "w": ("#ffffff", "white"),
    "k": ("#1a1a1a", "black"),
}
# Names for the colors the pot makes, said out loud: Purple says whichever one the pot is closest to.
COLOR_NAMES = {
    "orange": "#ff7019",
    "green": "#50ac64",
    "lime": "#a0d030",
    "mint": "#7cc588",
    "purple": "#823a82",
    "lavender": "#a663a4",
    "violet": "#3b33aa",
    "pink": "#ff7870",
    "sky blue": "#5499ff",
    "lemon": "#ffec70",
    "brown": "#b16939",
    "cherry": "#70120c",
    "olive": "#746608",
    "navy": "#072f6b",
    "gray": "#5a5a5a",
}

pot_holds = 12  # dabs; past that the oldest goes, so the pot never gets stuck on one color
names = {**{name: color for color, name in PAINTS.values()}, **COLOR_NAMES}
left = (grid.w - 3 * len(PAINTS) + 1) // 2
game = state(dabs=[])
shelf = keep.setdefault("shelf", [])


def rgb(color):
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def distance(a, b):
    """How different two colors look. Weighing red, green, and blue like this is closer to eyes than plain sums."""
    (r1, g1, b1), (r2, g2, b2) = rgb(a), rgb(b)
    red = (r1 + r2) / 2
    return (2 + red / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - red) / 256) * (b1 - b2) ** 2


def closest(color):
    return min(names, key=lambda name: distance(color, names[name]))


def pot():
    return mix(*game.dabs) if game.dabs else None


def draw():
    grid.clear()
    for i, (key, (color, _)) in enumerate(PAINTS.items()):
        grid.set(left + 3 * i, 0, color, size=2)
        grid.set(left + 3 * i + 1, 1, key.upper())
    grid.set(10, 3, pot() or "tile", size=6)
    for i, color in enumerate(game.dabs):
        grid.set(13 - len(game.dabs) // 2 + i, 10, color)
    for i, color in enumerate(shelf):
        grid.set(i, 11, color)
    if game.dabs:
        status(f"{closest(pot())}   Space empties the pot, Enter keeps the color")
    else:
        status("Press a paint's letter to put some in the pot")


def on_key(key):
    if key in PAINTS:
        game.dabs = (game.dabs + [PAINTS[key][0]])[-pot_holds:]
        drum("bongo")
    elif key == "backspace" and game.dabs:
        game.dabs.pop()
    elif key == "space" and game.dabs:
        game.dabs = []
        drum("tambourine")
    elif key == "enter" and game.dabs:
        shelf.append(pot())
        del shelf[:-grid.w]
        play("G5", "glockenspiel")
    if game.dabs and key in (*PAINTS, "backspace"):
        say(closest(pot()))
    draw()


draw()
