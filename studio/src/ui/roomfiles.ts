// A pack's own pictures and sounds for its rooms: a photo becomes a PNG no bigger than Purple takes,
// any sound the browser can play becomes the WAV Purple plays.
import type { RoomFileKind } from "@sdk/pack";
import { decodeToClip, encodeWav } from "../audio";
import { changed, draft, freeName, type RoomFile } from "../state";
import { filePicker, h } from "./dom";
import { tryChip } from "./trybar";

const MAX_SIDE = 1024;  // pack_manager.IMAGE_MAX_SIDE

async function png(file: Blob): Promise<Uint8Array> {
  const bitmap = await createImageBitmap(file);
  const k = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = new OffscreenCanvas(Math.max(1, Math.round(bitmap.width * k)), Math.max(1, Math.round(bitmap.height * k)));
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return new Uint8Array(await (await canvas.convertToBlob({ type: "image/png" })).arrayBuffer());
}

const wav = async (file: Blob) => encodeWav(await decodeToClip(file));

export async function addRoomFile(kind: RoomFileKind, file: File): Promise<RoomFile> {
  const name = freeName(file.name.replace(/\.[^.]+$/, ""), (n) => draft.roomFiles.some((f) => f.kind === kind && f.name === n), kind === "images" ? "picture" : "sound");
  const added: RoomFile = { kind, name, data: await (kind === "images" ? png : wav)(file), kept: true };
  draft.roomFiles.push(added);
  changed();
  return added;
}

// What's there, how a room uses each one, and adding more.
export function roomFilesBox(): HTMLElement {
  const box = h("div", {});
  const status = h("span", { class: "dim small" });
  const render = () => box.replaceChildren(h("div", {},
    h("h3", {}, "Pictures and sounds for your rooms"),
    h("p", { class: "dim small" }, "A photo of your pet, a voice saying hello: add them here, and any room in this Purple Pack can use them. Press ▶ Play from the start to see a new one."),
    draft.roomFiles.length ? h("div", { class: "row" }, ...draft.roomFiles.map((f) =>
      tryChip(h("span", { class: "btn secondary small mono" }, call(f)), f.name, () => drop(f)))) : null,
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
  return box;
}

const call = (f: RoomFile) => (f.kind === "images" ? `picture("${f.name}")` : `sound("${f.name}")`);
