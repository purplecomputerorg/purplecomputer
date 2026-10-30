// The app's draft, turned into the plain spec the SDK builds a pack from, and a pack turned back into a draft.
import { buildEntries, formatOf, letterPath, skippedBy, packBlob, packFilename as filename, phrasePath, pictureSourcePath, ROOM_FILE_NAME, ROOM_NAME, roomFilePath, type PackSkipped, type PackSpec, type RoomFileKind } from "@sdk/pack";
import { isCoreRanked } from "@sdk/purple/core";
import { gunzip, untar, type TarEntry } from "@sdk/tar";
import { decodeWav } from "@sdk/wav";
import type { PackFiles } from "./live/boot";
import { instrumentNotes } from "./notes";
import { roomVoice } from "./roomvoice";
import { dataUrl, onScreen, previewPng, refit, sourceJpeg, type Crop, type Words } from "./photo";
import { roomIcon } from "./examples";
import { draft, emptyDraft, madeOf, type Draft, type Keepable, type RoomDraft, type RoomFile } from "./state";

export { manifest } from "@sdk/pack";

// studio.json: what reopening needs beyond the files Purple reads. Clips are read back from the pack.
// A pack can be months old: a new field gets its value in NO_SAVED, and a field that changes meaning bumps STUDIO_FORMAT.
const STUDIO_FORMAT = 1;
interface Saved extends Pick<PackSpec, "name" | "words" | "synonyms" | "ranked" | "instruments" | "rooms" | "theme"> {
  format: number;
  letters: string[];
  phrases: string[];
  pictures: { name: string; title?: string; cells: string[][]; crop?: Crop; words?: Words; shelfId?: string }[];
  // Each room picture's shelf id by name, so reopening on this computer finds the same pictures.
  roomShelf?: Record<string, string>;
}
const NO_SAVED: Saved = { format: STUDIO_FORMAT, name: "", words: [], synonyms: [], ranked: [], instruments: [], rooms: [], theme: null, letters: [], phrases: [], pictures: [] };

// The download holds what the family added; Studio's own Purple also plays what they're trying.
export async function packSpec(d: Draft = draft, trying = false, onProgress?: (msg: string) => void): Promise<PackSpec> {
  const ok = (x: Keepable) => trying || !!x.kept;
  const words = d.words.filter(ok);
  const added = d.pictures.filter(ok);
  // Only the download keeps the photos; Studio's own Purple never reopens a pack.
  const sources = trying ? [] : await Promise.all(added.map(sourceJpeg));
  const pictures = await Promise.all(added.map(async (p, i) => ({ name: p.name, title: p.title, ...onScreen(p), png: await previewPng(onScreen(p)), source: sources[i]?.jpg })));
  // A family's own words come first in autocomplete, after the words Purple already ranks.
  const ranked = [...new Set([...d.ranked, ...words.map((w) => w.word).filter((w) => !isCoreRanked(w))])];
  const letters = Object.fromEntries(Object.entries(d.letters).filter(([, l]) => ok(l)).map(([k, l]) => [k, l.clip]));
  const phrases = d.phrases.filter(ok);
  const synonyms = d.synonyms.filter(ok);
  const instruments = d.instruments.filter(ok);
  const rooms = d.rooms.filter(ok).map((r) => ({ name: r.name, source: r.source, made: r.made, icon: roomIcon(r) }));
  const roomFiles = d.roomFiles.filter(ok);
  const theme = ok(d.colors) ? d.theme : null;
  const studio: Saved = {
    format: STUDIO_FORMAT, name: d.name, words, synonyms, ranked: d.ranked, instruments, rooms, theme,
    letters: Object.keys(letters), phrases: phrases.map((p) => p.text),
    pictures: added.map((p, i) => ({ name: p.name, title: p.title, cells: p.cells, words: p.words, crop: sources[i]?.crop, shelfId: p.shelfId })),
    roomShelf: Object.fromEntries(roomFiles.flatMap((f) => (f.shelfId ? [[f.name, f.shelfId]] : []))),
  };
  const rendered = await Promise.all(instruments.map(async (i) => ({ ...i, notes: await instrumentNotes(i) })));
  // The preview opens the room being tried from this pack's files too, added or not.
  const voiced = await roomVoice(trying ? draft.rooms : rooms, !trying, onProgress);
  return { id: d.id, name: d.name, pictures, words, ranked, letters, phrases, synonyms, instruments: rendered, rooms, roomFiles, roomVoice: voiced, theme, studio };
}

