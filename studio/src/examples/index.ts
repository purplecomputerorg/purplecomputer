// Every room Studio starts from, in one place: the forms (trivia, soundboard) that write a room's
// Python, and the starter rooms the Rooms page and the Room guide show. Form text goes into the code
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

export interface TriviaRow { emoji: string; question: string; answer: string }
export interface TriviaData { rows: TriviaRow[] }
export interface Sound { emoji: string; word: string; note: string }
export interface SoundboardData { rows: (Sound & { key: string })[]; other: Sound }
export type TemplateDraft = { kind: "trivia"; data: TriviaData } | { kind: "soundboard"; data: SoundboardData };

export function triviaSource({ rows }: TriviaData): string {
  const questions = rows.filter((r) => r.question.trim() && r.answer.trim())
    .map((r) => `    (${lit(r.emoji.trim())}, ${lit(r.question.trim())}, ${lit(r.answer.trim())}),`);
  return `from purple import *

# Made with the trivia form in Purple Studio. Type an answer and press Enter.
QUESTIONS = [
${questions.join("\n")}
]

for picture, question, answer in QUESTIONS:
    clear()
    show(picture)
    write(question)
    say(question)
    if ask("Your answer").strip().lower() == answer.lower():
        play("C5")
        say("Yes!")
    else:
        say(f"Good try! It was {answer}.")

clear()
show("🎉")
say("That was all of them!")
`;
}

export function soundboardSource({ rows, other }: SoundboardData): string {
  const sound = (s: Sound) => `(${lit(s.emoji.trim())}, ${lit(s.word.trim())}, ${lit(s.note.trim())})`;
  const keys = rows.map((r) => [normalizeKey(r.key), r] as const).filter(([k]) => k)
    .map(([k, r]) => `    ${lit(k!)}: ${sound(r)},`);
  return `from purple import *

# Made with the soundboard form in Purple Studio. Every key shows something, says it, and plays a note.
SOUNDS = {
${keys.join("\n")}
}
OTHER_KEYS = ${sound(other)}

show("🎹")


def on_key(key):
    picture, word, note = SOUNDS.get(key, OTHER_KEYS)
    show(picture or key)
    if word:
        say(word)
    if note:
        play(note)
`;
}

export const TEMPLATES = {
  trivia: {
    label: "Trivia",
    about: "Questions with a picture, answered by typing. For kids who read.",
    source: triviaSource,
    defaults: (): TriviaData => ({ rows: [
      { emoji: "🦕", question: "Which dinosaur had a very long neck?", answer: "brachiosaurus" },
      { emoji: "🦖", question: "Which dinosaur had tiny arms and big teeth?", answer: "t rex" },
      { emoji: "🦴", question: "What do we call bones that turned to stone?", answer: "fossils" },
    ] }),
  },
  soundboard: {
    label: "Soundboard",
    about: "Each key shows a picture, says a word, and plays a note. For the littlest ones.",
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
} as const;

export const templateSource = (t: TemplateDraft) => (t.kind === "trivia" ? triviaSource(t.data) : soundboardSource(t.data));

export interface Example { name: string; icon: string; label: string; about: string; source: string }

// Starters: each one a kind of room families asked for, short enough to read and change.
export const EXAMPLES: Example[] = [
  { name: "explore", icon: "🗺️", label: "A world to walk around", about: "Walk with the arrows, find stars, meet a fox. The world is drawn with letters you can change.", source: explore },
  { name: "garden", icon: "🌻", label: "A garden", about: "Plant seeds and water them. It remembers the garden for next time.", source: garden },
  { name: "beats", icon: "🥁", label: "A beat maker", about: "Turn beats on and off, then press Enter to hear them loop.", source: beats },
  { name: "memory", icon: "🃏", label: "Memory for two", about: "Take turns turning over cards to find the pairs.", source: memory },
  { name: "story", icon: "📖", label: "A story with choices", about: "Purple reads each page, and number keys pick what happens next.", source: story },
  { name: "snake", icon: "🐍", label: "Snake", about: "The smallest game: a snake that keeps moving. Arrow keys turn it.", source: snake },
];

export const BLANK_ROOM = `from purple import *

show("👋")
say("Hello!")


def on_key(key):
    show(key)
`;
