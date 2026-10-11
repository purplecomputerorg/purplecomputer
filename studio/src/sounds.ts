// What Studio itself makes audible (the room stage, the instrument sliders): synth notes, the core
// percussion clips, and the browser's voice standing in for Purple's.
import { PURPLE, SYNTH_RATE, defaults, noteFrequency, renderNote, type BaseName, type Params } from "@sdk";
import { GRID_ROWS, INSTRUMENTS, pitchFor } from "@sdk/purple/sounds";
import { audioContext, clipToBuffer, playBuffer } from "./audio";
import { draft } from "./state";

const DRUM_URLS = import.meta.glob("../../packs/core-sounds/content/[0-9].ogg", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const DRUM_KEYS: Record<string, string> = PURPLE.room.drum_keys;
const notes = new Map<string, AudioBuffer>();
const drums = new Map<string, Promise<AudioBuffer | null>>();

export function voiceFor(instrument: string): { base: BaseName; params: Params } {
  const inst = draft.instruments.find((i) => i.name === instrument);
  if (inst) return inst;
  const base = (INSTRUMENTS as readonly string[]).includes(instrument) ? (instrument as BaseName) : "marimba";
  return { base, params: defaults(base) };
}

export function playNote(instrument: string, note: string, octave: number): void {
  const { base, params } = voiceFor(instrument);
  const id = `${base}|${JSON.stringify(params)}|${note}${octave}`;
  let buffer = notes.get(id);
  if (!buffer) {
    if (notes.size > 200) notes.clear();
    buffer = clipToBuffer({ samples: renderNote(base, params, noteFrequency(note, octave)), rate: SYNTH_RATE });
    notes.set(id, buffer);
  }
  playBuffer(buffer);
}

// A letter-row key on the Music grid; false when the key isn't on it.
export function playGridKey(instrument: string, key: string): boolean {
  const row = GRID_ROWS.findIndex((r) => r.includes(key));
  if (row < 0) return false;
  const { note, octave } = pitchFor(row, GRID_ROWS[row].indexOf(key));
  playNote(instrument, note, octave);
  return true;
}

export function playDrum(nameOrDigit: string): void {
  const digit = nameOrDigit in DRUM_KEYS ? nameOrDigit : Object.entries(DRUM_KEYS).find(([, n]) => n === nameOrDigit.toLowerCase())?.[0];
  if (!digit) return;
  if (!drums.has(digit)) {
    const url = Object.entries(DRUM_URLS).find(([path]) => path.endsWith(`/${digit}.ogg`))?.[1];
    drums.set(digit, url ? fetch(url).then((r) => r.arrayBuffer()).then((b) => audioContext().decodeAudioData(b)).catch(() => null) : Promise.resolve(null));
  }
  void drums.get(digit)!.then((buffer) => buffer && playBuffer(buffer));
}

export function say(text: string): void {
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.95;
  speechSynthesis.speak(u);
}

export const hush = () => ("speechSynthesis" in window) && speechSynthesis.cancel();