// format: the pack format it needs (studio/pack_formats.json), which says how new a Purple it needs; skipped: what older ones leave out.
export async function buildPack(onProgress?: (msg: string) => void, d: Draft = draft, trying = false): Promise<{ blob: Blob; format: number; skipped: PackSkipped[] }> {
  const entries = await buildEntries(await packSpec(d, trying, onProgress), onProgress);
  onProgress?.("Packing");
  return { blob: await packBlob(entries), format: formatOf(entries), skipped: skippedBy(entries) };
}

export const packFilename = () => filename(draft);

// What Purple last got: a pack's id and files. An empty id means it may have nothing.
export interface Sent { id: string; files: Map<string, Uint8Array> }
const same = (a: Uint8Array | undefined, b: Uint8Array) => a === b || (!!a && a.length === b.length && a.every((v, i) => v === b[i]));

// A pack as Studio's Purple takes it: whole when it's another pack, else only the files that changed.
export function packChanges(id: string, entries: TarEntry[], last: Sent): PackFiles {
  const fresh = id !== last.id;
  return {
    id, fresh,
    files: entries.filter((e) => fresh || !same(last.files.get(e.path), e.data)).map((e) => [e.path, e.data]),
    removed: fresh ? [] : [...last.files.keys()].filter((path) => !entries.some((e) => e.path === path)),
  };
}

const kept = <T extends object>(x: T) => ({ ...x, kept: true });

// What any pack's rooms draw and play, whoever made it.
const roomFiles = (files: Map<string, Uint8Array>): RoomFile[] => (["images", "sounds"] as RoomFileKind[]).flatMap((kind) =>
  [...files].flatMap(([path, data]) => {
    const name = path.slice(`content/${kind}/`.length).replace(/\.\w+$/, "");
    return ROOM_FILE_NAME.test(name) && path === roomFilePath({ kind, name }) ? [kept({ kind, name, data })] : [];
  }));

// The rooms of a pack made without Studio (by hand, or with an AI helper), as Python.
function handMadeRooms(files: Map<string, Uint8Array>): RoomDraft[] {
  const text = (data: Uint8Array) => new TextDecoder().decode(data);
  return [...files].flatMap(([path, data]) => {
    const name = /^content\/rooms\/([^/]+)\.py$/.exec(path)?.[1];
    if (!name || !ROOM_NAME.test(name)) return [];
    const [made, about] = [`${name}.studio.json`, `${name}.json`].map((f) => files.get(`content/rooms/${f}`));
    return [kept({ name, source: text(data), made: made ? madeOf(JSON.parse(text(made))) : null, icon: about && JSON.parse(text(about)).icon })];
  });
}

// A Purple Pack, back as a draft with everything in it added: all of it when Studio made it, and the
// rooms with their pictures and sounds when it was made some other way.
export async function openPack(file: Blob): Promise<Draft> {
  const files = new Map(untar(await gunzip(new Uint8Array(await file.arrayBuffer()))).map((e) => [e.path, e.data]));
  const read = (path: string) => {
    const data = files.get(path);
    if (!data) throw new Error(`${path} is missing`);
    return data;
  };
  const readJson = (path: string) => JSON.parse(new TextDecoder().decode(read(path)));
  const image = (path: string, type: string) => new Blob([read(path) as BlobPart], { type });
  const m = readJson("manifest.json");
  if (!files.has("studio.json")) {
    const rooms = handMadeRooms(files);
    if (!rooms.length) throw new Error("studio.json is missing and there are no rooms");
    return { ...emptyDraft(), id: m.id, name: m.name, rooms, roomFiles: roomFiles(files) };
  }
  const s: Saved = { ...NO_SAVED, ...readJson("studio.json") };
  return {
    ...emptyDraft(),
    id: m.id,
    name: s.name,
    words: s.words.map(kept),
    synonyms: s.synonyms.map(kept),
    ranked: s.ranked,
    instruments: s.instruments.map(kept),
    rooms: s.rooms.map((r) => kept({ name: r.name, source: r.source, made: madeOf(r.made), icon: r.icon })),
    roomFiles: roomFiles(files).map((f) => ({ ...f, shelfId: f.kind === "images" ? s.roomShelf?.[f.name] : undefined })),
    theme: s.theme,
    colors: s.theme ? { kept: true } : {},
    letters: Object.fromEntries(s.letters.map((k) => [k, kept({ clip: decodeWav(read(letterPath(k))) })])),
    phrases: s.phrases.map((text) => kept({ text, clip: decodeWav(read(phrasePath(text))) })),
    pictures: await Promise.all(s.pictures.map(async (p) => {
      const photo = image(pictureSourcePath(p.name), "image/jpeg");
      return refit(kept({ ...p, ops: [], sourceUrl: await dataUrl(photo), bitmap: await createImageBitmap(photo) }));
    })),
  };
}
