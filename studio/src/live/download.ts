// How much of what Purple fetches to start has arrived, for the loading bar. Each fetch is counted from a
// clone, so Pyodide gets the real response and the wasm keeps the browser's compiled-code cache.
// Published file name -> decoded size, from vite.config.ts.
declare const __PURPLE_DOWNLOADS__: Record<string, number>;

// The packages Purple's Python loads as it starts.
export const PACKAGES = ["pygame-ce", "rich", "wcwidth"];

// Calls progress with the fraction downloaded so far, until the returned stop is called.
export function countDownloads(progress: (fraction: number) => void): () => void {
  const sizes = __PURPLE_DOWNLOADS__;
  const total = Object.values(sizes).reduce((a, b) => a + b, 0);
  let got = 0;
  const drain = async (body: ReadableStream<Uint8Array>) => {
    const reader = body.getReader();
    for (let r = await reader.read(); !r.done; r = await reader.read()) progress(Math.min(1, (got += r.value.length) / total));
  };
  const plain = globalThis.fetch;
  globalThis.fetch = async (...args: Parameters<typeof fetch>) => {
    const response = await plain(...args);
    const name = new URL(response.url, location.href).pathname.split("/").pop()!;
    if (name in sizes && response.body) void drain(response.clone().body!).catch(() => {});
    return response;
  };
  return () => void (globalThis.fetch = plain);
}
