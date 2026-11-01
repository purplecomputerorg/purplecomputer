from purple import *

# A world to walk around. Find all the stars and home opens. Some stars are through the door, in the cave.

# The world's maps, one letter a square, 26 across and 12 down: Y is where the hero starts. A number is a door, and
# it leads to the other door with the same number: put a 1 on two maps and the hero can walk between them.
WORLD = {
    "outside": [
        "TTTTTTTTTTTTTTTTTTTTTTTTTT",
        "T.........T..............T",
        "T..*......T.....~~~......T",
        "T.........T....~~~~~.*...T",
        "T....F.........~~~~~.....T",
        "T..........Y....~~~......T",
        "TTTTT..TTTTT.............T",
        "T..........T.......TTTTTTT",
        "T...1......T.............T",
        "T..........H.....*.......T",
        "T..........T.............T",
        "TTTTTTTTTTTTTTTTTTTTTTTTTT",
    ],
    "cave": [
        "RRRRRRRRRRRRRRRRRRRRRRRRRR",
        "R1,,,,,,RR,,,,,,,,,,,*,,,R",
        "R,,,,,,,RR,,,,RRRR,,,,,,,R",
        "R,,,,,,,,,,,,,RRRR,,,,,,,R",
        "RRRR,,,,,,,,,,,,,,,,RRRRRR",
        "R,,,,,,,RRRRR,,,,,,,,,,,,R",
        "R,,B,,,,R,,,,,,,,,,,,,,,,R",
        "R,,,,,,,R,,,~~~~,,,,,,,,,R",
        "R,,*,,,,,,,,~~~~,,,,,,,,,R",
        "RRRRRR,,,,,,,,,,,,RRRRRRRR",
        "R,,,,,,,,,,,,,,,,,,,,,,,,R",
        "RRRRRRRRRRRRRRRRRRRRRRRRRR",
    ],
}
# Everything in the world, by its letter on the maps: how it looks (an emoji, one of your photos, or a color), what it
# is, and what it says. It is a wall, ground to walk on, something to find, a friend, home, or a door. A friend
# says its words out loud when the hero bumps into them. Home opens once everything is found.
# Labels: letter, looks like, it is, it says
THINGS = {
    "T": ("🌳", "wall", ""),
    "R": ("🪨", "wall", ""),
    "~": ("#4677b0", "wall", ""),
    ",": ("#5c4b3b", "ground", ""),
    "*": ("⭐", "find", ""),
    "F": ("🦊", "friend", "Hello! Find all the stars and home will open. Some are through the door."),
    "B": ("🦇", "friend", "Squeak! The door goes back outside."),
    "H": ("🏠", "home", ""),
    "1": ("🚪", "door", ""),
}
# The grass's two colors.
GROUND = ("#4a8a50", "#4f9154")
# The hero, drawn square by square: each letter is one of the hero's colors, and . is see-through.
HERO = [
    "..HHHH..",
    ".HSSSSH.",
    "..SKSK..",
    "..SSSS..",
    ".BBBBBB.",
    "S.BBBB.S",
    "..B..B..",
    "..K..K..",
]
# The hero's colors, by the letter that paints them on the hero.
# Labels: letter, name, color
HERO_COLORS = {"H": ("hair", "#6b3e1e"), "S": ("skin", "#f2c49b"), "K": ("eyes and shoes", "#222222"), "B": ("shirt", "#e0457b")}
# An emoji or one of your photos to be the hero instead of the drawing, or nothing to use the drawing.
HERO_PICTURE = ""
# The drum when something is found: one of Purple's drums, one of your sounds, or none.
FIND_SOUND = ""
# The drum when the hero goes through a door, or none.
DOOR_SOUND = ""
# The drum when the hero bumps into a wall, or none.
BUMP_SOUND = ""
# The drum when the hero gets home, or none.
HOME_SOUND = ""

hero = HERO_PICTURE or pixels(HERO, {letter: color for letter, (_, color) in HERO_COLORS.items()})
moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
# Every square of every map, by (map, x, y).
spots = {(name, c, r): ch for name, rows in WORLD.items() for r, row in enumerate(rows) for c, ch in enumerate(row)}
# A door numbered 2, 3, and so on looks like door 1 unless THINGS gives it a look of its own.
door = next((look for letter, (look, _, _) in THINGS.items() if letter.isdigit()), "🚪")


# How a square looks, what it is, and what it says. Past a map's edge is a wall.
def what(ch):
    if ch in THINGS:
        return THINGS[ch]
    if ch and ch.isdigit():
        return (door, "door", "")
    return (None, "ground", "") if ch else (None, "wall", "")


finds = sum(1 for ch in spots.values() if what(ch)[1] == "find")
prize = next((look for look, kind, _ in THINGS.values() if kind == "find" and isinstance(look, str)), "⭐")
game = state(at=next(s for s, ch in spots.items() if ch == "Y"), found=set(), held_for=0)


# Draws the map the hero is on. Redrawing every square is fine: Purple only shows what changed.
def show_map():
    name, x, y = game.at
    grid.clear()
    for r, row in enumerate(WORLD[name]):
        for c, ch in enumerate(row):
            look = None if (name, c, r) in game.found else what(ch)[0]
            color = isinstance(look, str) and look.startswith("#")
            grid.floor.set(c, r, look if color else GROUND[(c + r) % 2])
            if look and not color:
                grid.set(c, r, look)
    grid.set(x, y, hero)
    status(f"{prize} {len(game.found)} of {finds}" if len(game.found) < finds else f"{prize} All found! Home is open.")


def sound(name):
    if name:
        drum(name)


def step(dx, dy):
    name, x, y = game.at
    spot = (name, x + dx, y + dy)
    here = spots.get(spot, "")
    _, kind, words = what(here)
    if kind == "friend":
        if words:
            say(words)
            status(words)
        return
    if kind == "wall" or (kind == "home" and len(game.found) < finds):
        return sound(BUMP_SOUND)
    if kind == "find" and spot not in game.found:
        game.found.add(spot)
        sound(FIND_SOUND)
    if kind == "door":
        sound(DOOR_SOUND)
        spot = next((s for s, ch in spots.items() if ch == here and s != spot), spot)
    game.at = spot
    show_map()
    if kind == "home":
        sound(HOME_SOUND)
        game_over("You made it home! Press a key to walk again.")


def on_key(key):
    if key in moves:
        game.held_for = 0
        step(*moves[key])


# on_key takes the first step. Holding the arrow a moment longer keeps walking, a step each time walk()
# runs, so a quick tap is still just one step.
def walk():
    key = next((k for k in moves if held(k)), None)
    game.held_for = game.held_for + 1 if key else 0
    if game.held_for > 2:
        step(*moves[key])


show_map()
every(0.12, walk)
