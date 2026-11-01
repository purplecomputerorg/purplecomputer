from purple import *

# A story your kid reads a page at a time, picking what happens next with the number keys.

# The story's name, on its cover and said out loud.
TITLE = "Mia and the map"
# The pages, in the order they were written: the story starts on the first. Each has a picture, the words said out
# loud, what Purple says next to ask for a choice, and its choices: what each one does, and the page it turns to.
# One choice turns with Space; none is an end.
# Labels: page, picture, words, then says, choices
PAGES = {
    "start": ("🗺️", "Mia finds a map. It shows a forest and the sea.", "Press 1 to go to the forest, or 2 to go to the sea.",
              {"go to the forest": "forest", "go to the sea": "sea"}),
    "forest": ("🦉", "In the forest, an owl shows Mia a cave full of glowing stones. The end!", "", {}),
    "sea": ("🦀", "At the sea, a crab gives Mia a shiny shell. The end!", "", {}),
}
# The drum when a page turns: one of Purple's drums, one of your sounds, or none.
PAGE_SOUND = ""


game = state(page=None)


def cover():
    game.page = None
    clear()
    show("📖")
    write(TITLE)
    say(TITLE)
    status("Press any key to start")


def choices():
    return list(PAGES[game.page][3].items())


def read_page():
    for line in PAGES[game.page][1:3]:
        if line:
            say(line)


def turn_to(name):
    game.page = name
    clear()
    show(PAGES[name][0])
    write(PAGES[name][1])
    read_page()
    ways = choices()
    if len(ways) == 1:
        status(f"Space {ways[0][0] or 'turn the page'}")
    elif ways:
        status("    ".join(f"{{{n}}} {what}" for n, (what, _) in enumerate(ways, 1)))
    else:
        status("The end. Press Space to start again")


def on_key(key):
    if game.page is None:
        return turn_to(next(iter(PAGES)))
    ways = choices()
    n = int(key) if key.isdigit() else (1 if key == "space" and len(ways) == 1 else 0)
    if 0 < n <= len(ways) and ways[n - 1][1] in PAGES:
        if PAGE_SOUND:
            drum(PAGE_SOUND)
        turn_to(ways[n - 1][1])
    elif key == "space" and not ways:
        cover()
    elif key == "space":
        read_page()


cover()
