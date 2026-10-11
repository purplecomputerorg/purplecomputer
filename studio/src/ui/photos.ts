import { pictureFromFile } from "../photo";
import { changed, draft } from "../state";
import { h } from "./dom";
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

// Every photo in the pack; the one being looked at is marked.
const photoList = (current: string | null) => draft.pictures.length < 2 && current ? null : h("div", { class: "photo-list" },
  ...draft.pictures.map((p) => h("a", { href: `#photos/${encodeURIComponent(p.name)}`, "aria-current": p.name === current ? "page" : null, title: p.name }, h("img", { src: p.sourceUrl, alt: p.name }))));

const caption = "Purple's Art room with your photo painted on. Type to paint over it.";

export function photosView(item: string | null): View {
  const pic = item ? draft.pictures.find((p) => p.name === item) : null;
  const live = { room: "art", picture: (pic ?? draft.pictures[0])?.name } as const;
  if (!pic) {
    return {
      title: "Photos",
      editor: h(
        "section",
        {},
        h("p", { class: "lead" }, "A photo becomes a painting in the Art room, made of the same squares a kid paints with. They can draw right on top of it."),
        photoList(null),
        dropZone(),
        h("p", { class: "dim small" }, "On Purple, a parent opens it from the parent menu, under Pictures."),
      ),
      live,
      caption,
    };
  }
  const remove = () => {
    draft.pictures = draft.pictures.filter((p) => p !== pic);
    changed();
    location.hash = "#photos";
  };
  return {
    title: pic.name,
    editor: h(
      "section",
      {},
      h("div", { class: "card" }, h("div", { class: "row", style: "gap:24px" }, h("img", { class: "photo", src: pic.sourceUrl, alt: "" }), h("div", {}, h("p", {}, "Painted on the right at the size it will be on Purple."), h("button", { class: "linkbtn dim", onclick: remove }, "Remove this photo")))),
      photoList(pic.name),
      h("h3", {}, "Add another"),
      dropZone(),
    ),
    live,
    caption,
  };
}
