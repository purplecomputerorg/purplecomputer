// Purple's own voice for the browser Purple. The model is a big download, so it starts the first time
// Purple speaks (or at boot, when an earlier visit already has it), and the browser's voice fills in
// until it's ready.
import { CACHE, MODEL } from "./piperfiles";

const base = document.baseURI;
let worker: Worker | null = null;
let ready = false;
let next = 0;
export interface Speech { pcm: Int16Array; rate: number }
const waiting = new Map<number, (speech: Speech | null) => void>();

// Shown once something has tried to speak, until the voice is ready (null hides it).
let asked = false;
let began = 0;
let eta = "";
let onNote = (_text: string | null) => {};
export const onVoiceNote = (f: typeof onNote) => (onNote = f);
const note = () => onNote(asked && !ready ? `Purple's voice is loading${eta}` : null);

function progress([loaded, total]: [number, number]) {
  began ||= performance.now() - 1;
  const left = total > loaded ? ((total - loaded) * (performance.now() - began)) / loaded / 1000 : 0;
  eta = !total ? "" : left < 2 ? ", almost ready" : `, ready in about ${Math.ceil(left)} seconds`;
  note();
}

function start() {
  if (worker) return;
  worker = new Worker(new URL("./piper.worker.ts", import.meta.url), { type: "module" });
  worker.onmessage = ({ data }) => {
    if (data.progress) progress(data.progress);
    if (data.ready || data.failed) {
      ready = !!data.ready;
      asked = false;
      note();
    }
    if (data.failed) console.warn("[studio] Purple's voice didn't load, the browser's speaks instead:", data.failed);
    if (data.error) console.warn("[studio] Purple's voice:", data.error);
    waiting.get(data.id)?.(data.pcm ? { pcm: data.pcm, rate: data.rate } : null);
    waiting.delete(data.id);
  };
  worker.onerror = (e) => console.warn("[studio] Purple's voice didn't load, the browser's speaks instead:", e.message);
  worker.postMessage({ base });
}

export async function startIfCached() {
  if (await caches.match(new URL(`voice/${MODEL}`, base).href, { cacheName: CACHE }).catch(() => null)) start();
}

// Purple's prepared text as 16-bit samples, or null while the voice is still loading.
export function piperSay(text: string): Promise<Speech | null> {
  start();
  if (!ready) {
    asked = true;
    note();
    return Promise.resolve(null);
  }
  return new Promise((done) => {
    waiting.set(++next, done);
    worker!.postMessage({ id: next, text });
  });
}

// Drops every line asked for so far: those not spoken yet answer null and never play late.
export function piperHush() {
  if (!waiting.size) return;
  worker?.postMessage({ drop: next });
  for (const done of waiting.values()) done(null);
  waiting.clear();
}
