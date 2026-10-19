// What Studio itself makes audible outside the live Purple: synth notes for the instrument sliders.
import { SYNTH_RATE, defaults, noteFrequency, renderNote, type BaseName, type Params } from "@sdk";
import { GRID_ROWS, INSTRUMENTS, SAMPLE_VOLUME, pitchFor } from "@sdk/purple/sounds";
import { clipToBuffer, playBuffer } from "./audio";
import { draft } from "./state";

const notes = new Map<string, AudioBuffer>();

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
  playBuffer(buffer, SAMPLE_VOLUME);
}

// A letter-row key on the Music grid; false when the key isn't on it.
export function playGridKey(instrument: string, key: string): boolean {
  const row = GRID_ROWS.findIndex((r) => r.includes(key));
  if (row < 0) return false;
  const { note, octave } = pitchFor(row, GRID_ROWS[row].indexOf(key));
  playNote(instrument, note, octave);
  return true;
}
