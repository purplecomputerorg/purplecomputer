// Port of purple_tui/synth.py and the instrument generators in scripts/generate_sounds.py.
// Every slider maps to a number that already exists in that Python; the defaults are its defaults.
// The only knowing difference: noise uses a small seeded PRNG instead of Python's Mersenne Twister.

export const SYNTH_RATE = 44100;
export type BaseName = "marimba" | "ukulele" | "accordion" | "glockenspiel";
export type Params = Record<string, number>;

export interface ParamSpec {
  key: string;
  label: string;
  group: string;
  min: number;
  max: number;
  step: number;
  default: number;
  unit?: string;
}

export interface Base { label: string; blurb: string; params: ParamSpec[] }

const p = (key: string, label: string, group: string, min: number, max: number, step: number, def: number, unit?: string): ParamSpec =>
  ({ key, label, group, min, max, step, default: def, unit });

export const BASES: Record<BaseName, Base> = {
  marimba: {
    label: "Marimba",
    blurb: "A wooden bar over a tube. The 4x partial is the woody knock.",
    params: [
      p("duration", "Length", "Shape", 0.2, 1.5, 0.05, 0.55, "s"),
      p("attack", "Attack", "Shape", 1, 40, 1, 8, "ms"),
      p("barDecay", "Bar decay", "Shape", 1, 15, 0.5, 5.5),
      p("wood", "Woodiness", "Tone", 0, 1.2, 0.05, 0.5),
      p("sparkle", "Sparkle", "Tone", 0, 0.3, 0.01, 0.08),
      p("tube", "Tube body", "Tone", 0, 0.6, 0.05, 0.25),
      p("tubeDecay", "Tube decay", "Tone", 2, 12, 0.5, 6),
      p("mallet", "Mallet knock", "Tone", 0, 0.6, 0.05, 0.25),
    ],
  },
  ukulele: {
    label: "Ukulele",
    blurb: "A plucked nylon string, modeled as a loop of sound that slowly loses its highs.",
    params: [
      p("duration", "Length", "Shape", 0.3, 2, 0.05, 0.9, "s"),
      p("damping", "Sustain", "Shape", 0.98, 0.999, 0.0005, 0.996),
      p("warmth", "Warmth", "Tone", 0.1, 1, 0.05, 0.4),
      p("softness", "Soft pluck", "Tone", 0, 6, 1, 3),
      p("pluckPos", "Pluck spot", "Tone", 0.1, 0.5, 0.05, 0.25),
      p("bodyFreq", "Body size", "Body", 150, 800, 10, 420, "Hz"),
      p("bodyQ", "Body ring", "Body", 1, 10, 0.5, 3),
      p("bodyMix", "Body amount", "Body", 0, 1, 0.05, 0.35),
    ],
  },
  accordion: {
    label: "Accordion",
    blurb: "Two reeds a few cents apart, breathing with a slow tremolo.",
    params: [
      p("duration", "Length", "Shape", 0.3, 2, 0.05, 0.55, "s"),
      p("attack", "Attack", "Shape", 10, 300, 5, 80, "ms"),
      p("detune", "Reed detune", "Tone", 0, 20, 0.5, 2, "cents"),
      p("harmonics", "Reediness", "Tone", 1, 20, 1, 10),
      p("rolloff", "Brightness", "Tone", 300, 4000, 50, 1000, "Hz"),
      p("tremRate", "Breath speed", "Breath", 2, 10, 0.5, 5, "Hz"),
      p("tremDepth", "Breath depth", "Breath", 0, 0.2, 0.005, 0.015),
    ],
  },
  glockenspiel: {
    label: "Glockenspiel",
    blurb: "A small metal bar. The bell lives in the 2.8x partial, louder than the fundamental.",
    params: [
      p("duration", "Length", "Shape", 0.3, 3, 0.05, 1.5, "s"),
      p("ring", "Ring", "Shape", 0.3, 3, 0.05, 1),
      p("fundamental", "Fundamental", "Tone", 0, 1, 0.05, 0.6),
      p("bell", "Bell", "Tone", 0, 1.2, 0.05, 0.9),
      p("shimmer", "Shimmer", "Tone", 0, 2, 0.05, 1),
      p("ping", "Mallet ping", "Tone", 0, 0.6, 0.05, 0.35),
    ],
  },
};

export const BASE_NAMES = Object.keys(BASES) as BaseName[];

export const defaults = (base: BaseName): Params =>
  Object.fromEntries(BASES[base].params.map((s) => [s.key, s.default]));

