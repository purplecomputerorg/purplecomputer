import { describe, expect, it } from "vitest";
import { BASES, BASE_NAMES, SYNTH_RATE, defaults, renderNote } from "../src/purple/synth";

describe("synth port", () => {
  it.each(BASE_NAMES)("%s renders a normalized note of the right length", (base) => {
    const q = defaults(base);
    const out = renderNote(base, q, 880);
    expect(out.length).toBe(Math.floor(SYNTH_RATE * q.duration));
    let peak = 0;
    for (const s of out) peak = Math.max(peak, Math.abs(s));
    // finalize_samples: peak_level 0.7 (0.4 for the accordion); above 500 Hz no loudness boost applies.
    const expected = base === "accordion" ? 0.4 : 0.7;
    expect(Math.abs(peak - expected)).toBeLessThan(0.01);
    expect(out[out.length - 1]).toBeCloseTo(0, 2);
  });

  it("low notes normalize hotter, like loudness_compensated_peak", () => {
    const out = renderNote("marimba", defaults("marimba"), 100);
    let peak = 0;
    for (const s of out) peak = Math.max(peak, Math.abs(s));
    expect(peak).toBeGreaterThan(0.85);
  });

  it("is deterministic per note", () => {
    const a = renderNote("ukulele", defaults("ukulele"), 220);
    const b = renderNote("ukulele", defaults("ukulele"), 220);
    expect(a).toEqual(b);
  });

  it("every slider default sits inside its range", () => {
    for (const base of BASE_NAMES) for (const s of BASES[base].params) {
      expect(s.default).toBeGreaterThanOrEqual(s.min);
      expect(s.default).toBeLessThanOrEqual(s.max);
    }
  });
});
