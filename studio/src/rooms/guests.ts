// Family rooms for the Purple running in Studio's preview: Purple's own FamilyRoom (through
// browser.py's JsGuest) starts a room here and gets each reply line back, the way it talks to the
// room's process on a laptop. Each room is a Web Worker; a spare one stays warm for the next.
import { newChannel, put } from "./channel";
import type { FromWorker } from "./worker";

// Rooms block on shared memory, which browsers only allow on a cross-origin isolated page, and
// that needs a secure context: https, or http on localhost.
export const NOT_ISOLATED = "The preview needs a secure page. Open Purple Studio at its https:// address, or at http://localhost on the computer running it.";

interface Guest { worker: Worker; channel: SharedArrayBuffer; queue: string[]; pump: number }

function spawn(): Guest {
  const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  const channel = newChannel();
  worker.postMessage({ type: "init", indexURL: new URL("pyodide/", document.baseURI).href, channel });
  return { worker, channel, queue: [], pump: 0 };
}

export interface RoomGuests {
  // onLine gets each reply line, then null when the room's Python ends.
  start(onLine: (line: string | null) => void): number;
  send(id: number, line: string): void;
  stop(id: number): void;
}

export function roomGuests(print: (text: string) => void): RoomGuests {
  const running = new Map<number, Guest>();
  let spare: Guest | null = null;
  let next = 0;

  // The worker takes one line at a time; Purple sends one and waits, so this rarely waits at all.
  const flush = (g: Guest) => {
    clearTimeout(g.pump);
    while (g.queue.length && put(g.channel, g.queue[0])) g.queue.shift();
    if (g.queue.length) g.pump = window.setTimeout(() => flush(g), 5);
  };

  return {
    start(onLine) {
      const id = ++next;
      if (!globalThis.crossOriginIsolated) {
        queueMicrotask(() => onLine(JSON.stringify({ error: { text: NOT_ISOLATED, line: null } }) + "\n"));
        return id;
      }
      const g = spare ?? spawn();
      spare = spawn();
      running.set(id, g);
      g.worker.onmessage = (e: MessageEvent<FromWorker>) => {
        const m = e.data;
        if ("line" in m) onLine(m.line);
        else if ("print" in m) print(m.print);
        else onLine(m.ended === null ? null : JSON.stringify({ error: { text: m.ended, line: null } }) + "\n");
      };
      g.worker.postMessage({ type: "run" });
      return id;
    },
    send(id, line) {
      const g = running.get(id);
      if (!g) return;
      g.queue.push(line);
      flush(g);
    },
    stop(id) {
      const g = running.get(id);
      if (!g) return;
      clearTimeout(g.pump);
      g.worker.onmessage = null;  // Purple has let go; a message already on its way goes nowhere
      g.worker.terminate();
      running.delete(id);
    },
  };
}
