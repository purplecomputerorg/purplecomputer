import { describe, expect, it } from "vitest";
import golden from "./golden.json";
import exported from "../sdk/src/purple/export.json";
import { BASES, BASE_NAMES, SYNTH_RATE, defaults, renderNote, type BaseName, type Params } from "../sdk/src/purple/synth";

// golden.json is rendered by purple_tui/synth.py (scripts/export_studio.py). One LSB of slack covers
// the last-bit differences between libm and V8 before int() truncation; nothing else may differ.
const toInt16 = (out: Float32Array) => Array.from(out, (s) => Math.round(s * 32767));

describe("synth port against Python renders", () => {
  it.each(golden.map((g) => [`${g.base} ${g.freq} Hz ${JSON.stringify(g.params)}`, g] as const))("%s", (_, g) => {
    const out = toInt16(renderNote(g.base as BaseName, g.params as Params, g.freq));
    expect(out.length).toBe(g.length);
    let worst = 0;
    g.head.forEach((v, i) => (worst = Math.max(worst, Math.abs(out[i] - v))));
    g.strided.forEach((v, i) => (worst = Math.max(worst, Math.abs(out[i * g.stride] - v))));
    expect(worst).toBeLessThanOrEqual(1);
  });

  it("slider keys are exactly the Python parameter names", () => {
    for (const base of BASE_NAMES) {
      expect(BASES[base].params.map((s) => s.key).sort()).toEqual(Object.keys(exported.synth.defaults[base]).sort());
      for (const s of BASES[base].params) {
        const d = defaults(base)[s.key];
        const pos = s.scale?.toSlider(d) ?? d;
        expect(pos, `${base}.${s.key}`).toBeGreaterThanOrEqual(s.min);
        expect(pos, `${base}.${s.key}`).toBeLessThanOrEqual(s.max);
        if (s.scale) expect(s.scale.fromSlider(pos)).toBeCloseTo(d, 6);
      }
    }
  });

  it("Sustain moves in multiples of the default ring time", () => {
    const sustain = BASES.ukulele.params.find((s) => s.key === "damping")!.scale!;
    expect(sustain.fromSlider(0.2)).toBeCloseTo(0.98, 6);
    expect(sustain.fromSlider(4)).toBeCloseTo(0.999, 6);
  });

  it("is deterministic and sized by duration", () => {
    const a = renderNote("ukulele", defaults("ukulele"), 220);
    expect(a).toEqual(renderNote("ukulele", defaults("ukulele"), 220));
    expect(a.length).toBe(Math.trunc(SYNTH_RATE * defaults("ukulele").duration));
  });
});
