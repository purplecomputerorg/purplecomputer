// Music and voice facts come from export.json; the two naming rules Studio needs live are ported
// and checked against examples in the export.
import exported from "./export.json";

const { music, voice } = exported;

// packs/core-sounds/content/letters/<key>.wav: one clip per key, lowercase filename.
export const LETTER_KEYS: string[] = voice.letter_keys;
export const CLIP_SAMPLE_RATE: number = voice.sample_rate;

// tts.voice_clip_filename
export function voiceClipFilename(text: string): string {
  return text.trim().toLowerCase().replaceAll(" ", "_") + ".wav";
}

export const INSTRUMENTS: readonly string[] = music.instruments;
export const GRID_ROWS: string[][] = music.grid_rows;
export const PERCUSSION_ROW: string[] = music.percussion_row;

// music_constants.pitch_filename: "C#4" -> "cs4"
export function pitchFilename(note: string, octave: number): string {
  return note.toLowerCase().replace("#", "s") + octave;
}

const CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11];
const ROW_OCTAVE_BASE = [4, 3, 2];

// music_constants.pitch_for with the default root (C) and no octave shift.
export function pitchFor(row: number, col: number, root = 0, octaveShift = 0): { note: string; octave: number } {
  const semis = root + 12 * (ROW_OCTAVE_BASE[row] + octaveShift) + MAJOR_SCALE[col % 7] + 12 * Math.floor(col / 7);
  return { note: CHROMATIC[semis % 12], octave: Math.floor(semis / 12) };
}

export function noteFrequency(note: string, octave: number): number {
  const semis = CHROMATIC.indexOf(note) + 12 * (octave + 1);
  return 440 * 2 ** ((semis - 69) / 12);
}

export interface SamplePitch { file: string; note: string; octave: number; freq: number }

// Every pitch the Music grid can reach, the same set every core instrument directory ships.
export const SAMPLE_PITCHES: SamplePitch[] = music.pitches.map((p) => ({ ...p, freq: noteFrequency(p.note, p.octave) }));
