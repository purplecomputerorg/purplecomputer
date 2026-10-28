import type { Clip } from "./audio";
import type { Picture } from "./photo";
import type { TemplateDraft } from "./examples";
import type { Rule } from "./rules";
import { roomTitle, slug } from "@sdk/pack";
import type { RoomFileKind } from "@sdk/pack";
import type { Theme } from "@sdk/purple/theme";
import { voiceClipFilename } from "@sdk/purple/sounds";
import type { BaseName, Params } from "@sdk/purple/synth";
import { asSaid } from "@sdk/says";

// Set false to hide the Rooms page, Room guide, and pack.room. Mutable so tests can flip it.
export const features = { rooms: true };

// A sample is one of Studio's examples, being tried: Studio's Purple plays it, the download leaves it out.
// Anything the family makes or changes is theirs and goes in their Purple Pack (kept) until they take it out.
export interface Keepable { kept?: boolean; sample?: boolean }
// means: what Play says when they ask what or who the word is.
export interface WordEntry extends Keepable { word: string; emoji: string; means?: string }
export interface SynonymEntry extends Keepable { alias: string; word: string }
// said: the words Purple reads, when the family typed them instead of recording.
export interface Phrase extends Keepable { text: string; clip: Clip; said?: string }
export interface Letter extends Keepable { clip: Clip; said?: string }
// title: the name as the family typed it, which Purple shows as is; name is its file name in the pack.
export interface Instrument extends Keepable { name: string; title?: string; base: BaseName; params: Params }
// What a room's Python is generated from, kept so it reopens: rules or a form. Null when the Python is the room's own.
export type Made = { kind: "rules"; rules: Rule[] } | TemplateDraft;
// The typed-answer trivia form is gone: a room made with it keeps its Python.
export const madeOf = (made: unknown): Made | null => (made && (made as { kind: string }).kind !== "trivia" ? made as Made : null);
export interface RoomDraft extends Keepable { name: string; source: string; made: Made | null }
// A picture or sound the pack's rooms draw with picture("name") and play with sound("name"), as Purple reads it.
// shelfId: for a picture, the one on the family's shelf (shelf.ts) it was made from.
export interface RoomFile extends Keepable { kind: RoomFileKind; name: string; data: Uint8Array; shelfId?: string }

// Saved in the browser (saved.ts), so loads can predate any field: a new top-level field just needs its emptyDraft value,
// but a new field inside an item (a room, a picture) needs a step in saved.ts's upgrade or an optional type.
export interface Draft {
  // The pack's id on Purple, made once per Purple Pack, so downloading it again under any name replaces it.
  id: string;
  name: string;
  pictures: Picture[];
  letters: Record<string, Letter>;
  phrases: Phrase[];
  words: WordEntry[];
  synonyms: SynonymEntry[];
  ranked: string[];
  instruments: Instrument[];
  rooms: RoomDraft[];
  roomFiles: RoomFile[];
  theme: Theme | null;
  // The colors are one piece: this says whether they're added.
  colors: Keepable;
}

const ADJECTIVES = ["sunny", "happy", "bouncy", "cozy", "fuzzy", "giggly", "jolly", "lucky", "merry", "silly", "sparkly", "sleepy", "speedy", "starry", "sweet", "tiny", "wiggly", "zippy", "brave", "bright"];
const ANIMALS = ["otter", "panda", "koala", "puppy", "kitten", "bunny", "duck", "fox", "owl", "penguin", "turtle", "whale", "zebra", "llama", "frog", "bear", "seal", "moose", "goat", "hippo"];
const pick = (list: string[]) => list[Math.floor(Math.random() * list.length)];
export const packWords = () => `purple-${pick(ADJECTIVES)}-${pick(ANIMALS)}`;
// Names Studio used to give, which looked out of date after the next day's edits.
const DATED = /^purple-\d{4}-\d{2}-\d{2}$/;

export const emptyDraft = (): Draft => ({
  id: `pack-${crypto.randomUUID().slice(0, 8)}`,
  name: packWords(),
  pictures: [],
  letters: {},
  phrases: [],
  words: [],
  synonyms: [],
  ranked: [],
  instruments: [],
  rooms: [],
  roomFiles: [],
  theme: null,
  colors: {},
});

export const draft: Draft = emptyDraft();

// Pages hold this one object, so another Purple Pack (reopened, recalled, or a fresh start) goes into it in place.
export function replaceDraft(d: Draft = emptyDraft()) {
  Object.assign(draft, d, DATED.test(d.name) && { name: packWords() });
  changed();
}

export { slug } from "@sdk/pack";

