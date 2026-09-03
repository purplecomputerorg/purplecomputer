// Ported from purple_tui/tts.py, purple_tui/music_constants.py, and the core-sounds pack layout.

// packs/core-sounds/content/letters/<key>.wav: one clip per key, lowercase filename.
export const LETTER_KEYS = [..."abcdefghijklmnopqrstuvwxyz0123456789"];

// Same numbers Piper writes for the core clips (checked with the wave module on letters/a.wav).
export const CLIP_SAMPLE_RATE = 22050;
export const CLIP_CHANNELS = 1;

// tts.py: text.strip().lower().replace(" ", "_") + ".wav"
export function voiceClipFilename(text: string): string {
  return text.trim().toLowerCase().replaceAll(" ", "_") + ".wav";
}

export const INSTRUMENTS = ["marimba", "ukulele", "accordion", "glockenspiel"] as const;

// The Music room grid: three letter rows of ten keys, plus the percussion number row.
export const GRID_ROWS = ["qwertyuiop", "asdfghjkl;", "zxcvbnm,./"].map((r) => [...r]);
export const PERCUSSION_ROW = [..."1234567890"];
const MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11];
const ROW_OCTAVE_BASE = [4, 3, 2];

// music_constants.pitch_for with the default root (C) and no octave shift.
export function pitchFor(row: number, col: number, root = 0, octaveShift = 0): { note: string; octave: number } {
  const semis = root + 12 * (ROW_OCTAVE_BASE[row] + octaveShift) + MAJOR_SCALE[col % 7] + 12 * Math.floor(col / 7);
  return { note: CHROMATIC[semis % 12], octave: Math.floor(semis / 12) };
}

// music_constants.pitch_filename: "C#4" -> "cs4"
export function pitchFilename(note: string, octave: number): string {
  return note.toLowerCase().replace("#", "s") + octave;
}

const CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

export function noteFrequency(note: string, octave: number): number {
  const semis = CHROMATIC.indexOf(note) + 12 * (octave + 1);
  return 440 * 2 ** ((semis - 69) / 12);
}

export function noteFromFrequency(freq: number): { note: string; octave: number; cents: number } {
  const midi = 69 + 12 * Math.log2(freq / 440);
  const nearest = Math.round(midi);
  return { note: CHROMATIC[nearest % 12], octave: Math.floor(nearest / 12) - 1, cents: Math.round((midi - nearest) * 100) };
}

// The 67 pitches every core instrument directory ships (ls packs/core-sounds/content/marimba).
const SAMPLE_PITCH_LIST =
  "c1 d1 e1 f1 fs1 g1 a1 as1 b1 " +
  "c2 cs2 d2 ds2 e2 f2 fs2 g2 a2 as2 b2 c3 cs3 d3 ds3 e3 f3 fs3 g3 a3 as3 b3 " +
  "c4 cs4 d4 ds4 e4 f4 fs4 g4 a4 as4 b4 c5 cs5 d5 ds5 e5 f5 fs5 g5 a5 as5 b5 " +
  "c6 cs6 d6 ds6 e6 f6 fs6 g6 a6 as6 b6 c7 cs7 d7";

export interface SamplePitch { file: string; note: string; octave: number; freq: number }

export const SAMPLE_PITCHES: SamplePitch[] = SAMPLE_PITCH_LIST.split(" ").map((file) => {
  const octave = Number(file.slice(-1));
  const note = file.slice(0, -1).toUpperCase().replace("S", "#");
  return { file, note, octave, freq: noteFrequency(note, octave) };
});
