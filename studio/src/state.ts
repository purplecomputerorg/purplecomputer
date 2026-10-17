import type { Clip } from "./audio";
import type { Picture } from "./photo";
import type { TemplateDraft } from "./examples";
import { packId as sdkPackId, roomTitle, slug } from "@sdk/pack";
import type { Theme } from "@sdk/purple/theme";
import type { BaseName, Params } from "@sdk/purple/synth";

// Off until room customization ships: no Rooms page, Room guide, or pack.room. Mutable so tests can turn it on.
export const features = { rooms: false };

// Everything starts as a try: Studio's Purple plays it, and it goes in the download once the family
// adds it (kept). A sample is one of Studio's examples, tried and not yet changed or added.
export interface Keepable { kept?: boolean; sample?: boolean }
export interface WordEntry extends Keepable { word: string; emoji: string }
export interface SynonymEntry extends Keepable { alias: string; word: string }
export interface Phrase extends Keepable { text: string; clip: Clip }
export interface Letter extends Keepable { clip: Clip }
// title: the name as the family typed it, which Purple shows as is; name is its file name in the pack.
export interface Instrument extends Keepable { name: string; title?: string; base: BaseName; params: Params }
// A room is its Python (what Purple runs) plus what it was made from, blocks or a form, so either can be
// reopened. Both are null once the Python has been edited by hand.
export interface RoomDraft extends Keepable { name: string; source: string; blocks: unknown | null; template: TemplateDraft | null }

export interface Draft {
  familyName: string;
  pictures: Picture[];
  letters: Record<string, Letter>;
  phrases: Phrase[];
  words: WordEntry[];
  synonyms: SynonymEntry[];
  ranked: string[];
  instruments: Instrument[];
  rooms: RoomDraft[];
  theme: Theme | null;
  // The colors are one piece: this says whether they're added.
  colors: Keepable;
}


export const draft: Draft = {
  familyName: "",
  pictures: [],
  letters: {},
  phrases: [],
  words: [],
  synonyms: [],
  ranked: [],
  instruments: [],
  rooms: [],
  theme: null,
  colors: {},
};

export { slug } from "@sdk/pack";

// A file name from what the family typed that nothing else uses: "Fairy Bells", then fairy-bells-2.
export function freeName(text: string, taken: (name: string) => boolean, fallback = "untitled"): string {
  const base = slug(text).slice(0, 40).replace(/-$/, "") || fallback;
  let name = base;
  for (let n = 2; taken(name); n++) name = `${base}-${n}`;
  return name;
}
export const titleOf = (p: { name: string; title?: string }) => p.title || roomTitle(p.name);
export const packId = (d: Draft = draft) => sdkPackId(d);

// Trying one of Studio's examples replaces the last one tried, unless the family changed or added it.
export const withSample = <T extends Keepable>(list: T[], item: T): T[] => [...list.filter((x) => !x.sample || x.kept), { ...item, sample: true }];

export interface Piece { id: string; section: string; label: string; one: string; items: Keepable[] }

// Everything in the draft by kind, with the Studio section it's made on.
export function allPieces(): Piece[] {
  return [
    { id: "pictures", section: "pictures", label: "pictures", one: "picture", items: draft.pictures },
    { id: "letter_recordings", section: "voice", label: "keys in your voice", one: "key in your voice", items: Object.values(draft.letters) },
    { id: "phrases", section: "voice", label: "phrases in your voice", one: "phrase in your voice", items: draft.phrases },
    { id: "words", section: "words", label: "words", one: "word", items: draft.words },
    { id: "autocomplete_picks", section: "words", label: "words suggested first", one: "word suggested first", items: draft.ranked.map(() => ({ kept: true })) },
    { id: "synonyms", section: "words", label: "nicknames", one: "nickname", items: draft.synonyms },
    { id: "instruments", section: "instruments", label: "instruments", one: "instrument", items: draft.instruments },
    { id: "rooms", section: "rooms", label: "rooms", one: "room", items: draft.rooms },
    { id: "colors", section: "colors", label: "new colors", one: "new set of colors", items: draft.theme ? [draft.colors] : [] },
  ];
}

export interface Count { id: string; section: string; label: string; one: string; count: number }
const counted = (kept: boolean): Count[] => allPieces()
  .map(({ items, ...p }) => ({ ...p, count: items.filter((i) => !!i.kept === kept).length }))
  .filter((p) => p.count > 0);
// What the family has added (the download), and what they're still trying.
export const pieces = () => counted(true);
export const tryingPieces = () => counted(false);
export const addAll = () => allPieces().forEach((p) => p.items.forEach((i) => { i.kept = true; i.sample = false; }));

type Listener = () => void;
const listeners = new Set<Listener>();
export const onChange = (fn: Listener) => listeners.add(fn);
export const changed = () => listeners.forEach((fn) => fn());
