import type { RoomSetup } from "../live/boot";
import { EXAMPLES, examplePicture, pictureFromFile, type Example, type Picture } from "../photo";
import { changed, draft, freeName, titleOf, withSample } from "../state";
import { field, h } from "./dom";
import { liveScreen } from "./live";
import { staysHere } from "./privacy";
import { tryBar } from "./trybar";
import type { View } from "./view";

const goTo = (name: string) => (location.hash = `#pictures/${encodeURIComponent(name)}`);
const pictureName = (text: string, except?: Picture) => freeName(text, (n) => draft.pictures.some((p) => p !== except && p.name === n), "picture");

function dropZone(): HTMLElement {
  const status = h("div", { class: "status" });
  const add = async (file: File | undefined) => {
    if (!file?.type.startsWith("image/")) return;
    status.textContent = `Painting ${file.name}…`;
    try {
      const pic = await pictureFromFile(file);
      pic.name = pictureName(pic.name);
      draft.pictures = [...draft.pictures, pic];
      changed();
      goTo(pic.name);
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
    h("div", { class: "small" }, "A photo, a scan of a drawing, anything. It stays on your device."),
    input,
  );
  return h("div", {}, drop, status);
}

// Trying one of ours: it joins the family's pictures as a try, replacing the last example tried.
async function tryExample(ex: Example) {
  let pic = draft.pictures.find((p) => p.sourceUrl === ex.src);
  if (!pic) {
    pic = { ...(await examplePicture(ex)), name: pictureName(ex.name) };
    draft.pictures = withSample(draft.pictures, pic);
    changed();
  }
  goTo(pic.name);
}

// Pictures to pick from, each with its name; the one being looked at is marked.
const thumb = (title: string, src: string, current: boolean, attrs: Record<string, unknown>) =>
  h("a", { ...attrs, "aria-current": current ? "page" : null }, h("img", { src, alt: "" }), h("span", {}, title));
const theirs = (list: Picture[], current: string | null) => h("div", { class: "photo-list" },
  ...list.map((p) => thumb(titleOf(p), p.sourceUrl, p.name === current, { href: `#pictures/${encodeURIComponent(p.name)}` })));

function more(current: Picture | null): HTMLElement[] {
  const kept = draft.pictures.filter((p) => p.kept);
  const trying = draft.pictures.filter((p) => !p.kept);
  return [
    h("div", {}, h("h3", {}, "On your Purple"), kept.length ? theirs(kept, current?.name ?? null) : h("p", { class: "dim small" }, "Nothing yet. Add your own, or try one of ours.")),
    ...(trying.length ? [h("h3", {}, "Trying"), theirs(trying, current?.name ?? null)] : []),
    h("h3", {}, "Add your own"), dropZone(),
    staysHere("Your pictures are turned into paintings right here in your browser. They are never uploaded."),
    h("h3", {}, "Try one of ours"),
    h("div", { class: "photo-list" }, ...EXAMPLES.map((e) => thumb(titleOf(e), e.src, current?.sourceUrl === e.src,
      { href: "#pictures", onclick: (ev: Event) => { ev.preventDefault(); void tryExample(e); } }))),
  ];
}

const card = (src: string, alt: string, ...body: (Node | null)[]) =>
  h("div", { class: "card" }, h("div", { class: "row", style: "gap:24px" }, h("img", { class: "photo", src, alt }), h("div", { class: "stack", style: "flex:1;min-width:200px" }, ...body)));

function pictureView(pic: Picture): HTMLElement {
  const ex = EXAMPLES.find((e) => e.src === pic.sourceUrl);
  const name = h("input", { type: "text", class: "name-field", value: titleOf(pic), maxLength: 24 });
  name.onchange = () => {
    pic.title = name.value.trim() || titleOf(pic);
    pic.name = pictureName(pic.title, pic);
    pic.sample = false;
    changed();
    history.replaceState(null, "", `#pictures/${encodeURIComponent(pic.name)}`);
  };
  const remove = () => {
    draft.pictures = draft.pictures.filter((p) => p !== pic);
    changed();
    location.hash = "#pictures";
  };
  return h("section", {},
    card(pic.sourceUrl, ex?.alt ?? "",
      tryBar(pic, remove),
      ex?.credit ? h("p", { class: "dim small" }, ex.credit) : null,
      field("Its name", name),
      h("p", { class: "dim small" }, "Your kid sees this name in the Art room, under Open (Esc, then O). Click the screen and type to paint on top of it.")),
    ...more(pic));
}

const caption = "Type on the keyboard to paint right on top of the picture, the way your kid will.";

export function picturesView(item: string | null): View {
  // Purple's screen shows the picture painted on, added or not; Open lists only the added ones.
  const setup: RoomSetup = { room: "art" };
  const view = (title: string, editor: HTMLElement): View => ({ title, editor, live: setup, caption });
  const pic = item ? draft.pictures.find((p) => p.name === item) : null;
  if (pic) {
    setup.picture = pic.ops;
    return view(titleOf(pic), pictureView(pic));
  }
  const first = draft.pictures.find((p) => p.kept) ?? draft.pictures[0];
  setup.picture = first?.ops;
  // With nothing of their own yet, the screen shows one of ours without trying it.
  const here = location.hash;
  if (!first) void examplePicture(EXAMPLES[0]).then((p) => {
    if (location.hash !== here) return;
    setup.picture = p.ops;
    liveScreen().show(setup);
  });
  return view("Pictures", h("section", {},
    h("p", { class: "lead" }, "A photo, or a drawing your kid made, becomes a painting in the Art room. Then your kid paints right on top of it: give the dog a hat, color in the dinosaur, add a sun."),
    ...more(null)));
}
