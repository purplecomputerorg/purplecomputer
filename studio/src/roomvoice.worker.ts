// The room voice in a worker, for roomvoice.ts: Kokoro (studio_bundle.py fetches it), on the same espeak-ng
// phonemes as Purple's Piper. Answers one line with float samples at the model's rate.
import type * as Ort from "onnxruntime-web";
import { cached, espeak, onnx, sentences } from "./live/espeak";

export interface Kokoro { model: string; voice: string; speed: number; rate: number; vocab: Record<string, number> }
// The model's longest input, its start and end pads aside.
const MAX_TOKENS = 510;
const STYLE = 256;

let ort: typeof Ort;

async function start(base: string) {
  const url = (f: string) => new URL(`voice/kokoro/${f}`, base).href;
  ort = await onnx(base);
  const spec: Kokoro = await (await fetch(url("kokoro.json"))).json();
  const [model, styles, e] = await Promise.all([
    cached(url(spec.model), (loaded, total) => self.postMessage({ progress: [loaded, total] })),
    fetch(url(`${spec.voice}.bin`)).then(async (r) => new Float32Array(await r.arrayBuffer())),
    espeak(base, "en-us"),
  ]);
  const session = await ort.InferenceSession.create(model, { executionProviders: ["wasm"] });
  return { spec, styles, session, espeak: e };
}

type Voice = Awaited<ReturnType<typeof start>>;

// Whole sentences per run, as many as fit, so a line keeps its flow.
function chunks({ spec, espeak }: Voice, text: string): number[][] {
  const out: number[][] = [[]];
  for (const ids of sentences(espeak, text).map((s) => s.flatMap((p) => spec.vocab[p] ?? []))) {
    if (out[out.length - 1].length + ids.length > MAX_TOKENS) out.push([]);
    out[out.length - 1].push(...ids.slice(0, MAX_TOKENS));
  }
  return out.filter((c) => c.length);
}

async function speak(voice: Voice, text: string): Promise<Float32Array> {
  const parts: Float32Array[] = [];
  for (const ids of chunks(voice, text)) {
    const tokens = [0, ...ids, 0];
    const { audio } = await voice.session.run({
      tokens: new ort.Tensor("int64", BigInt64Array.from(tokens, BigInt), [1, tokens.length]),
      style: new ort.Tensor("float32", voice.styles.slice(ids.length * STYLE, (ids.length + 1) * STYLE), [1, STYLE]),
      speed: new ort.Tensor("float32", [voice.spec.speed], [1]),
    });
    parts.push(audio.data as Float32Array);
  }
  const all = new Float32Array(parts.reduce((n, p) => n + p.length, 0));
  parts.reduce((at, p) => (all.set(p, at), at + p.length), 0);
  return all;
}

let voice: Promise<Voice> | null = null;
self.onmessage = async ({ data }: MessageEvent<{ base: string } | { id: number; text: string }>) => {
  if ("base" in data) {
    voice = start(data.base);
    return voice.then((v) => self.postMessage({ ready: true, rate: v.spec.rate }), (e) => self.postMessage({ failed: String(e) }));
  }
  try {
    const samples = await speak(await voice!, data.text);
    (self as unknown as Worker).postMessage({ id: data.id, samples }, [samples.buffer]);
  } catch (e) {
    self.postMessage({ id: data.id, error: String(e) });
  }
};
