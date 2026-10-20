from purple import *

# A story where your kid picks what happens. Write your own: add pages, and point the numbers at them.

# The pages: each one's name, its picture, the words Purple reads out, and the page each number leads to.
# Labels: page, picture, words, numbers
PAGES = {
    "start": ("🏡", "Mia finds a map under her bed. Press 1 to go to the forest, or 2 to go to the sea.",
              {"1": "forest", "2": "sea"}),
    "forest": ("🌲", "In the forest, an owl says hello. Press 1 to follow the owl, or 2 to climb a tree.",
               {"1": "owl", "2": "tree"}),
    "sea": ("🌊", "At the sea, a crab waves a claw. Press 1 to dig in the sand, or 2 to take a boat.",
            {"1": "sand", "2": "boat"}),
    "owl": ("🦉", "The owl shows Mia a cave full of glowing stones. The end!", {}),
    "tree": ("🌳", "From the top of the tree, Mia sees her house. Time for dinner. The end!", {}),
    "sand": ("🦀", "Mia digs up a shiny shell and gives it to the crab. The end!", {}),
    "boat": ("⛵", "The boat sails to an island with a hundred puppies. The end!", {}),
}


game = state(page="start")


def turn_to(name):
    game.page = name
    picture, words, _ = PAGES[name]
    clear()
    show(picture)
    write(words)
    say(words)
    if not PAGES[name][2]:
        status("Press Space to start again")


def on_key(key):
    choices = PAGES[game.page][2]
    if key in choices:
        play("G4")
        turn_to(choices[key])
    elif key == "space" and not choices:
        turn_to("start")
    elif key == "space":
        say(PAGES[game.page][1])


turn_to("start")
