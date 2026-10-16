from purple import *

# Asks, speaks, and plays: the calls a trivia room makes.
background("#173a2a")
show("🦖")
write("Which dinosaur had tiny arms?")
say("Which dinosaur had tiny arms?")
if ask("Your answer").strip().lower() == "t rex":
    play("C5")
    drum("snare")
show("🎉")
