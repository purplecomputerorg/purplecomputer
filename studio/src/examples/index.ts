// Every room Studio starts from, in one place: the forms (picture keyboard, picture quiz) that write a
// room's Python, and the starter rooms the Rooms page and the Room guide show. Form text goes into the code
// only as JSON string literals, which are valid Python strings, so nothing typed can become code.
import { PURPLE } from "@sdk";
import beats from "./beats.py?raw";
import explore from "./explore.py?raw";
import garden from "./garden.py?raw";
import memory from "./memory.py?raw";
import snake from "./snake.py?raw";
import story from "./story.py?raw";
import type { Made, RoomDraft } from "../state";

const SPECIAL_KEYS: string[] = PURPLE.room.keys;
const lit = (s: string) => JSON.stringify(s);

// What on_key receives for something typed into a key field: one lowercase character or a key word.
export function normalizeKey(v: string): string | null {
  const s = v.trim().toLowerCase();
  if (SPECIAL_KEYS.includes(s)) return s;
  const chars = [...s];
  return chars.length ? chars[0] : null;
}

// An emoji field also takes the name of one of the pack's pictures, and a note field one of its sounds:
// the room tells them apart by what the pack has.
export interface QuizChoice { emoji: string; word: string }
export interface QuizRow { question: string; emoji: string; right: QuizChoice; others: QuizChoice[] }
export interface QuizData { rows: QuizRow[] }
// voice: a recording of the word that Purple plays instead of saying it; drafts from before it lack one.
export interface Sound { emoji: string; word: string; voice?: string; note: string }
export interface SoundboardData { rows: (Sound & { key: string })[]; other: Sound }
export type TemplateDraft = { kind: "quiz"; data: QuizData } | { kind: "soundboard"; data: SoundboardData };

export const MAX_OTHERS = 3;
const filled = (c: QuizChoice) => !!(c.emoji.trim() || c.word.trim());

export function quizSource({ rows }: QuizData): string {
  const choice = (c: QuizChoice) => `(${lit(c.emoji.trim())}, ${lit(c.word.trim())})`;
  const questions = rows.filter((r) => r.question.trim() && filled(r.right))
    .map((r) => `    (${lit(r.question.trim())}, ${lit(r.emoji.trim())}, ${choice(r.right)}, [${r.others.filter(filled).slice(0, MAX_OTHERS).map(choice).join(", ")}]),`);
  return `import random

from purple import *

# Made with the picture quiz form in Purple Studio. Purple reads each question out loud, and a number key
# picks a picture. A wrong pick goes away, so every question ends on the right one. Space asks again.

# Each question: what Purple asks, its picture, the right choice, and the other choices. A choice is its
# picture (an emoji, or one of your pictures) and the word Purple says when it's picked.
QUESTIONS = [
${questions.join("\n")}
]

asked = 0
choices = []
spots = []
waiting = False


def place(x, y, thing, side):
    """An emoji, or one of the pack's pictures fitted in a side by side square. Returns the square it's in."""
    if thing not in images:
        grid.set(x, y, thing, size=side)
        return (x, y)
    w, h = images[thing]
    p = picture(thing, side) if w >= h else picture(thing, max(1, round(side * w / h)), side)
    spot = (x + (side - p.w) // 2, y + (side - p.h) // 2)
    grid.set(spot, p)
    return spot


def ask_next():
    global choices, spots, waiting
    waiting = False
    clear()
    if asked == len(QUESTIONS):
        show("🎉")
        write("That was all of them!")
        play("G5")
        game_over("Press a key to play again")
        return
    question, face, right, others = QUESTIONS[asked]
    if face:
        place(10, 0, face, 4)
    choices = [right] + others
    random.shuffle(choices)
    left = (grid.w - 6 * len(choices) + 3) // 2
    spots = []
    for i, (thing, word) in enumerate(choices):
        x = left + 6 * i
        grid.set(x + 1, 8, str(i + 1))
        spots.append((place(x, 5, thing or word, 3), (x + 1, 8)))
    write(question)
    say(question)


def pick(i):
    global asked, waiting
    thing, word = choices[i]
    if word:
        say(word)
    if choices[i] == QUESTIONS[asked][2]:
        play("G5")
        asked += 1
        waiting = True
        after(1.5, ask_next)
    else:
        play("E3")
        for spot in spots[i]:
            grid.erase(spot)
        spots[i] = None


def on_key(key):
    if waiting:
        return
    if key == "space":
        say(QUESTIONS[asked][0])
    elif key.isdigit() and 0 < int(key) <= len(choices) and spots[int(key) - 1]:
        pick(int(key) - 1)


ask_next()
`;
}

export function soundboardSource({ rows, other }: SoundboardData): string {
  const sound = (s: Sound) => `(${lit(s.emoji.trim())}, ${lit(s.word.trim())}, ${lit(s.voice ?? "")}, ${lit(s.note.trim())})`;
  const keys = rows.map((r) => [normalizeKey(r.key), r] as const).filter(([k]) => k)
    .map(([k, r]) => `    ${lit(k!)}: ${sound(r)},`);
  return `from purple import *

# Made with the picture keyboard form in Purple Studio. Each key shows its picture, says its word, and plays its sound.

# Each key's picture (an emoji, or one of your pictures), word, your recording of the word (blank: Purple says it),
# and sound (a note like "C4", or one of your sounds).
KEYS = {
${keys.join("\n")}
}
# What every other key does. A blank picture shows the key itself.
OTHER_KEYS = ${sound(other)}

show("🎹")


def on_key(key):
    face, word, voice, noise = KEYS.get(key, OTHER_KEYS)
    show(picture(face) if face in images else face or key)
    if voice in sounds:
        sound(voice)
    elif word:
        say(word)
    if noise in sounds:
        sound(noise)
    elif noise:
        play(noise)
`;
}

