// Minimal ustar writer plus gzip, matching what `tar -czf` produces for `just build-packs`
// closely enough for Python's tarfile to extract. No external dependency.

export interface TarEntry { path: string; data: Uint8Array }

const BLOCK = 512;
const enc = new TextEncoder();

function octal(value: number, width: number): string {
  return value.toString(8).padStart(width - 1, "0") + "\0";
}

function header(path: string, size: number, typeflag: "0" | "5", mtime: number): Uint8Array {
  const h = new Uint8Array(BLOCK);
  const put = (offset: number, text: string) => h.set(enc.encode(text).subarray(0, 100), offset);
  put(0, path);
  put(100, octal(typeflag === "5" ? 0o755 : 0o644, 8));
  put(108, octal(0, 8));
  put(116, octal(0, 8));
  put(124, octal(size, 12));
  put(136, octal(mtime, 12));
  put(148, "        ");
  put(156, typeflag);
  put(257, "ustar\0");
  put(263, "00");
  let checksum = 0;
  for (const b of h) checksum += b;
  put(148, checksum.toString(8).padStart(6, "0") + "\0 ");
  return h;
}

export function tar(entries: TarEntry[], mtime = Math.floor(Date.now() / 1000)): Uint8Array {
  const dirs = new Set<string>();
  for (const { path } of entries) {
    const parts = path.split("/");
    for (let i = 1; i < parts.length; i++) dirs.add(parts.slice(0, i).join("/") + "/");
  }
  const chunks: Uint8Array[] = [];
  for (const dir of [...dirs].sort()) chunks.push(header(dir, 0, "5", mtime));
  for (const { path, data } of entries) {
    if (path.length > 100) throw new Error(`Path too long for the pack: ${path}`);
    chunks.push(header(path, data.length, "0", mtime), data);
    const pad = (BLOCK - (data.length % BLOCK)) % BLOCK;
    if (pad) chunks.push(new Uint8Array(pad));
  }
  chunks.push(new Uint8Array(BLOCK * 2));
  const out = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

export async function gzip(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new CompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
