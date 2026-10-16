// Purple's voice in a worker, the way piper-tts 1.4.1 makes it: espeak-ng phonemes, phoneme ids, then
// the same ONNX model with Purple's settings (purple_tui/tts.py). Answers one prepared text with 16-bit
// samples, as Piper's audio_int16_bytes, before Purple's own trim and leveling.
import type * as Ort from "onnxruntime-web";
// @ts-expect-error: emscripten output, no types
import createEspeak from "../../vendor/espeak-ng/espeak.mjs";
import { CACHE, ESPEAK_DATA, MODEL, SPEAKER, SCALES } from "./piperfiles";

interface Espeak { FS: { mkdirTree(p: string): void; writeFile(p: string, d: Uint8Array): void }; ccall(f: string, r: string, t: string[], a: unknown[]): number | string }
interface Config { espeak: { voice: string }; audio: { sample_rate: number }; phoneme_id_map: Record<string, number[]> }

// espeak-ng's clause terminator flags, as piper's espeakbridge.c reads them.
const TERMINATORS: Record<number, string> = { [40 | 0x80000]: ".", [20 | 0x1000 | 0x40000]: ",", [40 | 0x2000 | 0x80000]: "?",
  [45 | 0x3000 | 0x80000]: "!", [30 | 0x40000]: ":", [30 | 0x1000 | 0x40000]: ";" };
const SENTENCE_END = 0x80000;

// Read in chunks so Studio can say how long the voice has left to load.
async function download(url: string): Promise<Uint8Array<ArrayBuffer>> {
  const res = await fetch(url);
  if (!res.ok || !res.body) throw new Error(`${url}: ${res.status}`);
  const total = +(res.headers.get("Content-Length") ?? 0);
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  let told = 0;
  for (const reader = res.body.getReader(); ;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.length;
    if (performance.now() - told > 250) {
      told = performance.now();
      self.postMessage({ progress: [loaded, total] });
    }
  }
  const all = new Uint8Array(loaded);
  chunks.reduce((at, c) => (all.set(c, at), at + c.length), 0);
  return all;
}

// The model is the one big file, kept in the Cache API so a later visit doesn't download it again.
async function cached(url: string): Promise<Uint8Array> {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(url);
  if (hit) return new Uint8Array(await hit.arrayBuffer());
  const data = await download(url);
  await cache.put(url, new Response(data));
  return data;
}
const bytes = async (url: string) => new Uint8Array(await (await fetch(url)).arrayBuffer());

let ort: typeof Ort;

async function start(base: string) {
  const url = (f: string) => new URL(`voice/${f}`, base).href;
  ort = await import(/* @vite-ignore */ new URL("ort/ort.wasm.min.mjs", base).href);
  ort.env.wasm.wasmPaths = new URL("ort/", base).href;
  ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency) : 1;
  const [config, model, espeak] = await Promise.all([
    fetch(url(`${MODEL}.json`)).then((r) => r.json() as Promise<Config>),
    cached(url(MODEL)),
    createEspeak() as Promise<Espeak>,
  ]);
  espeak.FS.mkdirTree("/espeak-ng-data/lang/gmw");
  await Promise.all(ESPEAK_DATA.map(async (f: string) => espeak.FS.writeFile(`/espeak-ng-data/${f}`, await bytes(url(`espeak-ng-data/${f}`)))));
  if (espeak.ccall("init", "number", ["string", "string"], ["/espeak-ng-data", config.espeak.voice]) !== 0) throw new Error("espeak-ng didn't start");
  const session = await ort.InferenceSession.create(model, { executionProviders: ["wasm"] });
  return { config, session, espeak };
}

type Voice = Awaited<ReturnType<typeof start>>;

// One phoneme list per sentence, as PiperVoice.phonemize.
function sentences({ espeak }: Voice, text: string): string[][] {
  const out: string[][] = [];
  let cur: string[] = [];
  for (const line of (espeak.ccall("phonemize", "string", ["string"], [text]) as string).split("\n").filter(Boolean)) {
    const [raw, flags] = line.split("\t");
    const term = TERMINATORS[+flags] ?? "";
    const ph = raw.replace(/\([^)]+\)/g, "") + term + (",:;".includes(term) && term ? " " : "");
    cur.push(...ph.normalize("NFD"));
    if (+flags & SENTENCE_END) {
      out.push(cur);
      cur = [];
    }
  }
  return [...out, cur].filter((s) => s.length);
}

const ids = ({ config: { phoneme_id_map: m } }: Voice, phonemes: string[]) =>
  [...m["^"], ...m["_"], ...phonemes.flatMap((p) => (m[p] ? [...m[p], ...m["_"]] : [])), ...m["$"]];
const int64 = (xs: number[], dims?: number[]) => new ort.Tensor("int64", BigInt64Array.from(xs, BigInt), dims);

// Each sentence normalized to full scale, then to 16 bits, as Piper's synthesize().
async function speak(voice: Voice, text: string): Promise<Int16Array> {
  const parts: Int16Array[] = [];
  for (const phonemes of sentences(voice, text)) {
    const input = ids(voice, phonemes);
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
self.onmessage = async ({ data }: MessageEvent<{ base: string } | { id: number; text: string }>) => {
  if ("base" in data) {
    voice = start(data.base);
    return voice.then(() => self.postMessage({ ready: true }), (e) => self.postMessage({ failed: String(e) }));
  }
  try {
    const v = await voice!;
    const pcm = await speak(v, data.text);
    (self as unknown as Worker).postMessage({ id: data.id, pcm, rate: v.config.audio.sample_rate }, [pcm.buffer]);
  } catch (e) {
    self.postMessage({ id: data.id, error: String(e) });
  }
};
