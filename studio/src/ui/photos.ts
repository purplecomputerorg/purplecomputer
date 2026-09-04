import { pictureFromFile } from "../photo";
import { CANVAS_HEIGHT, CANVAS_WIDTH } from "../purple/art";
import { changed, draft, DEFAULT_THEME } from "../state";
import { h } from "./dom";
import { artFrame } from "./facsimile";
import type { View } from "./view";

function dropZone(): HTMLElement {
  const status = h("div", { class: "status" });
  const add = async (files: FileList | File[]) => {
    let last: string | null = null;
    for (const file of files) {
      if (!file.type.startsWith("image/")) continue;
      status.textContent = `Painting ${file.name}…`;
      try {
        const pic = await pictureFromFile(file);
        draft.pictures = draft.pictures.filter((p) => p.name !== pic.name);
        draft.pictures.push(pic);
        last = pic.name;
      } catch {
        status.textContent = `${file.name} could not be opened as a photo.`;
      }
    }
    changed();
    if (last) location.hash = `#photos/${encodeURIComponent(last)}`;
  };
  const input = h("input", { type: "file", accept: "image/*", multiple: true, onchange: () => input.files && add(input.files) });
  const drop = h(
    "label",
    {
      class: "drop",
      ondragover: (e: DragEvent) => { e.preventDefault(); drop.classList.add("over"); },
      ondragleave: () => drop.classList.remove("over"),
      ondrop: (e: DragEvent) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer && add(e.dataTransfer.files); },
    },
    h("div", {}, "Drop a photo here, or click to choose one."),
    h("div", { class: "small" }, "It stays on this computer."),
    input,
  );
  return h("div", {}, drop, status);
}

const note = () => h("div", { class: "note" }, h("strong", {}, "What Purple does with this: "), "the parent menu gets a Pictures entry listing each one. Choosing a picture paints it onto the Art room canvas, where the kid can draw over it or clear it, the same as any drawing.");

export function photosView(item: string | null): View {
  const pic = item ? draft.pictures.find((p) => p.name === item) : null;
  const theme = draft.theme ?? DEFAULT_THEME;
  if (!pic) {
    return {
      title: "Photos",
      path: "content/pictures/<name>.json",
      tag: "real",
      editor: h(
        "section",
        {},
        h("p", { class: "lead" }, `A photo becomes a painting in the Art room: one block of color per cell, ${CANVAS_WIDTH} across and ${CANVAS_HEIGHT} down. Your kid draws on top of it, or over it.`),
        dropZone(),
        note(),
      ),
      stage: () => artFrame(draft.pictures[0]?.cells ?? null, theme),
      caption: draft.pictures.length ? `The Art room with ${draft.pictures[0].name}.` : "The Art room, empty. Drop a photo to see it painted here.",
    };
  }
  const remove = () => {
    draft.pictures = draft.pictures.filter((p) => p !== pic);
    changed();
    location.hash = "#photos";
  };
  return {
    title: pic.name,
    path: `content/pictures/${pic.name}.json  ·  ${pic.name}.png`,
    tag: "real",
    editor: h(
      "section",
      {},
      h("div", { class: "card" }, h("div", { class: "row", style: "gap:24px" }, h("img", { class: "photo", src: pic.sourceUrl, alt: "" }), h("div", {}, h("p", {}, `${pic.cells[0].length} by ${pic.cells.length} cells, centered on the canvas. ${pic.ops.length} paint strokes.`), h("p", { class: "dim small" }, "Every cell is one keypress's worth of paint, so a kid can erase or draw over any part of it."), h("button", { class: "linkbtn dim", onclick: remove }, "Remove this photo")))),
      h("h3", {}, "Add another"),
      dropZone(),
      note(),
    ),
    stage: () => artFrame(pic.cells, theme),
    caption: `The Art room with ${pic.name} painted at real size.`,
  };
}
