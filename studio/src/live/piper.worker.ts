// Purple's voice in a worker, the way piper-tts 1.4.1 makes it: espeak-ng phonemes, phoneme ids, then
// the same ONNX model with Purple's settings (purple_tui/tts.py). Answers one prepared text with 16-bit
// samples, as Piper's audio_int16_bytes, before Purple's own trim and leveling.
import type * as Ort from "onnxruntime-web";
import { cached, espeak, onnx, sentences } from "./espeak";
import { MODEL, SPEAKER, SCALES, WORD_GAP } from "./piperfiles";

interface Config { espeak: { voice: string }; audio: { sample_rate: number }; phoneme_id_map: Record<string, number[]> }

let ort: typeof Ort;

async function start(base: string) {
  const url = (f: string) => new URL(`voice/${f}`, base).href;
  ort = await onnx(base);
  const config: Config = await (await fetch(url(`${MODEL}.json`))).json();
  const [model, e] = await Promise.all([
    cached(url(MODEL), (loaded, total) => self.postMessage({ progress: [loaded, total] })),
    espeak(base, config.espeak.voice),
  ]);
  const session = await ort.InferenceSession.create(model, { executionProviders: ["wasm"] });
  return { config, session, espeak: e };
}

type Voice = Awaited<ReturnType<typeof start>>;

// Each pause between words repeated, as tts._synthesize_with_word_gaps.
const withWordGaps = (phonemes: string[]) => phonemes.flatMap((p) => (p === " " ? Array<string>(WORD_GAP).fill(p) : [p]));

const ids = ({ config: { phoneme_id_map: m } }: Voice, phonemes: string[]) =>
  [...m["^"], ...m["_"], ...phonemes.flatMap((p) => (m[p] ? [...m[p], ...m["_"]] : [])), ...m["$"]];
const int64 = (xs: number[], dims?: number[]) => new ort.Tensor("int64", BigInt64Array.from(xs, BigInt), dims);

// Each sentence normalized to full scale, then to 16 bits, as Piper's synthesize().
async function speak(voice: Voice, text: string, hushed: () => boolean): Promise<Int16Array> {
  const parts: Int16Array[] = [];
  for (const phonemes of sentences(voice.espeak, text)) {
    if (hushed()) break;
    const input = ids(voice, withWordGaps(phonemes));
    const { output } = await voice.session.run({
      input: int64(input, [1, input.length]),
      input_lengths: int64([input.length]),
      scales: new ort.Tensor("float32", Float32Array.from(SCALES)),
      sid: int64([SPEAKER]),
    });
    const audio = output.data as Float32Array;
    const peak = audio.reduce((m, x) => Math.max(m, Math.abs(x)), 0);
    // In float32 like numpy, so the samples match Piper's to the bit.
    parts.push(Int16Array.from(audio, (x) => (peak < 1e-8 ? 0 : Math.fround(Math.max(-1, Math.min(1, Math.fround(x / peak))) * 32767))));
  }
  const all = new Int16Array(parts.reduce((n, p) => n + p.length, 0));
  parts.reduce((at, p) => (all.set(p, at), at + p.length), 0);
  return all;
}

let voice: Promise<Voice> | null = null;
// Lines up to this id were hushed before they were spoken.
let dropped = 0;
self.onmessage = async ({ data }: MessageEvent<{ base: string } | { drop: number } | { id: number; text: string }>) => {
  if ("base" in data) {
    voice = start(data.base);
    return voice.then(() => self.postMessage({ ready: true }), (e) => self.postMessage({ failed: String(e) }));
  }
  if ("drop" in data) return void (dropped = data.drop);
  try {
    const v = await voice!;
    const pcm = await speak(v, data.text, () => data.id <= dropped);
    (self as unknown as Worker).postMessage({ id: data.id, pcm, rate: v.config.audio.sample_rate }, [pcm.buffer]);
  } catch (e) {
    self.postMessage({ id: data.id, error: String(e) });
  }
};
