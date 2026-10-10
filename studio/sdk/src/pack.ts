// Builds a .purplepack from a plain description. Everything Purple reads is described
// in studio/PACK_FORMAT.md; this is the one place that knows the file layout.
import exported from "./purple/export.json";
import { ASDF_ROW, QWERTY_ROW, ZXCV_ROW, generateRowGradient, type PaintOp } from "./purple/art";
import { SAMPLE_PITCHES, voiceClipFilename } from "./purple/sounds";
import { SYNTH_RATE, renderNote, type BaseName, type Params } from "./purple/synth";
import { gzip, tar, type TarEntry } from "./tar";
import { encodeWav, type Clip } from "./wav";

export interface PackPicture { name: string; ops: PaintOp[]; png?: Uint8Array }
export interface PackInstrument { name: string; base: BaseName; params: Params }
export interface PackTheme { background: string; surface: string; hues: { qwerty: number; asdf: number; zxcv: number } }
// content/rooms/<name>.py: Python run as a guest (guides/family-rooms.md); the Blockly workspace it came from rides beside it.
export interface PackRoom { name: string; source: string; blocks?: unknown }

export interface PackSpec {
  familyName: string;
  words: { word: string; emoji: string }[];
  synonyms: { alias: string; word: string }[];
  ranked: string[];
  letters: Record<string, Clip>;
  phrases: { text: string; clip: Clip }[];
  pictures: PackPicture[];
  instruments: PackInstrument[];
  rooms: PackRoom[];
  theme: PackTheme | null;
}

export const PACK_FORMAT: number = exported.pack_format;

const enc = new TextEncoder();
const text = (path: string, body: string): TarEntry => ({ path, data: enc.encode(body) });
const json = (path: string, value: unknown) => text(path, JSON.stringify(value, null, 2) + "\n");

export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
export const ROOM_NAME = /^[a-z0-9][a-z0-9-]{0,39}$/;
// content.display_name: what Purple shows for a room called `name`.
export const roomTitle = (name: string) =>
  name.replace(/[-_]/g, " ").trim().replace(/[a-zA-Z]+/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase()).slice(0, 24);
export const packId = (spec: Pick<PackSpec, "familyName">) => `${slug(spec.familyName) || "our-family"}-pack`;
export const packFilename = (spec: Pick<PackSpec, "familyName">) => `${packId(spec)}.purplepack`;

export function manifest(spec: Pick<PackSpec, "familyName">) {
  const name = spec.familyName;
  return {
    id: packId(spec),
    name: name ? `${name}${/s$/i.test(name) ? "'" : "'s"} Purple` : "Our Purple",
    version: "1.0.0",
    type: "emoji",
    format: PACK_FORMAT,
    description: "Made with Purple Studio.",
  };
}

export function emojiEntries(spec: PackSpec): TarEntry[] {
  const out: TarEntry[] = [];
  if (spec.words.length) out.push(json("content/emoji.json", Object.fromEntries(spec.words.map((w) => [w.word, w.emoji]))));
  if (spec.synonyms.length) out.push(json("content/synonyms.json", Object.fromEntries(spec.synonyms.map((s) => [s.alias, s.word]))));
  if (spec.ranked.length) out.push(text("content/rankings.txt", spec.ranked.join("\n") + "\n"));
  return out;
}

export function themeJson(t: PackTheme) {
  return {
    background: t.background,
    surface: t.surface,
    keys: {
      ...generateRowGradient(t.hues.qwerty, QWERTY_ROW),
      ...generateRowGradient(t.hues.asdf, ASDF_ROW),
      ...generateRowGradient(t.hues.zxcv, ZXCV_ROW),
    },
  };
}

const yieldToUi = () => new Promise((r) => setTimeout(r, 0));

export async function buildEntries(spec: PackSpec, onProgress?: (msg: string) => void): Promise<TarEntry[]> {
  const entries: TarEntry[] = [json("manifest.json", manifest(spec)), ...emojiEntries(spec)];

  for (const [key, clip] of Object.entries(spec.letters)) entries.push({ path: `content/letters/${key}.wav`, data: encodeWav(clip) });
  for (const p of spec.phrases) entries.push({ path: `content/voice/${voiceClipFilename(p.text)}`, data: encodeWav(p.clip) });

  for (const pic of spec.pictures) {
    entries.push(json(`content/pictures/${pic.name}.json`, { name: pic.name, ops: pic.ops }));
    if (pic.png) entries.push({ path: `content/pictures/${pic.name}.png`, data: pic.png });
  }

  for (const inst of spec.instruments) {
    entries.push(json(`content/instruments/${inst.name}.json`, { name: inst.name, base: inst.base, params: inst.params }));
    for (const pitch of SAMPLE_PITCHES) {
      onProgress?.(`Rendering ${inst.name}: ${pitch.note}${pitch.octave}`);
      await yieldToUi();
      const samples = renderNote(inst.base, inst.params, pitch.freq);
      entries.push({ path: `content/${inst.name}/${pitch.file}.wav`, data: encodeWav({ samples, rate: SYNTH_RATE }) });
    }
  }

  for (const room of spec.rooms) {
    if (!ROOM_NAME.test(room.name)) throw new Error(`A room name must be lowercase letters, digits, and dashes: ${room.name}`);
    entries.push(text(`content/rooms/${room.name}.py`, room.source.endsWith("\n") ? room.source : room.source + "\n"));
    if (room.blocks) entries.push(json(`content/rooms/${room.name}.blocks.json`, room.blocks));
  }

  if (spec.theme) entries.push(json("content/theme.json", themeJson(spec.theme)));
  return entries;
}

export async function buildPack(spec: PackSpec, onProgress?: (msg: string) => void): Promise<Blob> {
  const entries = await buildEntries(spec, onProgress);
  onProgress?.("Packing");
  return new Blob([(await gzip(tar(entries))) as BlobPart], { type: "application/gzip" });
}
