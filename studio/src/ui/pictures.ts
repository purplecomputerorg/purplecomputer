import type { RoomSetup } from "../live/boot";
import { CANVAS_SHAPE, EXAMPLES, clampCrop, cropTo, examplePicture, fillCrop, pictureFromFile, type Crop, type Example, type Picture } from "../photo";
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
    h("div", {}, h("h3", {}, "In your Purple Pack"), kept.length ? theirs(kept, current?.name ?? null) : h("p", { class: "dim small" }, "Nothing yet. Add your own, or try one of ours.")),
    ...(trying.length ? [h("h3", {}, "Trying"), theirs(trying, current?.name ?? null)] : []),
    h("h3", {}, "Add your own"), dropZone(),
    staysHere("Your pictures are turned into paintings right here in your browser. They are never uploaded."),
    h("h3", {}, "Try one of ours"),
    h("div", { class: "photo-list" }, ...EXAMPLES.map((e) => thumb(titleOf(e), e.src, current?.sourceUrl === e.src,
      { href: "#pictures", onclick: (ev: Event) => { ev.preventDefault(); void tryExample(e); } }))),
  ];
}

const card = (src: string, alt: string, ...body: (Node | null)[]) =>
  h("div", { class: "card" }, h("div", { class: "row", style: "gap:24px;align-items:flex-start" }, h("img", { class: "photo", src, alt }), h("div", { class: "stack", style: "flex:1;min-width:200px" }, ...body)));

// The whole photo on the screen, or a canvas-shaped box of it to drag and resize by its corner.
function cropper(pic: Picture): HTMLElement {
  const { width: W, height: H } = pic.bitmap;
  const handle = h("i", { class: "crop-handle", title: "Drag to resize" }, "⤡");
  const box = h("div", { class: "crop-box" }, h("i", { class: "crop-handle crop-move", title: "Drag to move" }, "✥"), handle);
  const frame = h("div", { class: "cropper" }, h("img", { src: pic.sourceUrl, alt: "" }), box);
  const mode = (label: string, crop: () => Crop | undefined) => h("button", { type: "button", onclick: () => apply(crop()) }, label);
  const whole = mode("Whole picture", () => undefined);
  const fill = mode("Fill the screen", () => pic.crop ?? fillCrop(W, H));
  const hint = h("p", { class: "dim small" }, "Drag the middle circle to move the box. Drag the corner circle to make it bigger or smaller.");
  const pct = (v: number, of: number) => `${(100 * v) / of}%`;
  const show = (c = pic.crop) => {
    box.hidden = hint.hidden = !c;
    whole.setAttribute("aria-pressed", String(!c));
    fill.setAttribute("aria-pressed", String(!!c));
    if (c) Object.assign(box.style, { left: pct(c.x, W), top: pct(c.y, H), width: pct(c.w, W), height: pct(c.h, H) });
  };
  const apply = (c?: Crop) => {
    cropTo(pic, c);
    pic.sample = false;
    show();
    changed();
    liveScreen().show({ room: "art", picture: pic.ops });
  };
  const drag = (e: PointerEvent) => {
    e.preventDefault();
    const start = pic.crop!;
    const resize = e.target === handle;
    const k = W / frame.clientWidth;
    let crop = start;
    const move = (m: PointerEvent) => {
      const [dx, dy] = [(m.clientX - e.clientX) * k, (m.clientY - e.clientY) * k];
      crop = clampCrop(resize
        ? { ...start, w: Math.min(start.w + Math.max(dx, dy * CANVAS_SHAPE), W - start.x, (H - start.y) * CANVAS_SHAPE) }
        : { ...start, x: start.x + dx, y: start.y + dy }, W, H);
      show(crop);
    };
    box.setPointerCapture(e.pointerId);
    box.onpointermove = move;
    box.onpointerup = () => { box.onpointermove = box.onpointerup = null; apply(crop); };
  };
  box.onpointerdown = drag;
  show();
  return h("div", {}, h("div", { class: "room-buttons crop-modes" }, whole, fill), frame, hint);
}

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
      field("Picture name", name),
      h("div", { class: "field" }, h("span", {}, "On the screen"), cropper(pic)),
      h("p", { class: "dim small" }, "Find it in Art under Open (Esc, then O).")),
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
