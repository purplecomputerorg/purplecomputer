// Builds a .purplepack from a plain description. Everything Purple reads is described
// in studio/PACK_FORMAT.md; this is the one place that knows the file layout.
import exported from "./purple/export.json";
import { type LetterOp, type PaintOp } from "./purple/art";
import { LETTER_FILES, SAMPLE_PITCHES, voiceClipFilename } from "./purple/sounds";
import { SYNTH_RATE, renderNote, type BaseName, type Params } from "./purple/synth";
import { themeJson, type Theme } from "./purple/theme";
import { gzip, tar, type TarEntry } from "./tar";
import { encodeWav, type Clip } from "./wav";
import roomLibrary from "../../../purple_tui/roomkit/purple.py?raw";

// title: the name as the family typed it, which Purple shows as is; name is the file name.
// source: the photo Studio crops from, kept for reopening; Purple never reads it.
export interface PackPicture { name: string; title?: string; ops: PaintOp[]; letters?: LetterOp[]; png?: Uint8Array; source?: Uint8Array }
export interface PackInstrument { name: string; title?: string; base: BaseName; params: Params }
// content/rooms/<name>.py: Python run as a guest (guides/family-rooms.md); the Blockly workspace it came from rides beside it.
export interface PackRoom { name: string; source: string; blocks?: unknown }

export interface PackSpec {
  // The file name without .purplepack.
  name: string;
  // What Purple installs it under, so a pack with the same id replaces it; the file name when missing.
  id?: string;
  // studio.json: how Purple Studio reopens the pack. Purple never reads it.
  studio?: unknown;
  words: { word: string; emoji: string }[];
  synonyms: { alias: string; word: string }[];
  ranked: string[];
  letters: Record<string, Clip>;
  phrases: { text: string; clip: Clip }[];
  pictures: PackPicture[];
  instruments: PackInstrument[];
  rooms: PackRoom[];
  theme: Theme | null;
}

export const PACK_FORMAT: number = exported.pack_format;

const enc = new TextEncoder();
const text = (path: string, body: string): TarEntry => ({ path, data: enc.encode(body) });
const json = (path: string, value: unknown) => text(path, JSON.stringify(value, null, 2) + "\n");

export const slug = (s: string) => s.toLowerCase().replace(/['’]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
// purple is taken: content/rooms/purple.py is the library the pack's rooms run on.
export const ROOM_NAME = /^(?!purple$)[a-z0-9][a-z0-9-]{0,39}$/;
// content.display_name: what Purple shows for a room called `name`.
export const roomTitle = (name: string) =>
  name.replace(/[-_]/g, " ").trim().replace(/[a-zA-Z]+/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase()).slice(0, 24);
export const packId = (spec: Pick<PackSpec, "name">) => slug(spec.name) || "purple";
export const packFilename = (spec: Pick<PackSpec, "name">) => `${packId(spec)}.purplepack`;

export function manifest(spec: Pick<PackSpec, "name" | "id">) {
  return {
    id: spec.id || packId(spec),
    name: spec.name.trim() || packId(spec),
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

export const letterPath = (key: string) => `content/letters/${LETTER_FILES[key] ?? key}.wav`;
export const phrasePath = (text: string) => `content/voice/${voiceClipFilename(text)}`;
export const picturePngPath = (name: string) => `content/pictures/${name}.png`;
export const pictureSourcePath = (name: string) => `studio/pictures/${name}.jpg`;

const yieldToUi =() => new Promise((r) => setTimeout(r, 0));

// Every note of an instrument as WAV files, kept for the last few sounds: Studio rebuilds its live
// pack on each edit, and rendering is most of that work.
const rendered = new Map<string, Uint8Array[]>();
const RENDERED_KEPT = 8;

async function renderInstrument(inst: PackInstrument, onProgress?: (msg: string) => void): Promise<Uint8Array[]> {
  const key = `${inst.base}|${JSON.stringify(inst.params)}`;
  let notes = rendered.get(key);
  if (!notes) {
    notes = [];
    for (const pitch of SAMPLE_PITCHES) {
      onProgress?.(`Rendering ${inst.name}: ${pitch.note}${pitch.octave}`);
      await yieldToUi();
      notes.push(encodeWav({ samples: renderNote(inst.base, inst.params, pitch.freq), rate: SYNTH_RATE }));
    }
    if (rendered.size >= RENDERED_KEPT) rendered.delete(rendered.keys().next().value!);
  }
  rendered.delete(key);
  rendered.set(key, notes);
  return notes;
}

export async function buildEntries(spec: PackSpec, onProgress?: (msg: string) => void): Promise<TarEntry[]> {
  const entries: TarEntry[] = [json("manifest.json", manifest(spec)), ...emojiEntries(spec)];

  for (const [key, clip] of Object.entries(spec.letters)) entries.push({ path: letterPath(key), data: encodeWav(clip) });
  for (const p of spec.phrases) entries.push({ path: phrasePath(p.text), data: encodeWav(p.clip) });

  for (const pic of spec.pictures) {
    entries.push(json(`content/pictures/${pic.name}.json`, { name: pic.title ?? pic.name, ops: pic.ops, ...(pic.letters?.length ? { letters: pic.letters } : {}) }));
    if (pic.png) entries.push({ path: picturePngPath(pic.name), data: pic.png });
    if (pic.source) entries.push({ path: pictureSourcePath(pic.name), data: pic.source });
  }

  for (const inst of spec.instruments) {
    entries.push(json(`content/instruments/${inst.name}.json`, { name: inst.title ?? inst.name, base: inst.base, params: inst.params }));
    const notes = await renderInstrument(inst, onProgress);
    SAMPLE_PITCHES.forEach((pitch, i) => entries.push({ path: `content/${inst.name}/${pitch.file}.wav`, data: notes[i] }));
  }

  // The rooms run on the library they were made with, whichever Purple they land on.
  if (spec.rooms.length) entries.push(text("content/rooms/purple.py", roomLibrary));
  for (const room of spec.rooms) {
    if (!ROOM_NAME.test(room.name)) throw new Error(`A room name must be lowercase letters, digits, and dashes, and not purple: ${room.name}`);
    entries.push(text(`content/rooms/${room.name}.py`, room.source.endsWith("\n") ? room.source : room.source + "\n"));
    if (room.blocks) entries.push(json(`content/rooms/${room.name}.blocks.json`, room.blocks));
  }

  if (spec.theme) entries.push(json("content/theme.json", themeJson(spec.theme)));
  if (spec.studio) entries.push(json("studio.json", spec.studio));
  return entries;
}

export async function buildPack(spec: PackSpec, onProgress?: (msg: string) => void): Promise<Blob> {
  const entries = await buildEntries(spec, onProgress);
  onProgress?.("Packing");
  return new Blob([(await gzip(tar(entries))) as BlobPart], { type: "application/gzip" });
}
