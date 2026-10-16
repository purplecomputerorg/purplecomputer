// A room's own thread. Loads Pyodide as soon as it starts (so a spare is warm), then on {type: "run"}
// walls off JavaScript and serves the room with Purple's runner.py until the page terminates it.
// Lines from the page arrive through the shared channel, so the room can block on them.
import runnerSource from "../../../purple_tui/roomkit/runner.py?raw";
import guest from "./guest.py?raw";
import { take } from "./channel";

interface Pyodide {
  FS: { mkdirTree(path: string): void; writeFile(path: string, data: string): void };
  registerJsModule(name: string, module: object): void;
  setStdout(options: { batched: (text: string) => void }): void;
  setStderr(options: { batched: (text: string) => void }): void;
  runPython(code: string): unknown;
}

// line: a reply for Purple; print: the room's print() output; ended: Python returned or failed.
export type FromWorker = { line: string } | { print: string } | { ended: string | null };
type Start = { type: "init"; indexURL: string; channel: SharedArrayBuffer } | { type: "run" };

// The DOM lib types postMessage for windows; in a worker it takes just the message.
const post = (m: FromWorker) => (self as unknown as { postMessage(m: FromWorker): void }).postMessage(m);

let ready: Promise<Pyodide> | null = null;
let channel: SharedArrayBuffer;

// Functions the room's Python can call, with no prototype so a proxy to them leads nowhere.
function bare<T extends (...args: never[]) => unknown>(fn: T): T {
  Object.setPrototypeOf(fn, null);
  return fn;
}

async function load(indexURL: string): Promise<Pyodide> {
  const { loadPyodide } = (await import(/* @vite-ignore */ `${indexURL}pyodide.mjs`)) as { loadPyodide: (o: { indexURL: string }) => Promise<Pyodide> };
  const py = await loadPyodide({ indexURL });
  py.FS.mkdirTree("/purple");
  py.FS.writeFile("/purple/runner.py", runnerSource);
  py.runPython("import sys; sys.path.insert(0, '/purple')");
  py.setStdout({ batched: (text) => post({ print: text }) });
  py.setStderr({ batched: (text) => post({ print: text }) });
  py.registerJsModule("room_channel", {
    send: bare((text: string) => post({ line: String(text) + "\n" })),
    recv: bare(() => take(channel)),
  });
  return py;
}

// Once the room starts, nothing in this thread needs the network again.
function cutNetwork(): void {
  for (const name of ["fetch", "XMLHttpRequest", "WebSocket", "EventSource", "importScripts", "WebTransport"]) {
    try { Object.defineProperty(self, name, { value: undefined, configurable: false }); } catch { /* not present here */ }
  }
}

self.onmessage = async (e: MessageEvent<Start>) => {
  const msg = e.data;
  if (msg.type === "init") {
    channel = msg.channel;
    ready = load(msg.indexURL);
    return;
  }
  try {
    const py = await ready!;
    cutNetwork();
    py.runPython(guest);
    post({ ended: null });
  } catch (err) {
    post({ ended: String(err) });
  }
};
