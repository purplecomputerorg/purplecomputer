import { EXAMPLES, examplePicture, pictureFromFile, type Example } from "../photo";
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
        status.textContent = `${file.name} could not be opened as a picture.`;
      }
    }
    changed();
    if (last) goTo(last);
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
    h("div", {}, "Drop a picture here, or click to choose one."),
    h("div", { class: "small" }, "A photo, a scan of a drawing, anything. It stays on this computer."),
    input,
  );
  return h("div", {}, drop, status);
}

const goTo = (name: string) => (location.hash = `#pictures/${encodeURIComponent(name)}`);

// A row of pictures to pick from; the one being looked at is marked.
const thumbs = (items: { name: string; src: string }[], current: string | null) => h("div", { class: "photo-list" },
  ...items.map((p) => h("a", { href: `#pictures/${encodeURIComponent(p.name)}`, "aria-current": p.name === current ? "page" : null, title: p.name }, h("img", { src: p.src, alt: p.name }))));

const family = (current: string | null) => thumbs(draft.pictures.map((p) => ({ name: p.name, src: p.sourceUrl })), current);

// Studio's examples the family hasn't put on their Purple; until they have a picture, the first is on the screen.
function examples(current: string | null): HTMLElement | null {
  const left = EXAMPLES.filter((e) => !draft.pictures.some((p) => p.name === e.name));
  if (!left.length) return null;
  const note = !draft.pictures.length && !current ? "The first one is on the screen now. " : "";
  return h("div", {}, h("h3", {}, "Or try one of ours"),
    h("p", { class: "dim small" }, `${note}Click one to see it on Purple. It goes on your Purple only if you add it.`), thumbs(left, current));
}

const card = (src: string, alt: string, ...body: (Node | null)[]) =>
  h("div", { class: "card" }, h("div", { class: "row", style: "gap:24px" }, h("img", { class: "photo", src, alt }), h("div", { style: "flex:1;min-width:200px" }, ...body)));

function exampleView(ex: Example): HTMLElement {
  const keep = async () => {
    draft.pictures = [...draft.pictures, await examplePicture(ex)];
    changed();
    goTo(ex.name);
  };
  return h("section", {},
    card(ex.src, ex.alt, h("p", {}, "One of Studio's examples, painted on the screen at the size it will be on Purple."),
      ex.credit ? h("p", { class: "dim small" }, ex.credit) : null,
      h("button", { class: "btn", onclick: keep }, "Put this one on Purple")),
    examples(ex.name),
    h("h3", {}, "Or add your own"),
    dropZone());
}

const caption = "Purple's Art room with the picture painted on. Type to paint over it.";

export function picturesView(item: string | null): View {
  const pic = item ? draft.pictures.find((p) => p.name === item) : null;
  const ex = !pic && item ? EXAMPLES.find((e) => e.name === item) : null;
  const live = { room: "art", picture: (pic ?? ex ?? draft.pictures[0] ?? EXAMPLES[0]).name } as const;
  const view = (title: string, editor: HTMLElement): View => ({ title, editor, live, caption });
  if (ex) return view(ex.name, exampleView(ex));
  if (!pic) {
    return view("Pictures", h(
      "section",
      {},
      h("p", { class: "lead" }, "A photo, or a drawing your kid made, becomes a painting in the Art room, made of the same squares a kid paints with. They can draw right on top of it."),
      draft.pictures.length ? family(null) : null,
      dropZone(),
      examples(null),
      h("p", { class: "dim small" }, "On Purple, it waits in the Art room under Open (Esc, then O), next to your kid's saved work."),
    ));
  }
  const remove = () => {
    draft.pictures = draft.pictures.filter((p) => p !== pic);
    changed();
    location.hash = "#pictures";
  };
  return view(pic.name, h(
    "section",
    {},
    card(pic.sourceUrl, "", h("p", {}, "Painted on the screen at the size it will be on Purple."), h("button", { class: "linkbtn dim", onclick: remove }, "Remove this picture")),
    draft.pictures.length > 1 ? family(pic.name) : null,
    h("h3", {}, "Add another"),
    dropZone(),
    examples(null),
  ));
}