const choice = (emoji: string, word: string): QuizChoice => ({ emoji, word });

export const TEMPLATES = {
  soundboard: {
    name: "picture-keyboard",
    label: "A picture keyboard",
    icon: "🎹",
    about: "Each key shows a picture, says a word, and plays a sound. Try your own photos and voice.",
    source: soundboardSource,
    defaults: (): SoundboardData => ({
      rows: [
        { key: "c", emoji: "🐄", word: "cow", voice: "", note: "C4" },
        { key: "d", emoji: "🐶", word: "dog", voice: "", note: "D4" },
        { key: "p", emoji: "🐖", word: "pig", voice: "", note: "E4" },
        { key: "s", emoji: "🐑", word: "sheep", voice: "", note: "G4" },
      ],
      other: { emoji: "", word: "", voice: "", note: "A4" },
    }),
  },
  quiz: {
    name: "picture-quiz",
    label: "A picture quiz",
    icon: "❓",
    about: "Purple asks out loud, and a number key picks the picture: an emoji or your own photo. No reading needed.",
    source: quizSource,
    defaults: (): QuizData => ({ rows: [
      { question: "Which one says moo?", emoji: "", right: choice("🐄", "cow"), others: [choice("🐖", "pig"), choice("🐑", "sheep")] },
      { question: "Which one can fly?", emoji: "", right: choice("🐦", "bird"), others: [choice("🐟", "fish"), choice("🐢", "turtle")] },
      { question: "What do we need in the rain?", emoji: "🌧️", right: choice("☂️", "umbrella"), others: [choice("🕶️", "sunglasses"), choice("🩴", "flip flops")] },
    ] }),
  },
} as const;

export const templateSource = (t: TemplateDraft) => (t.kind === "quiz" ? quizSource(t.data) : soundboardSource(t.data));

export interface Example { name: string; icon: string; label: string; about: string; source: string }

// Starters: each one a kind of room families asked for, short enough to read and change.
export const EXAMPLES: Example[] = [
  { name: "explore", icon: "🗺️", label: "A world to walk around", about: "Walk with the arrows and find the stars to open the house. Draw the maps yourself with emoji or your own photos, and join them with numbered doors.", source: explore },
  { name: "story", icon: "📖", label: "A story with choices", about: "Each page shows an emoji or your own photo, read in Purple's voice or yours. Number keys pick what happens next.", source: story },
  { name: "memory", icon: "🃏", label: "Memory", about: "Turn over cards to find the pairs, alone or taking turns. The cards can be your own photos.", source: memory },
  { name: "garden", icon: "🌻", label: "A garden", about: "Plant seeds on the letter keys and water them to grow. It remembers the garden.", source: garden },
  { name: "beats", icon: "🥁", label: "A beat maker", about: "Turn beats on and off with the keys, then Space plays them round and round.", source: beats },
  { name: "snake", icon: "🐍", label: "A wandering snake", about: "Press a key and a snake crawls to it, lighting it up with a note.", source: snake },
];

// Rules aren't offered any more, but a room made from them still opens in them.
const MADE_ICONS: Record<Made["kind"], string> = { rules: "🧱", quiz: TEMPLATES.quiz.icon, soundboard: TEMPLATES.soundboard.icon };
export const IDEA = "💡";
// The room's emoji, in Studio and in Purple's room picker: the family's pick, else its starter's (garden-3 came
// from garden), else the lightbulb that Python with no starter shows.
export const roomIcon = (room: RoomDraft) =>
  room.icon || (room.made ? MADE_ICONS[room.made.kind] : (EXAMPLES.find((e) => e.name === room.name.replace(/-\d+$/, ""))?.icon ?? IDEA));

// A blank room's first Python, one of a few tiny ones to pick from while it's still untouched.
export const BLANK_ROOMS = [
  { icon: "🌸", label: "Flowers", source: `from purple import *

# Place these symbols on the 26x12 grid, as (across, down)
grid.set(10, 5, "👋")
grid.set(15, 5, "🌟")

# A ring around one square
grid.cursor(12, 7)


# Purple calls this each time a key is pressed
def on_key(key):
    if key in ARROWS:
        grid.move(key)
    else:
        grid.set(grid.here, "🌸")
` },
  { icon: "🎨", label: "Paint", source: `from purple import *

# Each key adds its own color to the pot, the one on its sticker
pot = []
status("Press a letter or number key to mix its color into the pot, Space empties it")
grid.set(9, 2, "tile", size=8)


# Purple calls this each time a key is pressed
def on_key(key):
    if key in KEY_COLORS:
        pot.append(KEY_COLORS[key])
        # The color just added, beside the pot
        grid.set(5, 5, KEY_COLORS[key], size=2)
    elif key == "space":
        pot.clear()
        grid.erase(5, 5)
    # Only the last 6 colors count, so a new one always shows
    del pot[:-6]
    # Mixed like real paint: yellow and blue make green
    grid.set(9, 2, mix(*pot) if pot else "tile", size=8)
` },
  { icon: "📷", label: "Photo", source: `import random

from purple import *

# Your photos: add them below, under Pictures and sounds for your rooms
photos = list(images)
show("📷")


# Purple calls this each time a key is pressed
def on_key(key):
    if photos:
        show(picture(random.choice(photos)))
` },
];
