// Music and voice facts come from export.json; the two naming rules Studio needs live are ported
// and checked against examples in the export.
import exported from "./export.json";

const { music, voice } = exported;

// canvas/sounds.CLIP_NAMES: content/letters/<name>.wav, one clip per grid key, any of them.
export const LETTER_FILES: Record<string, string> = voice.letter_files;
export const LETTER_KEYS: string[] = Object.keys(LETTER_FILES);
export const CLIP_SAMPLE_RATE: number = voice.sample_rate;

// tts.voice_clip_filename
export function voiceClipFilename(text: string): string {
  return text.trim().toLowerCase().replaceAll(" ", "_") + ".wav";
}

// The four sampled instruments a pack instrument can be built on; rooms can also play the Synth, which
// Purple makes as it plays (dial_synth.py), and a Purple from before it plays the first of these instead.
export const INSTRUMENTS: readonly string[] = music.instruments;
export const NOTE_INSTRUMENTS: readonly string[] = [...music.instruments, music.synth];
export const GRID_ROWS: string[][] = music.grid_rows;
export const PERCUSSION_ROW: string[] = music.percussion_row;
export const SAMPLE_VOLUME: number = music.sample_volume;

// music_constants.pitch_filename: "C#4" -> "cs4"
export function pitchFilename(note: string, octave: number): string {
  return note.toLowerCase().replace("#", "s") + octave;
}

const CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11];
const ROW_OCTAVE_BASE = [4, 3, 2];

// music_constants.pitch_for, the root defaulting to C.
export function pitchFor(row: number, col: number, root = 0): { note: string; octave: number } {
  const semis = root + 12 * ROW_OCTAVE_BASE[row] + MAJOR_SCALE[col % 7] + 12 * Math.floor(col / 7);
  return { note: CHROMATIC[semis % 12], octave: Math.floor(semis / 12) };
}

// "C#4" -> ["C#", 4]; null for anything that is not a note name.
export function parseNote(text: string): [note: string, octave: number] | null {
  const m = /^([A-Ga-g])(#?)(\d)$/.exec(text.trim());
  return m ? [m[1].toUpperCase() + m[2], Number(m[3])] : null;
}

export function noteFrequency(note: string, octave: number): number {
  const semis = CHROMATIC.indexOf(note) + 12 * (octave + 1);
  return 440 * 2 ** ((semis - 69) / 12);
}

export interface SamplePitch { file: string; note: string; octave: number; freq: number }

// Every pitch the Music grid can reach, the same set every core instrument directory ships.
export const SAMPLE_PITCHES: SamplePitch[] = music.pitches.map((p) => ({ ...p, freq: noteFrequency(p.note, p.octave) }));
