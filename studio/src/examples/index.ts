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
export interface Sound { emoji: string; word: string; note: string }
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
  const sound = (s: Sound) => `(${lit(s.emoji.trim())}, ${lit(s.word.trim())}, ${lit(s.note.trim())})`;
  const keys = rows.map((r) => [normalizeKey(r.key), r] as const).filter(([k]) => k)
    .map(([k, r]) => `    ${lit(k!)}: ${sound(r)},`);
  return `from purple import *

# Made with the picture keyboard form in Purple Studio. Each key shows its picture, says its word, and plays its sound.

# Each key's picture (an emoji, or one of your pictures), word, and sound (a note like "C4", or one of your sounds).
KEYS = {
${keys.join("\n")}
}
# What every other key does. A blank picture shows the key itself.
OTHER_KEYS = ${sound(other)}

show("🎹")


def on_key(key):
    face, word, noise = KEYS.get(key, OTHER_KEYS)
    show(picture(face) if face in images else face or key)
    if word:
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
    about: "Each key shows a picture, says a word, and plays a sound. Use your own photos and voice: G is Grandma saying hi. For the littlest ones.",
    source: soundboardSource,
    defaults: (): SoundboardData => ({
      rows: [
        { key: "c", emoji: "🐄", word: "cow", note: "C4" },
        { key: "d", emoji: "🐶", word: "dog", note: "D4" },
        { key: "p", emoji: "🐖", word: "pig", note: "E4" },
        { key: "s", emoji: "🐑", word: "sheep", note: "G4" },
      ],
      other: { emoji: "", word: "", note: "A4" },
    }),
  },
  quiz: {
    name: "picture-quiz",
    label: "A picture quiz",
    icon: "❓",
    about: "Purple asks a question out loud, and your kid presses 1, 2, or 3 to pick a picture. No reading, no typing, no score.",
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
  { name: "explore", icon: "🗺️", label: "A world to walk around", about: "Walk with the arrows, find the stars, and the door opens. The world is drawn with letters you can change.", source: explore },
  { name: "garden", icon: "🌻", label: "A garden", about: "Plant seeds and water them. It remembers the garden for next time.", source: garden },
  { name: "beats", icon: "🥁", label: "A beat maker", about: "Each row of keys is a drum and each key a beat: press one to turn it on or off, then Space to hear them play round and round, and again to stop.", source: beats },
  { name: "memory", icon: "🃏", label: "Memory", about: "Play alone or take turns turning over cards to find the pairs. Each card is a letter key: press it to turn the card over. No score: it ends when every pair is found.", source: memory },
  { name: "story", icon: "📖", label: "A story with choices", about: "Purple reads each page, and number keys pick what happens next.", source: story },
  { name: "snake", icon: "🐍", label: "A wandering snake", about: "The smallest room: a snake that moves a square each time an arrow is pressed, leaving flowers behind it.", source: snake },
];

export const BLANK_ROOM = `from purple import *

show("👋")


def on_key(key):
    show(key)
`;