// A file name from what the family typed that nothing else uses: "Fairy Bells", then fairy-bells-2.
export function freeName(text: string, taken: (name: string) => boolean, fallback = "untitled"): string {
  const base = slug(text).slice(0, 40).replace(/-$/, "") || fallback;
  let name = base;
  for (let n = 2; taken(name); n++) name = `${base}-${n}`;
  return name;
}
// Purple finds a phrase's recording by its words as said, whatever their capitals, so these match the same one.
const sameWords = (a: string, b: string) => voiceClipFilename(asSaid(a)) === voiceClipFilename(asSaid(b));
export const phraseFor = (text: string) => (text.trim() ? draft.phrases.find((p) => sameWords(p.text, text)) : undefined);
// "No sound" for some words is a recording of silence: Purple plays a family's recording in place of its own voice.
export const QUIET: Clip = { samples: new Float32Array(2205), rate: 22050 };
export const isQuiet = (clip: Clip) => clip.samples.every((s) => s === 0);
// The family's recording of these words, in place of the one before; null goes back to Purple's voice.
export function putPhrase(text: string, clip: Clip | null, kept = false, said?: string) {
  kept ||= !!phraseFor(text)?.kept;
  draft.phrases = [...draft.phrases.filter((p) => !sameWords(p.text, text)), ...(clip ? [{ text, clip, kept, said }] : [])];
  changed();
}
// Whether Python names a file, in either quote: picture("dog"), CARDS = ['dog'].
export const names = (source: string, name: string) => source.includes(`"${name}"`) || source.includes(`'${name}'`);
export const titleOf = (p: { name: string; title?: string }) => p.title || roomTitle(p.name);

// Trying one of Studio's examples replaces the last one tried, unless the family changed or added it.
export const withSample = <T extends Keepable>(list: T[], item: T): T[] => [...list.filter(isTheirs), { ...item, sample: true }];
// Changed or added: an example only tried isn't the family's yet, so their lists leave it out.
export const isTheirs = (x: Keepable) => !x.sample || !!x.kept;
// Changing one of Studio's examples makes it the family's, so it goes in their Purple Pack. Their own stay as they are.
export function mine(x: Keepable) {
  if (x.sample) Object.assign(x, { sample: false, kept: true });
}
export function keep(x: Keepable, kept: boolean) {
  Object.assign(x, { sample: false, kept });
  changed();
}

export interface Piece { id: string; section: string; label: string; one: string; items: Keepable[] }

// Everything in the draft by kind, with the Studio section it's made on.
export function allPieces(): Piece[] {
  return [
    { id: "pictures", section: "pictures", label: "pictures", one: "picture", items: draft.pictures },
    { id: "letter_recordings", section: "keys", label: "letters in your voice", one: "letter in your voice", items: Object.values(draft.letters) },
    { id: "phrases", section: "words", label: "words in your voice", one: "word in your voice", items: draft.phrases },
    { id: "words", section: "words", label: "words", one: "word", items: draft.words },
    { id: "autocomplete_picks", section: "words", label: "words suggested first", one: "word suggested first", items: draft.ranked.map((word) => ({ kept: true, word })) },
    { id: "synonyms", section: "words", label: "nicknames", one: "nickname", items: draft.synonyms },
    { id: "instruments", section: "instruments", label: "instruments", one: "instrument", items: draft.instruments },
    { id: "rooms", section: "rooms", label: "rooms", one: "room", items: draft.rooms },
    { id: "room_files", section: "rooms", label: "room pictures and sounds", one: "room picture or sound", items: draft.roomFiles },
    { id: "colors", section: "colors", label: "sets of colors", one: "set of colors", items: draft.theme ? [draft.colors] : [] },
  ];
}

// The parts of the draft each Studio section makes, so one section can be cleared on its own.
const SECTION_FIELDS: Record<string, (keyof Draft)[]> = {
  pictures: ["pictures"], keys: ["letters"], words: ["words", "synonyms", "ranked", "phrases"], instruments: ["instruments"], rooms: ["rooms", "roomFiles"], colors: ["theme", "colors"],
};
export const hasWork = (section?: string) => allPieces().some((p) => (!section || p.section === section) && p.items.length);
export function clearSection(section: string) {
  const fresh = emptyDraft();
  for (const k of SECTION_FIELDS[section]) Object.assign(draft, { [k]: fresh[k] });
  changed();
}

export type Count = Piece & { count: number };
const counted = (which: (i: Keepable) => boolean): Count[] => allPieces()
  .map((p) => ({ ...p, items: p.items.filter(which) }))
  .map((p) => ({ ...p, count: p.items.length }))
  .filter((p) => p.count > 0);
export const countOf = (p: Count) => `${p.count} ${p.count === 1 ? p.one : p.label}`;
// What the family has added (the download), and what's left out: examples tried as they are, and what they took out.
export const pieces = () => counted((i) => !!i.kept);
export const notInPieces = () => counted((i) => !i.kept);

type Listener = () => void;
const listeners = new Set<Listener>();
export const onChange = (fn: Listener) => listeners.add(fn);
export const changed = () => listeners.forEach((fn) => fn());
// On each change while el is on the page, starting once it's there; after it leaves, never again.
export function whileShown(el: HTMLElement, fn: Listener) {
  let seen = false;
  const each = () => (el.isConnected ? (seen = true, fn()) : seen && listeners.delete(each));
  listeners.add(each);
}
