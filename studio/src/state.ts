import type { Clip } from "./audio";
import type { Picture } from "./photo";
import { packId as sdkPackId } from "@sdk/pack";
import { APP_BG_DARK, DEFAULT_BG_DARK, ROW_HUES } from "@sdk/purple/art";
import type { BaseName, Params } from "@sdk/purple/synth";
import type { RoomProgram } from "@sdk/room";

export interface WordEntry { word: string; emoji: string }
export interface SynonymEntry { alias: string; word: string }
export interface Phrase { text: string; clip: Clip }
export interface Instrument { name: string; base: BaseName; params: Params }
export interface Theme { background: string; surface: string; hues: { qwerty: number; asdf: number; zxcv: number } }
// A room is its program (what Purple runs) plus the Blockly workspace it was built from (so it can be reopened).
export interface RoomDraft { program: RoomProgram; blocks: unknown | null }

export interface Draft {
  familyName: string;
  pictures: Picture[];
  letters: Record<string, Clip>;
  phrases: Phrase[];
  words: WordEntry[];
  synonyms: SynonymEntry[];
  ranked: string[];
  instruments: Instrument[];
  rooms: RoomDraft[];
  theme: Theme | null;
}

export const DEFAULT_THEME: Theme = { background: APP_BG_DARK, surface: DEFAULT_BG_DARK, hues: { ...ROW_HUES } };

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
};

export { slug } from "@sdk/pack";
export const packId = (d: Draft = draft) => sdkPackId(d);

export interface Piece { label: string; count: number }

// What the parent has put in so far, for the summary and the download gate.
export function pieces(): Piece[] {
  return [
    { label: "photos", count: draft.pictures.length },
    { label: "letter recordings", count: Object.keys(draft.letters).length },
    { label: "phrases", count: draft.phrases.length },
    { label: "words", count: draft.words.length },
    { label: "synonyms", count: draft.synonyms.length },
    { label: "autocomplete picks", count: draft.ranked.length },
    { label: "instruments", count: draft.instruments.length },
    { label: "rooms", count: draft.rooms.length },
    { label: "colors", count: draft.theme ? 1 : 0 },
  ].filter((p) => p.count > 0);
}

type Listener = () => void;
const listeners = new Set<Listener>();
export const onChange = (fn: Listener) => listeners.add(fn);
export const changed = () => listeners.forEach((fn) => fn());
