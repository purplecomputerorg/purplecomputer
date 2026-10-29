import { describe, expect, it } from "vitest";
import { encodeWav, stretch, tidy } from "../src/audio";
import { CLIP_SAMPLE_RATE } from "../sdk/src/purple/sounds";
import { decodeWav } from "../sdk/src/wav";

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

  it("reads back what it wrote, clipping anything past full scale", () => {
    const samples = Float32Array.from([0, 0.5, -0.25, 1.5, -2]);
    const back = decodeWav(encodeWav({ samples, rate: 16000 }));
    expect(back.rate).toBe(16000);
    [0, 0.5, -0.25, 1, -1].forEach((s, i) => expect(back.samples[i]).toBeCloseTo(s, 4));
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

describe("stretch", () => {
  it("makes a clip longer at the same pitch", () => {
    const rate = 24000;
    const out = stretch({ samples: sine(440, 1, rate), rate }, 0.75).samples;
    expect(out.length).toBe(Math.round(rate / 0.75));
    const middle = out.subarray(rate * 0.1, rate * 1.2);
    const crossings = middle.filter((s, i) => i > 0 && Math.sign(s) !== Math.sign(middle[i - 1])).length;
    expect(crossings / (middle.length / rate) / 2).toBeCloseTo(440, -1);
  });
});
