// A pack's own pictures and sounds for its rooms: a photo becomes a PNG no bigger than Purple takes,
// any sound the browser can play becomes the WAV Purple plays.
import { ROOM_FILE_NAME, type RoomFileKind } from "@sdk/pack";
import { decodeToClip, encodeWav } from "../audio";
import { changed, draft, freeName, type RoomFile } from "../state";
import { filePicker, h } from "./dom";

const MAX_SIDE = 1024;  // pack_manager.IMAGE_MAX_SIDE

async function png(file: Blob): Promise<Uint8Array> {
  const bitmap = await createImageBitmap(file);
  const k = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = new OffscreenCanvas(Math.max(1, Math.round(bitmap.width * k)), Math.max(1, Math.round(bitmap.height * k)));
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return new Uint8Array(await (await canvas.convertToBlob({ type: "image/png" })).arrayBuffer());
}

const wav = async (file: Blob) => encodeWav(await decodeToClip(file));

export function addRoomData(kind: RoomFileKind, text: string, data: Uint8Array): RoomFile {
  const name = freeName(text, (n) => draft.roomFiles.some((f) => f.kind === kind && f.name === n), kind === "images" ? "picture" : "sound");
  const added: RoomFile = { kind, name, data, kept: true };
  draft.roomFiles.push(added);
  changed();
  return added;
}

export const addRoomFile = async (kind: RoomFileKind, file: File): Promise<RoomFile> =>
  addRoomData(kind, file.name.replace(/\.[^.]+$/, ""), await (kind === "images" ? png : wav)(file));

// A new name everywhere the pack's rooms use the old one: their Python and their rules.
function rename(f: RoomFile, text: string) {
  const name = freeName(text, (n) => draft.roomFiles.some((x) => x !== f && x.kind === f.kind && x.name === n), f.name);
  if (name === f.name || !ROOM_FILE_NAME.test(name)) return;
  const [before, after] = [call(f), call({ ...f, name })];
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

const face = (f: RoomFile) => f.kind === "images"
  ? h("img", { src: URL.createObjectURL(new Blob([f.data as BlobPart], { type: "image/png" })), alt: "" })
  : h("span", { class: "sound-face" }, "🔊");

// The pack's pictures and sounds as a tray: clicking one gives a room its call (into the Python when
// onPick takes it, else onto the clipboard), and each can be renamed or thrown away.
export function roomFilesBox(onPick?: (call: string) => boolean): HTMLElement & { refresh: () => void } {
  const box = h("div", {});
  const status = h("span", { class: "dim small" });
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
        h("button", { type: "button", class: "linkbtn small", title: "Rename", onclick: () => { const t = prompt("A new name", f.name); if (t) { rename(f, t); render(); } } }, f.name),
        h("button", { type: "button", class: "drop", title: `Throw away ${f.name}`, "aria-label": `Throw away ${f.name}`, onclick: () => drop(f) }, "×"))))
      : h("p", { class: "dim small" }, "A photo of your pet, a voice saying hello: add them here, and any room in this Purple Pack can use them."),
    h("p", { class: "row" }, filePicker("image/*", add("images"), "Add a picture"), filePicker("audio/*", add("sounds"), "Add a sound"), status),
  ));
  const add = (kind: RoomFileKind) => async (file: File) => {
    try {
      await addRoomFile(kind, file);
      status.textContent = "";
      render();
    } catch (e) {
      status.textContent = ` That file didn't open. (Technical: ${e instanceof Error ? e.message : String(e)})`;
    }
  };
  const drop = (f: RoomFile) => {
    draft.roomFiles = draft.roomFiles.filter((x) => x !== f);
    changed();
    render();
  };
  render();
  return Object.assign(box, { refresh: render });
}

const call = (f: RoomFile) => (f.kind === "images" ? `picture("${f.name}")` : `sound("${f.name}")`);
