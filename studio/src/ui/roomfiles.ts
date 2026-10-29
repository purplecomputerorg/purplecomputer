// A pack's own pictures and sounds for its rooms: a photo becomes a PNG no bigger than Purple takes,
// any sound the browser can play becomes the WAV Purple plays.
import { ROOM_FILE_NAME, type RoomFileKind } from "@sdk/pack";
import { audioContext, decodeToClip, encodeWav, playBuffer } from "../audio";
import { PICTURE_KINDS, bitmapFromSrc, dataUrl, pictureFailure } from "../photo";
import { roomFileOf, shelf, shelve, shelveFile, type Shelved } from "../shelf";
import { changed, draft, freeName, names, type Made, type RoomDraft, type RoomFile } from "../state";
import { askText, filePicker, h } from "./dom";
import { recordButton } from "./record";

const MAX_SIDE = 1024;  // pack_manager.IMAGE_MAX_SIDE
const MAX_BYTES = 1024 * 1024;  // pack_manager.IMAGE_MAX_BYTES

// A photo as PNG can pass MAX_BYTES even at MAX_SIDE, and Purple refuses a pack holding one, so it shrinks until it fits.
async function png(src: string): Promise<Uint8Array> {
  const bitmap = await bitmapFromSrc(src);
  const long = Math.max(bitmap.width, bitmap.height);
  for (let side = Math.min(MAX_SIDE, long); ; side = Math.floor(side * 0.8)) {
    const canvas = new OffscreenCanvas(Math.max(1, Math.round(bitmap.width * side / long)), Math.max(1, Math.round(bitmap.height * side / long)));
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const data = new Uint8Array(await (await canvas.convertToBlob({ type: "image/png" })).arrayBuffer());
    if (data.length <= MAX_BYTES || side < 64) return data;
  }
}

const wav = async (file: Blob) => encodeWav(await decodeToClip(file));

const sameData = (a: Uint8Array, b: Uint8Array) => a.length === b.length && a.every((x, i) => x === b[i]);

// The very same picture or sound again is the one the pack already has.
export function addRoomData(kind: RoomFileKind, text: string, data: Uint8Array, shelfId?: string): RoomFile {
  const same = draft.roomFiles.find((f) => f.kind === kind && sameData(f.data, data));
  if (same) return Object.assign(same, { shelfId: same.shelfId ?? shelfId });
  const name = freeName(text, (n) => draft.roomFiles.some((f) => f.kind === kind && f.name === n), kind === "images" ? "picture" : "sound");
  const added: RoomFile = { kind, name, data, kept: true, shelfId };
  draft.roomFiles.push(added);
  changed();
  return added;
}

// Any picture, as one of the pack's own.
const addRoomPicture = async (text: string, src: string, shelfId?: string) => addRoomData("images", text, await png(src), shelfId);

// A picture from the shelf, for the pack's rooms: the copy they already have, or a new one.
export async function roomFileFor(item: Shelved): Promise<RoomFile> {
  return roomFileOf(item) ?? addRoomPicture(item.name, item.src, item.id);
}

// One of Studio's photos, on the family's shelf like their own, so it's one picture wherever it's used.
export async function addOurPicture(text: string, src: string): Promise<RoomFile> {
  return roomFileFor(shelve(await dataUrl(await (await fetch(src)).blob()), text));
}

// A new photo goes on the shelf too, so any pack can use it again.
export async function addRoomFile(kind: RoomFileKind, file: File): Promise<RoomFile> {
  return kind === "images" ? roomFileFor(await shelveFile(file)) : addRoomData(kind, file.name.replace(/\.[^.]+$/, ""), await wav(file));
}

// The shelf's pictures this pack's rooms don't have yet.
export const shelfOnly = () => shelf.filter((s) => !roomFileOf(s));
export const shelfThumb = (s: Shelved) => h("img", { src: s.src, alt: s.name });

// A new name everywhere the pack uses the old one: Play's words, and its rooms' Python and rules.
export function renameRoomFile(f: RoomFile, text: string) {
  const name = freeName(text, (n) => draft.roomFiles.some((x) => x !== f && x.kind === f.kind && x.name === n), f.name);
  if (name === f.name || !ROOM_FILE_NAME.test(name)) return;
  const [before, after] = [call(f), call({ ...f, name })];
  if (f.kind === "images") for (const w of draft.words) if (w.emoji === f.name) w.emoji = name;
  for (const r of draft.rooms) {
    r.source = r.source.replaceAll(before.slice(0, -1), after.slice(0, -1));
    if (r.made?.kind !== "rules") continue;
    for (const a of r.made.rules.flatMap((rule) => rule.actions)) {
      if (a.kind === "sound" && f.kind === "sounds" && a.name === f.name) a.name = name;
      if ((a.kind === "show" || a.kind === "put") && f.kind === "images" && a.thing.kind === "picture" && a.thing.value === f.name) a.thing.value = name;
    }
  }
  f.name = name;
  changed();
}

// The sounds a form's room plays, read from the form: its Python catches up a moment later, and quotes a word that shares a recording's name.
function soundsIn(made: Made): string[] {
  if (made.kind === "rules") return made.rules.flatMap((r) => r.actions).flatMap((a) => (a.kind === "sound" ? [a.name] : []));
  return made.kind === "soundboard" ? [...made.data.rows, made.data.other].flatMap((s) => [s.voice ?? "", s.note]) : [];
}
const roomNames = (r: RoomDraft, name: string) => (r.made ? soundsIn(r.made).includes(name) : names(r.source, name));

