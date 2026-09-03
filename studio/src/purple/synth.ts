// Port of purple_tui/synth.py. Parameter names and defaults come from export.json; the arithmetic
// is kept in the same order as the Python so tests/synth.test.ts can hold it to within one sample
// of the golden renders in tests/golden.json.
import exported from "./export.json";

export const SYNTH_RATE: number = exported.synth.sample_rate;
export type BaseName = "marimba" | "ukulele" | "accordion" | "glockenspiel";
export type Params = Record<string, number>;

export interface ParamSpec { key: string; label: string; group: string; min: number; max: number; step: number; unit?: string }
export interface Base { label: string; blurb: string; params: ParamSpec[] }

const p = (key: string, label: string, group: string, min: number, max: number, step: number, unit?: string): ParamSpec =>
  ({ key, label, group, min, max, step, unit });

// Slider ranges and labels are Studio's; the keys must match synth.DEFAULTS in Python (tested).
export const BASES: Record<BaseName, Base> = {
  marimba: {
    label: "Marimba",
    blurb: "A wooden bar over a tube. The 4x partial is the woody knock.",
    params: [
      p("duration", "Length", "Shape", 0.2, 1.5, 0.05, "s"),
      p("attack_ms", "Attack", "Shape", 1, 40, 1, "ms"),
      p("bar_decay", "Bar decay", "Shape", 1, 15, 0.5),
      p("wood", "Woodiness", "Tone", 0, 1.2, 0.05),
      p("sparkle", "Sparkle", "Tone", 0, 0.3, 0.01),
      p("tube", "Tube body", "Tone", 0, 0.6, 0.05),
      p("tube_decay", "Tube decay", "Tone", 2, 12, 0.5),
      p("mallet", "Mallet knock", "Tone", 0, 0.6, 0.05),
    ],
  },
  ukulele: {
    label: "Ukulele",
    blurb: "A plucked nylon string, modeled as a loop of sound that slowly loses its highs.",
    params: [
      p("duration", "Length", "Shape", 0.3, 2, 0.05, "s"),
      p("damping", "Sustain", "Shape", 0.98, 0.999, 0.0005),
      p("warmth", "Warmth", "Tone", 0.1, 1, 0.05),
      p("softness", "Soft pluck", "Tone", 0, 6, 1),
      p("pluck_pos", "Pluck spot", "Tone", 0.1, 0.5, 0.05),
      p("body_freq", "Body size", "Body", 150, 800, 10, "Hz"),
      p("body_q", "Body ring", "Body", 1, 10, 0.5),
      p("body_mix", "Body amount", "Body", 0, 1, 0.05),
    ],
  },
  accordion: {
    label: "Accordion",
    blurb: "Two reeds a few cents apart, breathing with a slow tremolo.",
    params: [
      p("duration", "Length", "Shape", 0.3, 2, 0.05, "s"),
      p("attack_ms", "Attack", "Shape", 10, 300, 5, "ms"),
      p("detune", "Reed detune", "Tone", 0, 20, 0.5, "cents"),
      p("harmonics", "Reediness", "Tone", 1, 20, 1),
      p("rolloff", "Brightness", "Tone", 300, 4000, 50, "Hz"),
      p("trem_rate", "Breath speed", "Breath", 2, 10, 0.5, "Hz"),
      p("trem_depth", "Breath depth", "Breath", 0, 0.2, 0.005),
    ],
  },
  glockenspiel: {
    label: "Glockenspiel",
    blurb: "A small metal bar. The bell lives in the 2.8x partial, louder than the fundamental.",
    params: [
      p("duration", "Length", "Shape", 0.3, 3, 0.05, "s"),
      p("ring", "Ring", "Shape", 0.3, 3, 0.05),
      p("fundamental", "Fundamental", "Tone", 0, 1, 0.05),
      p("bell", "Bell", "Tone", 0, 1.2, 0.05),
      p("shimmer", "Shimmer", "Tone", 0, 2, 0.05),
      p("ping", "Mallet ping", "Tone", 0, 0.6, 0.05),
    ],
  },
};

