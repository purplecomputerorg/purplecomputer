from purple import *

# A world to walk around. Draw it in MAP, one character a square: change the letters to change
# the world, and add rows of your own (it's 24 across and 12 down).
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
THINGS = {"T": "🌳", "~": "#3b82c4", "*": "⭐", "F": "🦊", "D": "🚪"}
WALLS = "T~D"
GROUND = ("#4f9d4a", "#57a852")

# The hero is a tiny picture made of letters. Change the colors, or use picture("name") for a
# photo you added on the Rooms page.
HERO = pixels([
    "..HHHH..",
    ".HSSSSH.",
    "..SKSK..",
    "..SSSS..",
    ".BBBBBB.",
    "S.BBBB.S",
    "..B..B..",
    "..K..K..",
], {"H": "#6b3e1e", "S": "#f2c49b", "K": "#222222", "B": "#e0457b"})

TALK = {"F": "Hello! I'm Fox. Find all the stars and the door will open."}
MOVES = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

stars = sum(row.count("*") for row in MAP)
found = 0
x, y = next((c, r) for r, row in enumerate(MAP) for c, ch in enumerate(row) if ch == "Y")

for r, row in enumerate(MAP):
    for c, ch in enumerate(row):
        grid.floor.set(c, r, GROUND[(c + r) % 2])
        if ch in THINGS:
            grid.set(c, r, THINGS[ch])
grid.set(x, y, HERO)
status(f"Find the stars: {found} of {stars} ⭐")
say("Walk with the arrow keys. Find the stars!")


def step(dx, dy):
    global x, y, found
    nx, ny = x + dx, y + dy
    here = MAP[ny][nx]
    if here in TALK:
        say(TALK[here])
        return
    if here in WALLS and not (here == "D" and found == stars):
        drum("woodblock")
        return
    grid.erase(x, y)
    x, y = nx, ny
    if grid.get(x, y) == "⭐":
        found += 1
        play("C5")
        say(f"{found}!" if found < stars else "All the stars! The door is open.")
        status(f"Find the stars: {found} of {stars} ⭐")
    if here == "D":
        game_over("You did it! Press a key to play again.")
        say("You found the way out!")
    grid.set(x, y, HERO)


held_for = 0


def on_key(key):
    global held_for
    if key in MOVES:
        held_for = 0
        step(*MOVES[key])


# on_key takes the first step. Holding the arrow a moment longer keeps walking, a step each time walk()
# runs, so a quick tap is still just one step.
def walk():
    global held_for
    key = next((k for k in MOVES if held(k)), None)
    held_for = held_for + 1 if key else 0
    if held_for > 2:
        step(*MOVES[key])


every(0.12, walk)
