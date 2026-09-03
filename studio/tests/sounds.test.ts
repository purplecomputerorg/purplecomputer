import { describe, expect, it } from "vitest";
import exported from "../src/purple/export.json";
import { GRID_ROWS, LETTER_KEYS, SAMPLE_PITCHES, noteFrequency, pitchFilename, pitchFor, voiceClipFilename } from "../src/purple/sounds";

describe("sound naming matches purple_tui", () => {
  it("voice clip filename matches tts.voice_clip_filename on the exported examples", () => {
    for (const [text, name] of Object.entries(exported.voice.clip_filenames)) expect(voiceClipFilename(text)).toBe(name);
  });

  it("pitch filenames round-trip the exported pitch set", () => {
    expect(SAMPLE_PITCHES.length).toBe(exported.music.pitches.length);
    for (const p of SAMPLE_PITCHES) expect(pitchFilename(p.note, p.octave)).toBe(p.file);
  });

  it("pitch_for agrees with the exported grid at the default root", () => {
    GRID_ROWS.forEach((row, r) => row.forEach((_, c) => {
      const { note, octave } = pitchFor(r, c);
      expect(`${note}${octave}`, `row ${r} col ${c}`).toBe(exported.music.grid_pitches[`${r},${c}` as keyof typeof exported.music.grid_pitches]);
    }));
  });

  it("frequencies and keys", () => {
    expect(noteFrequency("A", 4)).toBeCloseTo(440);
    expect(LETTER_KEYS.length).toBe(36);
  });
});