export const BASE_NAMES = Object.keys(BASES) as BaseName[];
export const defaults = (base: BaseName): Params => ({ ...(exported.synth.defaults as Record<BaseName, Params>)[base] });

// synth.noise: mulberry32, same stream as the Python for the same seed.
function noise(seed: number) {
  let a = Math.trunc(seed) >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return (((t ^ (t >>> 14)) >>> 0) / 4294967296) * 2 - 1;
  };
}

function loudnessCompensatedPeak(freq: number, base: number): number {
  if (freq >= 500) return base;
  return Math.min(0.95, base * (1 + 0.4 * (1 - Math.max(freq, 80) / 500)));
}

const lowFreqPartialBoost = (freq: number) => (freq >= 250 ? 1 : Math.min(2.5, 250 / Math.max(freq, 80)));

// finalize_samples, returning the int16 values scaled back to [-1, 1] for playback.
function finalize(samples: Float64Array, peakLevel: number, freq: number): Float32Array {
  const level = loudnessCompensatedPeak(freq, peakLevel);
  let peak = 0;
  for (const s of samples) peak = Math.max(peak, Math.abs(s));
  peak ||= 1;
  return Float32Array.from(samples, (s) => Math.trunc(((s / peak) * level) * 32767) / 32767);
}

function cosineFade(samples: Float64Array, duration: number, fade: number) {
  const start = duration - fade;
  for (let i = 0; i < samples.length; i++) {
    const t = i / SYNTH_RATE;
    if (t > start) samples[i] *= 0.5 * (1 + Math.cos((Math.PI * (t - start)) / fade));
  }
}

function marimba(q: Params, freq: number): Float32Array {
  const n = Math.trunc(SYNTH_RATE * q.duration);
  const out = new Float64Array(n);
  const boost = lowFreqPartialBoost(freq);
  const partials: [number, number, number][] = [
    [1, 1, q.bar_decay],
    [4, q.wood * boost, q.bar_decay * 2],
    [9.2, q.sparkle * boost, (q.bar_decay * 18) / 5.5],
  ];
  const attackS = q.attack_ms / 1000;
  const mallet = noise(freq * 1000);
  for (let i = 0; i < n; i++) {
    const t = i / SYNTH_RATE;
    let s = 0;
    for (const [ratio, amp, decay] of partials) {
      const f = freq * ratio;
      if (f < SYNTH_RATE / 2) s += amp * Math.exp(-t * decay) * Math.sin(2 * Math.PI * f * t);
    }
    const tubeEnv = (1 - Math.exp(-t * 30)) * Math.exp(-t * q.tube_decay);
    s += q.tube * tubeEnv * Math.sin(2 * Math.PI * freq * t);
    if (t < 0.01) s += mallet() * q.mallet * Math.exp(-t * 400);
    out[i] = s * Math.min(1, t / attackS);
  }
  cosineFade(out, q.duration, Math.min(0.18, q.duration / 3));
  return finalize(out, 0.7, freq);
}

function accordion(q: Params, freq: number): Float32Array {
  const n = Math.trunc(SYNTH_RATE * q.duration);
  const out = new Float64Array(n);
  const nyquist = SYNTH_RATE / 2;
  const freqs = [freq, freq * 2 ** (q.detune / 1200)];
  const maxN = Math.min(Math.trunc(q.harmonics), Math.trunc(nyquist / Math.max(freq, 1)));
  const attackS = q.attack_ms / 1000;
  for (let i = 0; i < n; i++) {
    const t = i / SYNTH_RATE;
    let s = 0;
    for (const f of freqs) {
      for (let k = 1; k <= maxN; k++) {
        const fk = f * k;
        if (fk >= nyquist) break;
        const amp = (1 / k) * (fk > q.rolloff ? q.rolloff / fk : 1);
        s += amp * Math.sin(2 * Math.PI * fk * t);
      }
    }
    const trem = 1 + q.trem_depth * Math.sin(2 * Math.PI * q.trem_rate * t);
    out[i] = s * Math.min(1, t / attackS) * trem;
  }
  cosineFade(out, q.duration, Math.min(0.12, q.duration / 3));
  return finalize(out, 0.4, freq);
}

