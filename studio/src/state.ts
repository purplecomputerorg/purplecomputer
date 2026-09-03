import type { Clip } from "./audio";
import type { Picture } from "./photo";
import { APP_BG_DARK, DEFAULT_BG_DARK, ROW_HUES } from "./purple/art";
import type { BaseName, Params } from "./purple/synth";

export interface WordEntry { word: string; emoji: string }
export interface SynonymEntry { alias: string; word: string }
export interface Phrase { text: string; clip: Clip }
export interface Instrument { name: string; base: BaseName; params: Params }
export interface Theme { background: string; surface: string; hues: { qwerty: number; asdf: number; zxcv: number } }

export interface Draft {
  familyName: string;
  pictures: Picture[];
  letters: Record<string, Clip>;
  phrases: Phrase[];
  words: WordEntry[];
  synonyms: SynonymEntry[];
  ranked: string[];
  instruments: Instrument[];
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
  theme: null,
};

export const slug = (text: string) =>
  text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const packId = (d: Draft = draft) => `${slug(d.familyName) || "our-family"}-pack`;

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
    { label: "colors", count: draft.theme ? 1 : 0 },
  ].filter((p) => p.count > 0);
}

type Listener = () => void;
const listeners = new Set<Listener>();
export const onChange = (fn: Listener) => listeners.add(fn);
export const changed = () => listeners.forEach((fn) => fn());
