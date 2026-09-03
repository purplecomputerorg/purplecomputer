import { describe, expect, it } from "vitest";
import { LETTER_KEYS, SAMPLE_PITCHES, noteFrequency, noteFromFrequency, pitchFilename, voiceClipFilename } from "../src/purple/sounds";

describe("sound naming matches purple_tui", () => {
  it("voice clip filename follows tts.py", () => {
    expect(voiceClipFilename("  Hello There ")).toBe("hello_there.wav");
    expect(voiceClipFilename("It's Purple Computer")).toBe("it's_purple_computer.wav");
  });

  it("pitch filename follows music_constants.pitch_filename", () => {
    expect(pitchFilename("C#", 4)).toBe("cs4");
    expect(pitchFilename("A", 1)).toBe("a1");
  });

  it("sample set is the 67 core pitches with round-trip names", () => {
    expect(SAMPLE_PITCHES.length).toBe(67);
    for (const p of SAMPLE_PITCHES) expect(pitchFilename(p.note, p.octave)).toBe(p.file);
    expect(SAMPLE_PITCHES.some((p) => p.file === "gs4")).toBe(false);
  });

  it("frequencies round-trip", () => {
    expect(noteFrequency("A", 4)).toBeCloseTo(440);
    expect(noteFromFrequency(261.63)).toMatchObject({ note: "C", octave: 4 });
    expect(LETTER_KEYS.length).toBe(36);
  });
});