// A recording no room uses any more, gone, so a key recorded again doesn't leave its last take behind.
export function dropUnusedSound(name: string) {
  if (draft.rooms.some((r) => roomNames(r, name))) return;
  draft.roomFiles = draft.roomFiles.filter((f) => f.kind !== "sounds" || f.name !== name);
  changed();
}

export const roomPictures = () => draft.roomFiles.filter((f) => f.kind === "images");
const urls = new WeakMap<RoomFile, string>();
const thumb = (f: RoomFile) => {
  if (!urls.has(f)) urls.set(f, URL.createObjectURL(new Blob([f.data as BlobPart], { type: "image/png" })));
  return h("img", { src: urls.get(f), alt: f.name });
};
// One of the pack's pictures by name, as a thumbnail; null when the pack has none by that name.
export function roomPicture(name: string): HTMLImageElement | null {
  const f = roomPictures().find((p) => p.name === name);
  return f ? thumb(f) : null;
}

const face = (f: RoomFile) => (f.kind === "images" ? thumb(f) : h("span", { class: "sound-face" }, "🔊"));

// Plays one of the pack's sounds by name; false when the pack has none by that name.
export function hearRoomSound(name: string): boolean {
  const f = draft.roomFiles.find((x) => x.kind === "sounds" && x.name === name);
  if (f) void audioContext().decodeAudioData(f.data.slice().buffer).then((b) => playBuffer(b));
  return !!f;
}

// The pack's pictures and sounds as a tray: clicking one gives a room its call (into the Python when
// onPick takes it, else onto the clipboard), and each can be renamed or thrown away. onChange: the files changed, so pickers redraw.
export function roomFilesBox(onPick?: (call: string) => boolean, onChange = () => {}): HTMLElement & { refresh: () => void } {
  const box = h("div", {});
  const status = h("span", { class: "dim small" });
  const say = (text: string) => void (status.textContent = text);
  const changedHere = () => { render(); onChange(); };
  const pick = async (f: RoomFile) => {
    if (onPick?.(call(f))) return void (status.textContent = "");
    await navigator.clipboard?.writeText(call(f)).catch(() => {});
    status.textContent = `Copied ${call(f)}. The forms and Knobs list it in their pickers.`;
  };
  const render = () => box.replaceChildren(h("div", { class: "tray" },
    h("h3", {}, "Pictures and sounds for your rooms"),
    draft.roomFiles.length
      ? h("div", { class: "photo-list" }, ...draft.roomFiles.map((f) => h("div", { class: "try-chip tray-item" },
        h("button", { type: "button", title: `Use ${call(f)}`, onclick: () => pick(f) }, face(f)),
        f.kind === "sounds" ? h("button", { type: "button", class: "hear", title: `Hear ${f.name}`, "aria-label": `Hear ${f.name}`, onclick: () => hearRoomSound(f.name) }, "▶") : null,
        h("button", { type: "button", class: "linkbtn small", title: "Rename", onclick: async () => { const t = await askText("A new name", f.name, "Rename"); if (t) { renameRoomFile(f, t); changedHere(); } } }, f.name),
        h("button", { type: "button", class: "drop", title: `Throw away ${f.name}`, "aria-label": `Throw away ${f.name}`, onclick: () => drop(f) }, "×"))))
      : h("p", { class: "dim small" }, "A photo of your pet, a voice saying hello: add them here, and any room in this Purple Pack can use them."),
    shelfOnly().length ? h("div", {}, h("p", { class: "dim small" }, "From your pictures:"),
      h("div", { class: "photo-list" }, ...shelfOnly().map((s) => h("div", { class: "try-chip tray-item" },
        h("button", { type: "button", title: `Add ${s.name} for your rooms`, onclick: () => roomFileFor(s).then(changedHere, failed("images")) }, shelfThumb(s)),
        h("span", { class: "dim" }, s.name))))) : null,
    h("p", { class: "row" }, filePicker("image/*", add("images"), "Add a picture", "btn secondary"), filePicker("audio/*", add("sounds"), "Add a sound", "btn secondary"),
      recordButton((clip) => { addRoomData("sounds", "recording", encodeWav(clip)); changedHere(); }, say), status),
    h("p", { class: "dim small" }, `Pictures: ${PICTURE_KINDS}. Studio makes each one small enough for Purple.`),
  ));
  const failed = (kind: RoomFileKind) => (e: unknown) => (status.textContent = kind === "images" ? ` ${pictureFailure(e)}`
    : ` That sound didn't open. (Technical: ${e instanceof Error ? e.message : String(e)})`);
  const add = (kind: RoomFileKind) => async (file: File) => {
    try {
      await addRoomFile(kind, file);
      say("");
      changedHere();
    } catch (e) {
      failed(kind)(e);
    }
  };
  const drop = (f: RoomFile) => {
    draft.roomFiles = draft.roomFiles.filter((x) => x !== f);
    changed();
    changedHere();
  };
  render();
  return Object.assign(box, { refresh: render });
}

const call = (f: RoomFile) => (f.kind === "images" ? `picture("${f.name}")` : `sound("${f.name}")`);
