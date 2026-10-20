// The rooms' fixed lines (fixedSays) in the room voice, for the pack: each spoken once by
// roomvoice.worker.ts, a few seconds a line, and kept in the Cache API. The preview takes the lines
// already done and hears the rest in Purple's own voice until they are; a download waits for all.
import { type PackRoomLine } from "@sdk/pack";
import { voiceClipFilename } from "@sdk/purple/sounds";
import { fixedSays } from "@sdk/says";
import { decodeWav } from "@sdk/wav";
import { decodeToClip, encodeWav, normalize, tidy, type Clip } from "./audio";
import type { Kokoro } from "./roomvoice.worker";

const CACHE = "purple-room-voice-1";
const base = () => document.baseURI;
let settings: Promise<Pick<Kokoro, "model" | "voice" | "speed" | "rate"> | null> | null = null;
let worker: Promise<Worker | null> | null = null;
let queue: Promise<unknown> = Promise.resolve();
let next = 0;
const waiting = new Map<number, (samples: Float32Array | null) => void>();
const lines = new Map<string, Promise<Clip | null>>();
const done = new Map<string, Clip>();
// The lines the rooms say now: a line edited away before its turn is skipped.
let wanted = new Set<string>();
let version = 0;
const listeners: (() => void)[] = [];
export const roomVoiceVersion = () => version;
export const onRoomVoice = (f: () => void) => listeners.push(f);

const spec = () => (settings ??= fetch(new URL("voice/kokoro/kokoro.json", base())).then((r) => (r.ok ? r.json() : null)).catch(() => null));

function start(): Promise<Worker | null> {
  return (worker ??= new Promise((ready) => {
    const w = new Worker(new URL("./roomvoice.worker.ts", import.meta.url), { type: "module" });
    const fail = (why: unknown) => (console.warn("[studio] The room voice didn't load, rooms speak in Purple's own voice:", why), ready(null));
    w.onmessage = ({ data }) => {
      if (data.ready) ready(w);
      if (data.failed) fail(data.failed);
      if (data.error) console.warn("[studio] The room voice:", data.error);
      waiting.get(data.id)?.(data.samples ?? null);
      waiting.delete(data.id);
    };
    w.onerror = (e) => fail(e.message);
    w.postMessage({ base: base() });
  }));
}

// One at a time: the worker has one model.
function speak(text: string): Promise<Float32Array | null> {
  const turn = queue.then(async () => {
    const w = wanted.has(text) ? await start() : null;
    return w && new Promise<Float32Array | null>((answer) => {
      waiting.set(++next, answer);
      w.postMessage({ id: next, text });
    });
  });
  queue = turn;
  return turn;
}

async function render(text: string): Promise<Clip | null> {
  const s = await spec();
  if (!s) return null;
  const cache = await caches.open(CACHE);
  const key = new URL(`room-voice/${encodeURIComponent(`${s.model}|${s.voice}|${s.speed}`)}/${encodeURIComponent(text)}`, base()).href;
  const hit = await cache.match(key);
  if (hit) return decodeWav(new Uint8Array(await hit.arrayBuffer()));
  const samples = await speak(text);
  if (!samples) return null;
  // Purple's clip rate, trimmed and leveled like a recorded phrase.
  const clip = normalize(tidy(await decodeToClip(new Blob([encodeWav({ samples, rate: s.rate }) as BlobPart]))));
  await cache.put(key, new Response(encodeWav(clip) as BlobPart));
  return clip;
}

function line(text: string): Promise<Clip | null> {
  let clip = lines.get(text);
  if (!clip) {
    clip = render(text).catch((e) => (console.warn("[studio] The room voice:", e), null));
    lines.set(text, clip);
    void clip.then((c) => {
      if (c) {
        done.set(text, c);
        version++;
        listeners.forEach((f) => f());
      } else lines.delete(text);  // skipped or failed: asked again next time
    });
  }
  return clip;
}

// The rooms' fixed lines with their clips: the ones done so far, or with `wait` every one there can be.
export async function roomVoice(sources: string[], wait = false, onProgress?: (msg: string) => void): Promise<PackRoomLine[]> {
  if (typeof Worker === "undefined") return [];
  const texts = [...new Map(sources.flatMap(fixedSays).map((t) => [voiceClipFilename(t), t])).values()];
  wanted = new Set(texts);
  texts.forEach(line);
  if (wait) {
    for (const [i, text] of texts.entries()) {
      onProgress?.(`Recording your rooms' lines, ${i + 1} of ${texts.length}`);
      await line(text);
    }
  }
  return texts.flatMap((text) => (done.has(text) ? [{ text, clip: done.get(text)! }] : []));
}
