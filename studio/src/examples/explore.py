from purple import *

# A world to walk around. Find all the stars and the house opens. Some stars are through the door, in the cave.

# The world's maps, one letter a square, 24 across and 12 down: Y is where the hero starts. A number is a door, and
# it leads to the other door with the same number: put a 1 on two maps and the hero can walk between them.
WORLD = {
    "outside": [
        "TTTTTTTTTTTTTTTTTTTTTTTT",
        "T.........T............T",
        "T..*......T.....~~~....T",
        "T.........T....~~~~~.*.T",
        "T....F.........~~~~~...T",
        "T..........Y....~~~....T",
        "TTTTT..TTTTT...........T",
        "T..........T.......TTTTT",
        "T...1......T...........T",
        "T..........H.....*.....T",
        "T..........T...........T",
        "TTTTTTTTTTTTTTTTTTTTTTTT",
    ],
    "cave": [
        "RRRRRRRRRRRRRRRRRRRRRRRR",
        "R1,,,,,,RR,,,,,,,,,,,*,R",
        "R,,,,,,,RR,,,,RRRR,,,,,R",
        "R,,,,,,,,,,,,,RRRR,,,,,R",
        "RRRR,,,,,,,,,,,,,,,,RRRR",
        "R,,,,,,,RRRRR,,,,,,,,,,R",
        "R,,B,,,,R,,,,,,,,,,,,,,R",
        "R,,,,,,,R,,,~~~~,,,,,,,R",
        "R,,*,,,,,,,,~~~~,,,,,,,R",
        "RRRRRR,,,,,,,,,,,,RRRRRR",
        "R,,,,,,,,,,,,,,,,,,,,,,R",
        "RRRRRRRRRRRRRRRRRRRRRRRR",
    ],
}
# What each letter in the world is: an emoji, one of your photos, or a color for the ground.
THINGS = {"T": "🌳", "R": "🪨", "~": "#3b82c4", ",": "#5c4b3b", "*": "⭐", "F": "🦊", "B": "🦇", "H": "🏠", "1": "🚪"}
# The grass's two colors.
GROUND = ("#4f9d4a", "#57a852")
# The hero's colors: H hair, S skin, K eyes and shoes, B shirt.
HERO_COLORS = {"H": "#6b3e1e", "S": "#f2c49b", "K": "#222222", "B": "#e0457b"}
# What someone in the world says out loud when the hero bumps into them.
TALK = {"F": "Hello! Find all the stars and the house will open. Some are through the door.", "B": "Squeak! The door goes back outside."}

# The letters the hero can't walk through. The house opens once every star is found. Past a map's edge is a wall too.
walls = "TR~H"
# The hero, a tiny picture: each letter is a color from HERO_COLORS, and . is see-through. Or
# picture("name") for a photo you added on the Rooms page.
hero = pixels([
    "..HHHH..",
    ".HSSSSH.",
    "..SKSK..",
    "..SSSS..",
    ".BBBBBB.",
    "S.BBBB.S",
    "..B..B..",
    "..K..K..",
], HERO_COLORS)
moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
# Every square of every map, by (map, x, y).
spots = {(name, c, r): ch for name, rows in WORLD.items() for r, row in enumerate(rows) for c, ch in enumerate(row)}
stars = list(spots.values()).count("*")
# A door numbered 2, 3, and so on looks like door 1 unless THINGS gives it a look of its own.
door = next((v for k, v in THINGS.items() if k.isdigit()), None)
game = state(at=next(s for s, ch in spots.items() if ch == "Y"), found=set(), held_for=0)


# Draws the map the hero is on. Redrawing every square is fine: Purple only shows what changed.
def show_map():
    name, x, y = game.at
    grid.clear()
    for r, row in enumerate(WORLD[name]):
        for c, ch in enumerate(row):
            look = None if (name, c, r) in game.found else THINGS.get(ch, door if ch.isdigit() else None)
            ground = isinstance(look, str) and look.startswith("#")
            grid.floor.set(c, r, look if ground else GROUND[(c + r) % 2])
            if look and not ground:
                grid.set(c, r, look)
    grid.set(x, y, hero)
    status(f"⭐ {len(game.found)} of {stars}" if len(game.found) < stars else "⭐ All the stars! The house is open.")


def step(dx, dy):
    name, x, y = game.at
    spot = (name, x + dx, y + dy)
    here = spots.get(spot, walls[0])
    if here in TALK:
        say(TALK[here])
        return status(TALK[here])
    if here in walls and not (here == "H" and len(game.found) == stars):
        return drum("woodblock")
    if here == "*" and spot not in game.found:
        game.found.add(spot)
        play("C5")
    if here.isdigit():
        play("A5")
        spot = next((s for s, ch in spots.items() if ch == here and s != spot), spot)
    game.at = spot
    show_map()
    if here == "H":
        play("G5")
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
