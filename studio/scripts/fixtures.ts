// Files the end-to-end tests feed Studio and the SDK: a PNG from a color function, and a tone.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { crc32, deflateSync } from "node:zlib";
import { CLIP_SAMPLE_RATE, encodeWav, type Clip } from "@sdk";

export const tone = (hz: number, seconds = 0.2, rate = CLIP_SAMPLE_RATE): Clip =>
  ({ rate, samples: Float32Array.from({ length: Math.round(rate * seconds) }, (_, i) => 0.3 * Math.sin((2 * Math.PI * hz * i) / rate)) });

export function png(w: number, h: number, color: (x: number, y: number) => number[]): Uint8Array {
  const chunk = (type: string, data: Uint8Array) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const out = Buffer.alloc(12 + data.length);
    out.writeUInt32BE(data.length, 0);
    body.copy(out, 4);
    out.writeUInt32BE(crc32(body), 8 + data.length);
    return out;
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr.set([8, 2, 0, 0, 0], 8);
  const rows = Buffer.concat(Array.from({ length: h }, (_, y) => Buffer.from([0, ...Array.from({ length: w }, (_, x) => color(x, y)).flat()])));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

export const solid = (w: number, h: number, rgb: number[]) => png(w, h, () => rgb);
// Something like a photo: a sky over grass with a sun, so painting it has edges to keep.
export const photo = () => png(320, 240, (x, y) => ((x - 250) ** 2 + (y - 50) ** 2 < 900 ? [255, 210, 40] : y > 160 ? [40, 150, 50] : [90, 160, 230 - y / 2]));

// What a parent has on hand in Studio: a photo to choose, and what the (fake) microphone hears.
export function studioFiles(dir: string): { photo: string; mic: string } {
  mkdirSync(dir, { recursive: true });
  const files = { photo: join(dir, "backyard.png"), mic: join(dir, "mic.wav") };
  writeFileSync(files.photo, photo());
  writeFileSync(files.mic, encodeWav(tone(440, 3, 48000)));
  return files;
}