function ukulele(q: Params, freq: number): Float32Array {
  const n = Math.trunc(SYNTH_RATE * q.duration);
  const period = SYNTH_RATE / freq;
  const N = Math.trunc(period);
  const frac = period - N;
  const allpass = (1 - frac) / (1 + frac);
  const pluckNoise = noise(freq * 1000);
  const line = Float64Array.from({ length: N }, () => pluckNoise());
  for (let pass = 0; pass < Math.trunc(q.softness); pass++) for (let j = 1; j < N; j++) line[j] = 0.5 * line[j] + 0.5 * line[j - 1];
  const pluck = Math.trunc(N * q.pluck_pos);
  if (pluck > 0) for (let j = pluck; j < N; j++) line[j] = line[j] - 0.5 * line[j - pluck];

  const out = new Float64Array(n);
  let pos = 0, apIn = 0, apOut = 0, prev = 0;
  const warmth = q.warmth;
  for (let i = 0; i < n; i++) {
    const cur = line[pos];
    const filtered = warmth * cur + (1 - warmth) * prev;
    prev = filtered;
    const a = allpass * filtered + apIn - allpass * apOut;
    apIn = filtered;
    apOut = a;
    line[pos] = a * q.damping;
    pos = (pos + 1) % N;
    out[i] = cur;
  }
  const w0 = (2 * Math.PI * q.body_freq) / SYNTH_RATE;
  const alpha = Math.sin(w0) / (2 * q.body_q);
  const a0 = 1 + alpha;
  const b0 = alpha / a0, b2 = -alpha / a0, a1 = (-2 * Math.cos(w0)) / a0, a2 = (1 - alpha) / a0;
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  for (let i = 0; i < n; i++) {
    const x0 = out[i];
    const y0 = b0 * x0 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1; x1 = x0; y2 = y1; y1 = y0;
    out[i] = x0 + q.body_mix * y0;
  }
  cosineFade(out, q.duration, Math.min(0.15, q.duration / 3));
  return finalize(out, 0.7, freq);
}

function glockenspiel(q: Params, freq: number): Float32Array {
  const n = Math.trunc(SYNTH_RATE * q.duration);
  const out = new Float64Array(n);
  const boost = lowFreqPartialBoost(freq);
  const ring = q.ring;
  const partials: [number, number, number][] = [
    [1, q.fundamental, 1.4 / ring],
    [2.8, q.bell * boost, 2.8 / ring],
    [5.42, 0.45 * q.shimmer * boost, 4.2 / ring],
    [8.6, 0.22 * q.shimmer * boost, 6.5 / ring],
    [11.7, 0.12 * q.shimmer * boost, 9 / ring],
  ];
  for (let i = 0; i < n; i++) {
    const t = i / SYNTH_RATE;
    let s = 0;
    for (const [ratio, amp, decay] of partials) {
      const f = freq * ratio;
      if (f < SYNTH_RATE / 2) s += amp * Math.exp(-t * decay) * Math.sin(2 * Math.PI * f * t);
    }
    if (t < 0.005) s += q.ping * Math.exp(-t / 0.00125) * Math.sin(2 * Math.PI * 4000 * t);
    out[i] = s * Math.min(1, t / 0.002);
  }
  cosineFade(out, q.duration, Math.min(0.7, q.duration / 2));
  return finalize(out, 0.7, freq);
}

const GENERATORS: Record<BaseName, (q: Params, freq: number) => Float32Array> = { marimba, ukulele, accordion, glockenspiel };

export function renderNote(base: BaseName, params: Params, freq: number): Float32Array {
  return GENERATORS[base]({ ...defaults(base), ...params }, freq);
}
