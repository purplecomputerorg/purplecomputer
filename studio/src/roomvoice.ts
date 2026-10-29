// The rooms' lines known before they run (roomSays) in the room voice, for the pack: each spoken once by
// roomvoice.worker.ts, a few seconds a line, and kept in the Cache API. The preview starts a room once
// its lines are done (roomReady), and a download waits for all.
import { type PackRoomLine } from "@sdk/pack";
import { voiceClipFilename } from "@sdk/purple/sounds";
import { asSaid, fits, fixedSays } from "@sdk/says";
import { decodeWav } from "@sdk/wav";
import { decodeToClip, encodeWav, normalize, stretch, tidy, type Clip } from "./audio";
import { loudLines } from "./knobs";
import type { Kokoro } from "./roomvoice.worker";
import { speakable } from "./speakable";
import { draft, phraseFor, type RoomDraft } from "./state";

const CACHE = "purple-room-voice-1";
const base = () => document.baseURI;
let settings: Promise<Pick<Kokoro, "model" | "voice" | "tempo" | "rate"> | null> | null = null;
let worker: Promise<Worker | null> | null = null;
let loaded = false;
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
      if (data.ready) { loaded = true; ready(w); }
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
  if (!s || !(text = await speakable(text))) return null;
  const cache = await caches.open(CACHE);
  const key = new URL(`room-voice/${encodeURIComponent(`${s.model}|${s.voice}|${s.tempo}`)}/${encodeURIComponent(text)}`, base()).href;
  const hit = await cache.match(key);
  if (hit) return decodeWav(new Uint8Array(await hit.arrayBuffer()));
  const samples = await speak(text);
  if (!samples) return null;
  // Purple's clip rate, trimmed and leveled like a recorded phrase.
  const clip = normalize(tidy(await decodeToClip(new Blob([encodeWav(stretch({ samples, rate: s.rate }, s.tempo)) as BlobPart]))));
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

// One line in the room voice, for a form's ▶; null when the voice can't load.
export function roomLine(text: string): Promise<Clip | null> {
  wanted.add(asSaid(text));
  return line(asSaid(text));
}

type Said = Pick<RoomDraft, "source" | "made">;
const recorded = (name = "") => draft.roomFiles.some((f) => f.kind === "sounds" && f.name === name);

// What a room says that's known before it runs: say("...") lines, the words of knobs said out loud, and a
// form's words. A line the family recorded is left out, since Purple looks in the room voice first.
function roomSays({ source, made }: Said): string[] {
  const said = made?.kind === "soundboard" ? [...made.data.rows, made.data.other].filter((s) => !recorded(s.voice)).map((s) => s.word)
    : made?.kind === "quiz" ? made.data.rows.flatMap((q) => [q.question, ...[q.right, ...q.others].map((c) => c.word)])
    : [...fixedSays(source), ...loudLines(source)];
  return said.map((t) => asSaid(t.trim())).filter((t) => fits(t) && !phraseFor(t));
}

const unique = (texts: string[]) => [...new Map(texts.map((t) => [voiceClipFilename(t), t])).values()];

async function ready(texts: string[], onProgress?: (msg: string) => void) {
  for (const [i, text] of texts.entries()) {
    if (!done.has(text)) onProgress?.(loaded ? `Preparing your rooms' lines, ${i + 1} of ${texts.length}` : "Getting Purple's voice ready");
    await line(text);
  }
}

// The rooms' lines with their clips: the ones done so far, or with `wait` every one there can be.
export async function roomVoice(rooms: Said[], wait = false, onProgress?: (msg: string) => void): Promise<PackRoomLine[]> {
  if (typeof Worker === "undefined") return [];
  const texts = unique(rooms.flatMap(roomSays));
  wanted = new Set(texts);
  texts.forEach(line);
  if (wait) await ready(texts, onProgress);
  return texts.flatMap((text) => (done.has(text) ? [{ text, clip: done.get(text)! }] : []));
}

// Resolves once every line the room says is in the room voice, so the preview never says one in another voice first.
export async function roomReady(room: Said, onProgress?: (msg: string) => void): Promise<void> {
  if (typeof Worker === "undefined") return;
  const texts = unique(roomSays(room));
  texts.forEach((t) => wanted.add(t));
  await ready(texts, onProgress);
}

// Studio starts the room voice as it opens, so it's ready by the time a room speaks.
export const warmRoomVoice = () => void spec().then((s) => s && start());
