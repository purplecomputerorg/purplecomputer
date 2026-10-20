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
// notes: its WAVs already rendered, in SAMPLE_PITCHES order (Studio renders them off the page).
export interface PackInstrument { name: string; title?: string; base: BaseName; params: Params; notes?: Uint8Array[] }
// content/rooms/<name>.py: Python run as a guest (guides/family-rooms.md); the Studio rules or form it was made from ride beside it.
export interface PackRoom { name: string; source: string; made?: unknown }
// content/images/<name>.png and content/sounds/<name>.wav: what rooms draw with picture() and play with sound().
export type RoomFileKind = "images" | "sounds";
export interface PackRoomFile { kind: RoomFileKind; name: string; data: Uint8Array }
// content/room-voice/<phrase>.wav: a line the pack's rooms say (fixedSays), spoken ahead of time.
export interface PackRoomLine { text: string; clip: Clip }

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
  roomFiles?: PackRoomFile[];
  roomVoice?: PackRoomLine[];
  theme: Theme | null;
}

export const PACK_FORMAT: number = exported.pack_format;

const enc = new TextEncoder();
const text = (path: string, body: string): TarEntry => ({ path, data: enc.encode(body) });
const json = (path: string, value: unknown) => text(path, JSON.stringify(value, null, 2) + "\n");

export const slug = (s: string) => s.toLowerCase().replace(/['’]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
// purple is taken: content/rooms/purple.py is the library the pack's rooms run on.
export const ROOM_NAME = /^(?!purple$)[a-z0-9][a-z0-9-]{0,39}$/;
// content.ASSET_NAME: a room picture's or sound's name.
export const ROOM_FILE_NAME = /^[a-z0-9][a-z0-9_-]{0,39}$/;
export const roomFilePath = (f: Pick<PackRoomFile, "kind" | "name">) => `content/${f.kind}/${f.name}.${f.kind === "images" ? "png" : "wav"}`;
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
export const roomLinePath = (text: string) => `content/room-voice/${voiceClipFilename(text)}`;
export const picturePngPath = (name: string) => `content/pictures/${name}.png`;
export const pictureSourcePath = (name: string) => `studio/pictures/${name}.jpg`;

const yieldToUi =() => new Promise((r) => setTimeout(r, 0));

// Every note of an instrument as WAV files, in SAMPLE_PITCHES order.
async function renderNotes(inst: PackInstrument, onProgress?: (msg: string) => void): Promise<Uint8Array[]> {
  const notes = [];
  for (const pitch of SAMPLE_PITCHES) {
    onProgress?.(`Rendering ${inst.name}: ${pitch.note}${pitch.octave}`);
    await yieldToUi();
    notes.push(encodeWav({ samples: renderNote(inst.base, inst.params, pitch.freq), rate: SYNTH_RATE }));
  }
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
    const notes = inst.notes ?? (await renderNotes(inst, onProgress));
    SAMPLE_PITCHES.forEach((pitch, i) => entries.push({ path: `content/${inst.name}/${pitch.file}.wav`, data: notes[i] }));
  }

  // The rooms run on the library they were made with, whichever Purple they land on.
  if (spec.rooms.length) entries.push(text("content/rooms/purple.py", roomLibrary));
  for (const room of spec.rooms) {
    if (!ROOM_NAME.test(room.name)) throw new Error(`A room name must be lowercase letters, digits, and dashes, and not purple: ${room.name}`);
    entries.push(text(`content/rooms/${room.name}.py`, room.source.endsWith("\n") ? room.source : room.source + "\n"));
    if (room.made) entries.push(json(`content/rooms/${room.name}.studio.json`, room.made));
  }
  for (const f of spec.roomFiles ?? []) entries.push({ path: roomFilePath(f), data: f.data });
  for (const line of spec.roomVoice ?? []) entries.push({ path: roomLinePath(line.text), data: encodeWav(line.clip) });

  if (spec.theme) entries.push(json("content/theme.json", themeJson(spec.theme)));
  if (spec.studio) entries.push(json("studio.json", spec.studio));
  return entries;
}

export async function buildPack(spec: PackSpec, onProgress?: (msg: string) => void): Promise<Blob> {
  const entries = await buildEntries(spec, onProgress);
  onProgress?.("Packing");
  return new Blob([(await gzip(tar(entries))) as BlobPart], { type: "application/gzip" });
}
