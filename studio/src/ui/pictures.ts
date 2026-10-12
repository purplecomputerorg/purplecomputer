import type { RoomSetup } from "../live/boot";
import { EXAMPLES, examplePicture, pictureTitle, pictureFromFile, slug, type Example, type Picture } from "../photo";
import { changed, draft } from "../state";
import { field, h } from "./dom";
import { liveScreen } from "./live";
import type { View } from "./view";

// Trying a picture paints it on Purple's screen and puts it nowhere else; adding it, with a name,
// puts it in the pack. A file the parent chose waits here until they add it or pick another.
let uploaded: Picture | null = null;

const goTo = (name: string) => (location.hash = `#pictures/${encodeURIComponent(name)}`);

function dropZone(): HTMLElement {
  const status = h("div", { class: "status" });
  const add = async (file: File | undefined) => {
    if (!file?.type.startsWith("image/")) return;
    status.textContent = `Painting ${file.name}…`;
    try {
      const pic = await pictureFromFile(file);
      uploaded = pic;
      location.hash = "#pictures/try";
    } catch {
      status.textContent = `${file.name} could not be opened as a picture.`;
    }
  };
  const input = h("input", { type: "file", accept: "image/*", onchange: () => add(input.files?.[0]) });
  const drop = h(
    "label",
    {
      class: "drop",
      ondragover: (e: DragEvent) => { e.preventDefault(); drop.classList.add("over"); },
      ondragleave: () => drop.classList.remove("over"),
      ondrop: (e: DragEvent) => { e.preventDefault(); drop.classList.remove("over"); add(e.dataTransfer?.files[0]); },
    },
    h("div", {}, "Drop a picture here, or click to choose one."),
    h("div", { class: "small" }, "A photo, a scan of a drawing, anything. It stays on this computer."),
    input,
  );
  return h("div", {}, drop, status);
}

// Pictures to pick from, each with its name; the one being looked at is marked.
const thumbs = (items: { href: string; title: string; src: string; current: boolean }[]) => h("div", { class: "photo-list" },
  ...items.map((p) => h("a", { href: p.href, "aria-current": p.current ? "page" : null },
    h("img", { src: p.src, alt: "" }), h("span", {}, p.title))));

function family(current: string | null): HTMLElement {
  return h("div", {}, h("h3", {}, "On your Purple"),
    draft.pictures.length
      ? thumbs(draft.pictures.map((p) => ({ href: `#pictures/${encodeURIComponent(p.name)}`, title: pictureTitle(p), src: p.sourceUrl, current: p.name === current })))
      : h("p", { class: "dim small" }, "Nothing yet. Add your own, or one of ours."));
}

function examples(current: string | null): HTMLElement {
  return h("div", {}, h("h3", {}, "Try one of ours"),
    h("p", { class: "dim small" }, "Click one to see it on the screen. It goes on your Purple only if you add it."),
    thumbs(EXAMPLES.map((e) => ({ href: `#pictures/try/${e.name}`, title: pictureTitle(e), src: e.src, current: e.name === current }))));
}

const more = (current: string | null) => [family(current), h("h3", {}, "Add your own"), dropZone(), examples(current)];

const card = (src: string, alt: string, ...body: (Node | null)[]) =>
  h("div", { class: "card" }, h("div", { class: "row", style: "gap:24px" }, h("img", { class: "photo", src, alt }), h("div", { class: "stack", style: "flex:1;min-width:200px" }, ...body)));

const nameInput = (pic: Picture) => h("input", { type: "text", class: "name-field", value: pictureTitle(pic), maxLength: 24 });
const typed = (input: HTMLInputElement) => input.value.trim() || "Picture";
const nameHint = h("p", { class: "dim small" }, "Your kid sees this name in the Art room, under Open (Esc, then O).");

// A name no other picture of theirs has.
function freeName(text: string, except?: Picture): string {
  const base = slug(text);
  const taken = (n: string) => draft.pictures.some((p) => p !== except && p.name === n);
  let name = base;
  for (let i = 2; taken(name); i++) name = `${base}-${i}`;
  return name;
}

function tryView(pic: Picture, ex: Example | null): HTMLElement {
  const name = nameInput(pic);
  const add = () => {
    const kept = { ...pic, title: typed(name), name: freeName(typed(name)) };
    draft.pictures = [...draft.pictures, kept];
    uploaded = null;
    changed();
    goTo(kept.name);
  };
  name.addEventListener("keydown", (e) => e.key === "Enter" && add());
  return h("section", {},
    card(pic.sourceUrl, ex?.alt ?? "",
      h("p", { class: "trying" }, "Just trying it on the screen. It isn't on your Purple yet."),
      ex?.credit ? h("p", { class: "dim small" }, ex.credit) : null,
      field("Name it", name), nameHint,
      h("div", { class: "row" }, h("button", { class: "btn", onclick: add }, "Add to my Purple"))),
    ...more(ex?.name ?? null));
}

function familyView(pic: Picture): HTMLElement {
  const name = nameInput(pic);
  name.onchange = () => {
    pic.title = typed(name);
    pic.name = freeName(pic.title, pic);
    changed();
    history.replaceState(null, "", `#pictures/${encodeURIComponent(pic.name)}`);
  };
  const remove = () => {
    draft.pictures = draft.pictures.filter((p) => p !== pic);
    changed();
    location.hash = "#pictures";
  };
  return h("section", {},
    card(pic.sourceUrl, "",
      h("p", { class: "added" }, "✓ On your Purple. Click the screen and type to paint on top of it."),
      field("Its name", name), nameHint,
      h("div", {}, h("button", { class: "linkbtn dim", onclick: remove }, "Take it off my Purple"))),
    ...more(pic.name));
}

const caption = "Type on the keyboard to paint right on top of the picture, the way your kid will.";

export function picturesView(item: string | null): View {
  const setup: RoomSetup = { room: "art" };
  const view = (title: string, editor: HTMLElement, picture?: Picture): View => {
    setup.picture = picture?.ops;
    return { title, editor, live: setup, caption };
  };
  const pic = item ? draft.pictures.find((p) => p.name === item) : null;
  if (pic) return view(pictureTitle(pic), familyView(pic), pic);
  if (item === "try" && uploaded) return view("Trying a picture", tryView(uploaded, null), uploaded);

  const ex = EXAMPLES.find((e) => item === `try/${e.name}`);
  // With no pictures of their own yet, the first example is on the screen.
  const shown = ex ?? (draft.pictures.length ? null : EXAMPLES[0]);
  const editor = h("section", {});
  const here = location.hash;
  // An example paints in a moment; then it goes on the screen, and its page fills in.
  if (shown) void examplePicture(shown).then((p) => {
    if (location.hash !== here) return;
    setup.picture = p.ops;
    liveScreen().show(setup);
    if (ex) editor.replaceChildren(tryView(p, ex));
  });
  if (ex) return view(pictureTitle(ex), editor);
  editor.append(
    h("p", { class: "lead" }, "A photo, or a drawing your kid made, becomes a painting in the Art room. Then your kid paints right on top of it: give the dog a hat, color in the dinosaur, add a sun."),
    ...more(null),
  );
  return view("Pictures", editor, draft.pictures[0]);
}
