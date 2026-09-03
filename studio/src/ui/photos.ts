import { pictureFromFile } from "../photo";
import { CANVAS_HEIGHT, CANVAS_WIDTH } from "../purple/art";
import { changed, draft } from "../state";
import { clear, h } from "./dom";
import { artFrame } from "./facsimile";

export function photosView(): HTMLElement {
  const list = h("div");
  const status = h("div", { class: "status" });

  const add = async (files: FileList | File[]) => {
    for (const file of files) {
      if (!file.type.startsWith("image/")) continue;
      status.textContent = `Painting ${file.name}…`;
      try {
        draft.pictures.push(await pictureFromFile(file));
      } catch {
        status.textContent = `${file.name} could not be opened as a photo.`;
        continue;
      }
      status.textContent = "";
      changed();
    }
    render();
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
    h("div", { class: "small" }, "Photos stay on this computer."),
    input,
  );

  function render() {
    clear(list);
    for (const pic of draft.pictures) {
      const remove = () => {
        draft.pictures = draft.pictures.filter((p) => p !== pic);
        changed();
        render();
      };
      list.append(
        h(
          "div",
          { class: "card" },
          h("div", { class: "pair" }, h("img", { class: "photo", src: pic.sourceUrl, alt: "" }), artFrame(pic.cells)),
          h(
            "div",
            { class: "row between", style: "margin-top:16px" },
            h("span", { class: "dim small" }, h("span", { class: "mono" }, `content/pictures/${pic.name}.json`), ` · ${pic.cells[0].length} by ${pic.cells.length} cells`),
            h("button", { class: "linkbtn dim", onclick: remove }, "Remove"),
          ),
        ),
      );
    }
  }
  render();

  return h(
    "section",
    {},
    h("h2", {}, "Your own photos"),
    h("p", { class: "lead" }, `A photo becomes a painting in the Art room: one block of color per cell, ${CANVAS_WIDTH} across and ${CANVAS_HEIGHT} down. Your kid draws on top of it, or over it.`),
    drop,
    status,
    list,
    h("div", { class: "note" }, h("strong", {}, "What Purple does with this today: "), "nothing yet. The Art room can only show a picture that was built into Purple itself. The pack carries your photo as a paint list in the layout the loader would read once it learns to look there."),
  );
}
