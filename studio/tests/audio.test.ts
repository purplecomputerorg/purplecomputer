import { describe, expect, it } from "vitest";
import { encodeWav, tidy } from "../src/audio";
import { CLIP_SAMPLE_RATE } from "../src/purple/sounds";

const sine = (freq: number, seconds: number, rate = CLIP_SAMPLE_RATE) =>
  Float32Array.from({ length: Math.floor(rate * seconds) }, (_, i) => 0.5 * Math.sin((2 * Math.PI * freq * i) / rate));

describe("wav", () => {
  it("writes 16-bit mono PCM at the core clip rate", () => {
    const wav = encodeWav({ samples: sine(440, 0.01), rate: CLIP_SAMPLE_RATE });
    const v = new DataView(wav.buffer);
    expect(String.fromCharCode(...wav.subarray(0, 4))).toBe("RIFF");
    expect(String.fromCharCode(...wav.subarray(8, 12))).toBe("WAVE");
    expect(v.getUint16(20, true)).toBe(1);
    expect(v.getUint16(22, true)).toBe(1);
    expect(v.getUint32(24, true)).toBe(22050);
    expect(v.getUint16(34, true)).toBe(16);
    expect(v.getUint32(40, true)).toBe(wav.length - 44);
  });
});

describe("tidy", () => {
  it("trims leading and trailing silence and keeps a little air", () => {
    const rate = CLIP_SAMPLE_RATE;
    const samples = new Float32Array(rate);
    samples.set(sine(440, 0.2), Math.floor(rate * 0.4));
    const out = tidy({ samples, rate });
    expect(out.samples.length).toBeGreaterThan(rate * 0.2);
    expect(out.samples.length).toBeLessThan(rate * 0.25);
  });

  it("returns an empty clip for silence", () => {
    expect(tidy({ samples: new Float32Array(1000), rate: CLIP_SAMPLE_RATE }).samples.length).toBe(0);
  });
});
