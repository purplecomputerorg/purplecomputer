// An instrument's notes for a pack, rendered across a few workers and kept for the last few sounds:
// the live Purple gets a new pack on every slider move, and rendering on the page took about a second.
import type { PackInstrument } from "@sdk/pack";
import { SAMPLE_PITCHES } from "@sdk/purple/sounds";
import type { NotesJob } from "./notes.worker";

const KEPT = 8;
const rendered = new Map<string, Promise<Uint8Array[]>>();
let workers: Worker[] = [];
let next = 0;
const waiting = new Map<number, (wavs: Uint8Array[]) => void>();

function pool(): Worker[] {
  if (!workers.length) {
    const n = Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 2) - 1));
    workers = Array.from({ length: n }, () => {
      const w = new Worker(new URL("./notes.worker.ts", import.meta.url), { type: "module" });
      w.onmessage = ({ data }) => {
        waiting.get(data.id)?.(data.wavs);
        waiting.delete(data.id);
      };
      return w;
    });
  }
  return workers;
}

async function render({ base, params }: PackInstrument): Promise<Uint8Array[]> {
  const all = pool();
  const shares = all.map((_, w) => SAMPLE_PITCHES.map((_, i) => i).filter((i) => i % all.length === w));
  const parts = await Promise.all(all.map((worker, w) => new Promise<Uint8Array[]>((done) => {
    const job: NotesJob = { id: ++next, base, params, freqs: shares[w].map((i) => SAMPLE_PITCHES[i].freq) };
    waiting.set(job.id, done);
    worker.postMessage(job);
  })));
  const notes: Uint8Array[] = [];
  shares.forEach((share, w) => share.forEach((i, k) => (notes[i] = parts[w][k])));
  return notes;
}

// Undefined where there are no workers (the tests run in Node); the SDK renders them itself then.
export function instrumentNotes(inst: PackInstrument): Promise<Uint8Array[]> | undefined {
  if (typeof Worker === "undefined") return undefined;
  const key = `${inst.base}|${JSON.stringify(inst.params)}`;
  const notes = rendered.get(key) ?? render(inst);
  rendered.delete(key);
  rendered.set(key, notes);
  if (rendered.size > KEPT) rendered.delete(rendered.keys().next().value!);
  return notes;
}
