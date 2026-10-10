// A room's own thread. Loads Pyodide as soon as it starts (so a spare is warm), then on
// {type: "run"} puts purple.py in place, walls off JavaScript, and runs the room until the page
// terminates it. Messages to the page are postMessage'd JSON strings; messages from the page
// arrive through the shared channel, so the room can block on them.
import purpleSource from "../../../purple_tui/roomkit/purple.py?raw";
import guest from "./guest.py?raw";
import { take } from "./channel";

interface Pyodide {
  FS: { mkdirTree(path: string): void; writeFile(path: string, data: string): void };
  globals: { set(name: string, value: unknown): void };
  registerJsModule(name: string, module: object): void;
  setStdout(options: { batched: (text: string) => void }): void;
  setStderr(options: { batched: (text: string) => void }): void;
  runPython(code: string): unknown;
}

type Start = { type: "init"; indexURL: string; channel: SharedArrayBuffer } | { type: "run"; source: string };

// The DOM lib types postMessage for windows; in a worker it takes just the message.
const post = (text: string) => (self as unknown as { postMessage(m: string): void }).postMessage(text);

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
  py.FS.writeFile("/purple/purple.py", purpleSource);
  py.runPython("import sys; sys.path.insert(0, '/purple')");
  py.setStdout({ batched: (text) => post(JSON.stringify({ cmd: "print", text })) });
  py.setStderr({ batched: (text) => post(JSON.stringify({ cmd: "print", text })) });
  py.registerJsModule("room_channel", {
    send: bare((text: string) => post(String(text))),
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
  let py: Pyodide;
  try {
    py = await ready!;
  } catch (err) {
    return post(JSON.stringify({ cmd: "error", text: `Python did not load: ${err}`, line: null }));
  }
  py.runPython(guest);
  cutNetwork();
  py.globals.set("ROOM_SOURCE", msg.source);
  post(JSON.stringify({ cmd: "started" }));
  py.runPython("purple.run(ROOM_SOURCE)");
  post(JSON.stringify({ cmd: "ended" }));
};
