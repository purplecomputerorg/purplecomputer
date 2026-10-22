// The family's pictures on this computer, apart from any one Purple Pack: a picture goes in the pack only
// once Art or a room uses it. Best effort, like the draft (saved.ts): a downloaded pack, reopened, brings its pictures back.
import { recallShelf, rememberShelf } from "./saved";
import { changed, draft, freeName, isTheirs, names, titleOf, type Draft, type RoomFile } from "./state";
import { PICTURE_KINDS, PICTURE_MAX_MB, PictureProblem, bitmapFromSrc, dataUrl, type Picture } from "./photo";

// src: the photo as a data URL, as the family added it. Saved in the browser, so a field added here must be optional.
export interface Shelved { id: string; name: string; src: string }

export const shelf: Shelved[] = [];

export async function loadShelf() {
  shelf.splice(0, shelf.length, ...await recallShelf());
}

function saved() {
  void rememberShelf(shelf);
  changed();
}

// Clear of Art's pictures not from the shelf (one of ours, made the family's), since a page is found by either name.
export const shelfName = (text: string, except?: Shelved) => freeName(text, (n) =>
  shelf.some((s) => s !== except && s.name === n) || draft.pictures.some((p) => !p.shelfId && p.name === n), "picture");

// The same picture again (by id, or the very same photo) is the one already on the shelf.
export function shelve(src: string, text: string, id?: string): Shelved {
  const found = shelf.find((s) => s.id === id || s.src === src);
  if (found) return found;
  const item = { id: id ?? crypto.randomUUID(), name: shelfName(text), src };
  shelf.push(item);
  saved();
  return item;
}

// A file the family picked, on the shelf, once it's a picture Studio can open.
export async function shelveFile(file: File): Promise<Shelved> {
  const mb = file.size / 1024 / 1024;
  if (mb > PICTURE_MAX_MB) throw new PictureProblem(`${file.name} is ${Math.ceil(mb)} MB. Studio takes pictures up to ${PICTURE_MAX_MB} MB, so try a smaller copy.`);
  const src = await dataUrl(file);
  await bitmapFromSrc(src).catch(() => {
    throw new PictureProblem(`${file.name} didn't open. Studio takes ${PICTURE_KINDS}; save an iPhone photo (HEIC) as JPG first.`);
  });
  return shelve(src, file.name.replace(/\.[^.]+$/, ""));
}

export function unshelve(item: Shelved) {
  shelf.splice(shelf.indexOf(item), 1);
  saved();
}

export function renameShelved(item: Shelved, text: string) {
  item.name = shelfName(text, item);
  saved();
}

// Where this pack uses it: Art's copy, and the rooms' copy.
export const artOf = (item: Shelved): Picture | undefined => draft.pictures.find((p) => p.shelfId === item.id);
export const roomFileOf = (item: Shelved): RoomFile | undefined => draft.roomFiles.find((f) => f.kind === "images" && f.shelfId === item.id);

// What a parent reads under "Used in": Art once it's added, and each room naming its picture.
export function usedIn(item: Shelved): string[] {
  const art = artOf(item);
  const file = roomFileOf(item);
  const rooms = file ? draft.rooms.filter((r) => names(r.source, file.name)) : [];
  const words = file && draft.words.some((w) => w.emoji === file.name) ? ["Play"] : [];
  return [...(art?.kept ? ["Art"] : []), ...words, ...rooms.map((r) => `the ${titleOf(r)} room`)];
}

export function removeFromPack(item: Shelved) {
  draft.pictures = draft.pictures.filter((p) => p.shelfId !== item.id);
  draft.roomFiles = draft.roomFiles.filter((f) => f.shelfId !== item.id);
  changed();
}

const pngUrl = (data: Uint8Array) => `data:image/png;base64,${btoa(Array.from(data, (b) => String.fromCharCode(b)).join(""))}`;

// A reopened or recalled draft's pictures go on the shelf, each tied to the one it came from.
export function shelveDraft(d: Draft) {
  for (const p of d.pictures.filter((p) => isTheirs(p) && p.sourceUrl.startsWith("data:"))) p.shelfId = shelve(p.sourceUrl, titleOf(p), p.shelfId).id;
  for (const f of d.roomFiles.filter((f) => f.kind === "images")) f.shelfId = shelve(pngUrl(f.data), f.name, f.shelfId).id;
}
