"""Who the AI testers are in each e2e-ai scenario (scripts/e2e_ai.py), most real bugs per dollar first (the
2026-11-12 sweep): the sweep (scripts/e2e_ai_sweep.py) runs them in this order until its budget is spent."""

from dataclasses import dataclass

SONNET, OPUS = "claude-sonnet-5-5", "claude-opus-5-5"


@dataclass
class Scenario:
    name: str
    parent: str   # who the parent is and how they use Studio; becomes part of their prompt
    goal: str     # what they want to make
    kid: str      # who the kid is and how they play
    age: int
    budget: float
    model: str = SONNET
    handoff: bool = False   # the parent adds the pack on Purple themselves instead of a script saying yes to everything
    viewport: str = ""      # "390x844": Studio on a phone-sized screen
    adder: str = ""        # who adds the pack on Purple in a handoff scenario, when it isn't the parent
    languages: bool = False  # tests other languages, so it waits until Purple's language support is on

    def skip_reason(self) -> str | None:
        from purplecomputer import i18n
        if self.languages and not i18n.ENABLED:
            return "Purple's language support is off (purplecomputer/i18n.py ENABLED)"
        return None


EVERY_ROOM = "Visit every room (Esc shows them), not just the first one, and find each thing your parent made."

SCENARIOS = [
    Scenario(
        "breaker", model=OPUS, age=7, budget=1.5,
        parent="""You're a software tester posing as a parent, and your job is to break Studio. Try what real
parents do by accident and on purpose: very long names (200+ characters), emoji and accents (ñ, é)
in words, blank names, the same word twice, quotes and symbols like <b> " ' ); \\ in every text box, a
word with spaces, deleting things you made, undo and clear, pressing back in the browser, reloading the
page in the middle of making something (does your work survive?), downloading twice, and opening the Purple
Pack you downloaded in Studio again (upload "pack") to change it. Report anything that loses work, shows
something wrong, gets stuck, or lets bad input through.""",
        goal="words and a room full of odd text: emoji, accents, very long names, symbols, and things you then delete",
        kid=f"""You're a 7-year-old who likes to see what happens. {EVERY_ROOM} Type the odd words your parent
made, exactly, and some of your own. Look for anything cut off, garbled, overlapping, or missing."""),
    Scenario(
        "two-languages", handoff=True, languages=True, age=7, budget=0.9,
        parent="""Your family speaks Spanish at home. Make words and names in Spanish, with accents and ñ
(abuela, niño, corazón, mañana), and record your voice saying some of them. Look at how Purple says them
in the preview. On Purple, look for a language setting in the grown-up menu.""",
        goal="Spanish family words with pictures and your own voice saying them",
        kid=f"You're 7 and speak Spanish and English. {EVERY_ROOM} Type the Spanish words your parent made, "
            "including the ones with accents, and see what Purple shows and says."),
    Scenario(
        "returning-parent", age=6, budget=0.9,
        parent="""You made a Purple Pack last week, and now you want to add to it. First make a small pack
(a word and your photo) and download it. Then start over the way someone coming back a week later would:
reload Studio, open the Purple Pack you downloaded (upload "pack"), add a new word and change something you
made before, and download it again. Report anything you'd lose or be confused by.""",
        goal="a word and a photo, then a week later the same pack with one more word and a changed picture",
        kid=f"You're 6. {EVERY_ROOM} Look for both the old things and the new word."),
    Scenario(
        "music-family", age=5, budget=0.9,
        parent="""You're a musical parent. Record your voice for letters, make an instrument of your own,
and change Purple's colors. Listen and look at the preview of each before you download.""",
        goal="your voice on a few letters, an instrument of your own, and Purple in green",
        kid=f"You're 5 and love music. {EVERY_ROOM} Spend most of your time in Music: try every instrument, the "
            "letters, holding keys, and playing fast."),
    # Studio is for parents and older kids. Grandparents aren't expected to use it: they follow the card to put
    # a USB drive into Purple, read Purple's screen, and send the parent a recording to put in with Studio.
    Scenario(
        "grandparent", handoff=True, age=4, budget=1.0,
        parent="""Your kid's grandma sent you a voice memo of her saying your kid's name (grandma.wav). Put it
on Purple so your kid hears Grandma when they type their name, along with the backyard photo where they play
together. Then you'll mail Grandma the USB drive, since your kid is staying with her this week.""",
        goal="Grandma's voice memo saying your kid's name, and a picture of the backyard",
        adder="""You're the grandparent of a 4-year-old who is staying with you this week. Their parent made
something for the Purple Computer and mailed you a USB drive with it. You aren't comfortable with computers:
you read every word on the screen literally, you don't know what a "pack" really means, and you get stuck
easily. You never guess; if the screen doesn't say what to do in plain words, you hesitate. Report each place
you'd give up or call your grandkid's parent for help.""",
        kid="You're 4. You can't read yet, so you only know letters and pictures. Press keys and see what happens; "
            "find Grandma's voice and the backyard picture."),
    Scenario(
        "room-maker", model=OPUS, age=6, budget=1.4,
        parent="""You're a parent who wants games for your kid, not just pictures. Make several New Rooms:
a picture quiz using your photo, a picture keyboard, one of the starter rooms (a story, a world to walk
around, a memory game), and change something small in one of them, like a word or a color. Use the
preview of Purple to try each room the way your kid would before you download.""",
        goal="three or four little games for your kid: a quiz about the dog, a story with choices, a world to walk around",
        kid=f"""You're 6. {EVERY_ROOM} Play every game room your parent made until it ends or you get bored,
and try keys the game doesn't tell you about too."""),
    Scenario(
        "thorough-tour", handoff=True, age=6, budget=1.0,
        parent="""You're careful and curious, and you want to see everything Studio can do before you trust it.
Go through every part of Studio's home page one by one: Pictures, Words, Letters, Instruments, Colors and
New Rooms. In each, really make something (use your photo, record your voice where it offers, type real
words), then check that it shows up where Studio says it will, including the preview of Purple if there is
one. Read what each page tells you and notice when it's unclear or wrong.""",
        goal="a pack with a bit of everything: the dog's name with your photo, grandma's voice on G, an instrument, "
             "a new color, and one little game room",
        kid=f"""You're a curious 6-year-old. {EVERY_ROOM} Type the words your parent told you about, press the
letters, play the instrument in Music, and play the game room until it's over."""),
    Scenario(
        "phone-parent", viewport="390x844", age=5, budget=0.9,
        parent="""You're making this on your phone on the couch, so Studio is on a small screen. Make the
things below; notice anything cut off, too small to tap, hidden behind something, or that needs scrolling
you wouldn't think to do.""",
        goal="the dog's name with your photo, and a picture keyboard room with family words",
        kid=f"You're 5. {EVERY_ROOM}"),
    Scenario(
        "toddler-masher", age=3, budget=1.0,
        parent="""You're a tired parent with five minutes. Do the fastest thing that gets a photo and a couple
of family words onto Purple, and don't read more than you have to.""",
        goal="the backyard photo and the word mama",
        kid="""You're 3. You mash the keyboard: many keys fast, the same key over and over, holding keys down for
a few seconds (space, escape, enter, letters), and pressing escape and numbers to jump between rooms quickly.
Report anything that gets stuck, crashes, looks broken, gets loud and won't stop, or lands somewhere a
3-year-old can't get back from."""),
    Scenario(
        "coder-kid", age=9, budget=0.9,
        parent="""You're a parent who once took a coding class. Make a New Room starting from one of Studio's
starter rooms and open its code. Don't read all of it: the settings in CAPITALS near the top are the easy
part. Change two numbers there and one word the room shows, try it in the preview to see your change, then
on purpose make one mistake (a typo in a name) to see what Studio tells you. Fix it and download.""",
        goal="a game room where you changed two numbers and a word in the code yourself",
        kid="""You're 9 and you love code. Play the room your parent made and look for what they changed. Then
go to Art, Music or Blocks and press Esc, then Space, to open the side where you write code, and try
things: math, words, mistakes on purpose, very long lines, and code that never ends. Report errors a
9-year-old couldn't understand, and anything that freezes."""),
]

BY_NAME = {s.name: s for s in SCENARIOS}
