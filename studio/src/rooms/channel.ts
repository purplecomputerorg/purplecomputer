// One message at a time from the page to the room's worker, in shared memory so the worker
// can block on it (purple.ask and the event loop are blocking reads). Layout: [state, length]
// as Int32, then UTF-8 bytes. state 0 = empty, 1 = full.
const HEADER = 8;
export const CHANNEL_BYTES = 1 << 16;

export const newChannel = () => new SharedArrayBuffer(HEADER + CHANNEL_BYTES);

const enc = new TextEncoder();
const dec = new TextDecoder();

// Page side: false when the worker has not taken the last message yet.
export function put(sab: SharedArrayBuffer, text: string): boolean {
  const head = new Int32Array(sab, 0, 2);
  if (Atomics.load(head, 0) !== 0) return false;
  const bytes = enc.encode(text).slice(0, CHANNEL_BYTES);
  new Uint8Array(sab, HEADER).set(bytes);
  head[1] = bytes.length;
  Atomics.store(head, 0, 1);
  Atomics.notify(head, 0);
  return true;
}

// Worker side: blocks until a message is there, then empties the slot.
export function take(sab: SharedArrayBuffer): string {
  const head = new Int32Array(sab, 0, 2);
  Atomics.wait(head, 0, 0);
  const text = dec.decode(new Uint8Array(sab, HEADER, head[1]).slice());
  Atomics.store(head, 0, 0);
  return text;
}
