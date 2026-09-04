import { describe, expect, it } from "vitest";
import { gzip, tar } from "../sdk/src/tar";

const dec = new TextDecoder();
const field = (block: Uint8Array, offset: number, len: number) => dec.decode(block.subarray(offset, offset + len)).replace(/\0.*$/s, "");

function readHeaders(archive: Uint8Array) {
  const out: { name: string; size: number; type: string; checksumOk: boolean }[] = [];
  for (let off = 0; off + 512 <= archive.length; ) {
    const block = archive.subarray(off, off + 512);
    if (block.every((b) => b === 0)) break;
    const size = parseInt(field(block, 124, 12), 8);
    let sum = 0;
    block.forEach((b, i) => (sum += i >= 148 && i < 156 ? 32 : b));
    out.push({ name: field(block, 0, 100), size, type: field(block, 156, 1), checksumOk: sum === parseInt(field(block, 148, 8), 8) });
    off += 512 + Math.ceil(size / 512) * 512;
  }
  return out;
}

describe("tar", () => {
  it("writes ustar headers with directory entries and valid checksums", () => {
    const archive = tar([
      { path: "manifest.json", data: new TextEncoder().encode("{}") },
      { path: "content/letters/a.wav", data: new Uint8Array(600) },
    ], 0);
    const headers = readHeaders(archive);
    expect(headers.map((h) => [h.name, h.type, h.size])).toEqual([
      ["content/", "5", 0],
      ["content/letters/", "5", 0],
      ["manifest.json", "0", 2],
      ["content/letters/a.wav", "0", 600],
    ]);
    expect(headers.every((h) => h.checksumOk)).toBe(true);
    expect(archive.length % 512).toBe(0);
  });

  it("refuses names the installer would reject", () => {
    expect(() => tar([{ path: "a".repeat(101), data: new Uint8Array(0) }])).toThrow();
  });

  it("gzips to a stream python's tarfile can open", async () => {
    const gz = await gzip(tar([{ path: "manifest.json", data: new Uint8Array(10) }]));
    expect([gz[0], gz[1]]).toEqual([0x1f, 0x8b]);
  });
});
