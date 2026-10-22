from purple import *

# A world to walk around. Find all the stars and the door opens.

# The world, one letter a square, 24 across and 12 down: Y is where the hero starts.
MAP = [
    "TTTTTTTTTTTTTTTTTTTTTTTT",
    "T.........T............T",
    "T..*......T.....~~~....T",
    "T.........T....~~~~~.*.T",
    "T....F.........~~~~~...T",
    "T..........Y....~~~....T",
    "TTTTT..TTTTT...........T",
    "T..........T.......TTTTT",
    "T...*......T...........T",
    "T..........D.....*.....T",
    "T..........T...........T",
    "TTTTTTTTTTTTTTTTTTTTTTTT",
]
# What each letter in the world is: an emoji, or a color.
THINGS = {"T": "🌳", "~": "#3b82c4", "*": "⭐", "F": "🦊", "D": "🚪"}
# The grass's two colors.
GROUND = ("#4f9d4a", "#57a852")
# The hero's colors: H hair, S skin, K eyes and shoes, B shirt.
HERO_COLORS = {"H": "#6b3e1e", "S": "#f2c49b", "K": "#222222", "B": "#e0457b"}
# What someone in the world says when the hero bumps into them.
TALK = {"F": "🦊 Hello! Find all the stars and the door will open."}

# The letters the hero can't walk through. The door opens once every star is found.
walls = "T~D"
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
stars = sum(row.count("*") for row in MAP)
start = next((c, r) for r, row in enumerate(MAP) for c, ch in enumerate(row) if ch == "Y")
game = state(x=start[0], y=start[1], found=0, held_for=0)


def show_stars():
    status(f"⭐ {game.found} of {stars}" if game.found < stars else "⭐ All the stars! The door is open.")


for r, row in enumerate(MAP):
    for c, ch in enumerate(row):
        grid.floor.set(c, r, GROUND[(c + r) % 2])
        if ch in THINGS:
            grid.set(c, r, THINGS[ch])
grid.set(start, hero)
show_stars()


def step(dx, dy):
    nx, ny = game.x + dx, game.y + dy
    here = MAP[ny][nx]
    if here in TALK:
        play("E5")
        return status(TALK[here])
    if here in walls and not (here == "D" and game.found == stars):
        return drum("woodblock")
    grid.erase(game.x, game.y)
    game.x, game.y = nx, ny
    if grid.get(nx, ny) == THINGS["*"]:
        game.found += 1
        play("C5")
    show_stars()
    if here == "D":
        play("G5")
        game_over("You found the way out! Press a key to walk again.")
    grid.set(nx, ny, hero)


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


every(0.12, walk)