// Mulberry32: deterministic per note like random.seed(int(freq * 1000)) in the Python.
function rng(seed: number) {
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

function finalize(samples: Float32Array, peakLevel: number, freq: number): Float32Array {
  const level = loudnessCompensatedPeak(freq, peakLevel);
  let peak = 0;
  for (const s of samples) peak = Math.max(peak, Math.abs(s));
  const scale = (peak || 1) ? level / (peak || 1) : 0;
  return samples.map((s) => Math.trunc((s * scale) * 32767) / 32767);
}

function cosineFade(samples: Float32Array, duration: number, fadeOut: number) {
  const start = duration - fadeOut;
  for (let i = 0; i < samples.length; i++) {
    const t = i / SYNTH_RATE;
    if (t > start) samples[i] *= 0.5 * (1 + Math.cos((Math.PI * (t - start)) / fadeOut));
  }
}

function marimba(q: Params, freq: number): Float32Array {
  const n = Math.floor(SYNTH_RATE * q.duration);
  const out = new Float32Array(n);
  const boost = lowFreqPartialBoost(freq);
  const partials: [number, number, number][] = [
    [1, 1, q.barDecay],
    [4, q.wood * boost, q.barDecay * 2],
    [9.2, q.sparkle * boost, q.barDecay * 3.27],
  ];
  const noise = rng(freq * 1000);
  const attackS = q.attack / 1000;
  for (let i = 0; i < n; i++) {
    const t = i / SYNTH_RATE;
    let s = 0;
    for (const [ratio, amp, decay] of partials) {
      const f = freq * ratio;
      if (f < SYNTH_RATE / 2) s += amp * Math.exp(-t * decay) * Math.sin(2 * Math.PI * f * t);
    }
    const tubeEnv = (1 - Math.exp(-t * 30)) * Math.exp(-t * q.tubeDecay);
    s += q.tube * tubeEnv * Math.sin(2 * Math.PI * freq * t);
    if (t < 0.01) s += noise() * q.mallet * Math.exp(-t * 400);
    out[i] = s * Math.min(1, t / attackS);
  }
  cosineFade(out, q.duration, Math.min(0.18, q.duration / 3));
  return finalize(out, 0.7, freq);
}

function accordion(q: Params, freq: number): Float32Array {
  const n = Math.floor(SYNTH_RATE * q.duration);
  const out = new Float32Array(n);
  const nyquist = SYNTH_RATE / 2;
  const freqs = [freq, freq * 2 ** (q.detune / 1200)];
  const maxN = Math.min(q.harmonics, Math.floor(nyquist / Math.max(freq, 1)));
  const attackS = q.attack / 1000;
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
    out[i] = s * Math.min(1, t / attackS) * (1 + q.tremDepth * Math.sin(2 * Math.PI * q.tremRate * t));
  }
  cosineFade(out, q.duration, Math.min(0.12, q.duration / 3));
  return finalize(out, 0.4, freq);
}

function ukulele(q: Params, freq: number): Float32Array {
  const n = Math.floor(SYNTH_RATE * q.duration);
  const period = SYNTH_RATE / freq;
  const N = Math.floor(period);
  const frac = period - N;
  const ap = (1 - frac) / (1 + frac);
  const noise = rng(freq * 1000);
  const line = Float64Array.from({ length: N }, () => noise());
  for (let pass = 0; pass < q.softness; pass++) for (let j = 1; j < N; j++) line[j] = 0.5 * line[j] + 0.5 * line[j - 1];
  const pluck = Math.floor(N * q.pluckPos);
  if (pluck > 0) for (let j = N - 1; j >= pluck; j--) line[j] -= 0.5 * line[j - pluck];

  const out = new Float32Array(n);
  let pos = 0, apIn = 0, apOut = 0, prev = 0;
  for (let i = 0; i < n; i++) {
    const cur = line[pos];
    const filtered = q.warmth * cur + (1 - q.warmth) * prev;
    prev = filtered;
    const a = ap * filtered + apIn - ap * apOut;
    apIn = filtered;
    apOut = a;
    line[pos] = a * q.damping;
    pos = (pos + 1) % N;
    out[i] = cur;
  }
  const w0 = (2 * Math.PI * q.bodyFreq) / SYNTH_RATE;
  const alpha = Math.sin(w0) / (2 * q.bodyQ);
  const a0 = 1 + alpha;
  const b0 = alpha / a0, b2 = -alpha / a0, a1 = (-2 * Math.cos(w0)) / a0, a2 = (1 - alpha) / a0;
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  for (let i = 0; i < n; i++) {
    const x0 = out[i];
    const y0 = b0 * x0 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1; x1 = x0; y2 = y1; y1 = y0;
    out[i] = x0 + q.bodyMix * y0;
  }
  cosineFade(out, q.duration, Math.min(0.15, q.duration / 3));
  return finalize(out, 0.7, freq);
}

function glockenspiel(q: Params, freq: number): Float32Array {
  const n = Math.floor(SYNTH_RATE * q.duration);
  const out = new Float32Array(n);
  const boost = lowFreqPartialBoost(freq);
  const partials: [number, number, number][] = [
    [1, q.fundamental, 1.4 / q.ring],
    [2.8, q.bell * boost, 2.8 / q.ring],
    [5.42, 0.45 * q.shimmer * boost, 4.2 / q.ring],
    [8.6, 0.22 * q.shimmer * boost, 6.5 / q.ring],
    [11.7, 0.12 * q.shimmer * boost, 9 / q.ring],
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
