// What Purple's two voices share in a worker: the model files, kept in the Cache API, onnxruntime-web,
// and espeak-ng phonemes the way piper-tts 1.4.1 makes them.
import type * as Ort from "onnxruntime-web";
// @ts-expect-error: emscripten output, no types
import createEspeak from "../../vendor/espeak-ng/espeak.mjs";
import { CACHE, ESPEAK_DATA } from "./piperfiles";

export interface Espeak { FS: { mkdirTree(p: string): void; writeFile(p: string, d: Uint8Array): void }; ccall(f: string, r: string, t: string[], a: unknown[]): number | string }
export type Progress = (loaded: number, total: number) => void;

// espeak-ng's clause terminator flags, as piper's espeakbridge.c reads them.
const TERMINATORS: Record<number, string> = { [40 | 0x80000]: ".", [20 | 0x1000 | 0x40000]: ",", [40 | 0x2000 | 0x80000]: "?",
  [45 | 0x3000 | 0x80000]: "!", [30 | 0x40000]: ":", [30 | 0x1000 | 0x40000]: ";" };
const SENTENCE_END = 0x80000;

// Read in chunks so Studio can say how long the voice has left to load.
async function download(url: string, progress: Progress): Promise<Uint8Array<ArrayBuffer>> {
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
      progress(loaded, total);
    }
  }
  const all = new Uint8Array(loaded);
  chunks.reduce((at, c) => (all.set(c, at), at + c.length), 0);
  return all;
}

// A model is the one big file, kept so a later visit doesn't download it again.
export async function cached(url: string, progress: Progress): Promise<Uint8Array> {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(url);
  if (hit) return new Uint8Array(await hit.arrayBuffer());
  const data = await download(url, progress);
  await cache.put(url, new Response(data));
  return data;
}
export const bytes = async (url: string) => new Uint8Array(await (await fetch(url)).arrayBuffer());

export async function onnx(base: string): Promise<typeof Ort> {
  const ort: typeof Ort = await import(/* @vite-ignore */ new URL("ort/ort.wasm.min.mjs", base).href);
  ort.env.wasm.wasmPaths = new URL("ort/", base).href;
  ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency) : 1;
  return ort;
}

export async function espeak(base: string, voice: string): Promise<Espeak> {
  const e = (await createEspeak()) as Espeak;
  e.FS.mkdirTree("/espeak-ng-data/lang/gmw");
  await Promise.all(ESPEAK_DATA.map(async (f: string) => e.FS.writeFile(`/espeak-ng-data/${f}`, await bytes(new URL(`voice/espeak-ng-data/${f}`, base).href))));
  if (e.ccall("init", "number", ["string", "string"], ["/espeak-ng-data", voice]) !== 0) throw new Error("espeak-ng didn't start");
  return e;
}

// One phoneme list per sentence, as PiperVoice.phonemize.
export function sentences(espeak: Espeak, text: string): string[][] {
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
