import type { RoomSetup } from "../live/boot";
import { CANVAS_SHAPE, EXAMPLES, clampCrop, cropTo, examplePicture, fillCrop, onScreen, pictureFromFile, type Crop, type Example, type Picture } from "../photo";
import { changed, draft, freeName, titleOf, withSample } from "../state";
import { KEY_EVENT } from "../keys";
import { go, h } from "./dom";
import { liveScreen } from "./live";
import { staysHere } from "./privacy";
import { tryBar, tryChip } from "./trybar";
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
  ...list.map((p) => {
    const link = thumb(titleOf(p), p.sourceUrl, p.name === current, { href: `#pictures/${encodeURIComponent(p.name)}` });
    return p.kept ? link : tryChip(link, titleOf(p), () => drop(p, p.name === current));
  }));

function drop(pic: Picture, showing: boolean) {
  draft.pictures = draft.pictures.filter((p) => p !== pic);
  changed();
  go(showing ? "#pictures" : location.hash);
}

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

// A card with its title, and the toggle (if any) on the title's right.
const card = (title: string, toggle: HTMLElement | null, ...body: (Node | null)[]) =>
  h("div", { class: "card stack" }, h("div", { class: "card-head" }, h("h2", {}, title), toggle), ...body);
const toggle = (...buttons: HTMLElement[]) => h("div", { class: "seg", role: "group" }, ...buttons);

const showPicture = (pic: Picture, writing = false) => liveScreen().show({ room: "art", picture: onScreen(pic), letters: writing });

// Keys that move the cursor, switch modes or open the menu without changing the canvas.
const NOT_EDITS = new Set(["tab", "escape", "up", "down", "left", "right"]);

// Paint or Write words on Purple's screen, and keeping what's there as the picture.
function paintedCard(pic: Picture): { element: HTMLElement; reset: () => void } {
  const live = liveScreen();
  const mode = (label: string, writing: boolean) => h("button", { type: "button", onclick: () => {
    if (live.place.writing !== writing) live.key("tab");
    live.engage();
  } }, label);
  const paint = mode("Paint", false);
  const write = mode("Write words", true);
  const how = h("p", { class: "dim small" });
  const kept = h("div", { class: "row", style: "gap:12px" });
  let edited = false;
  const reset = () => { edited = false; render(); };
  const onKey = (e: Event) => {
    if (!element.isConnected) return removeEventListener(KEY_EVENT, onKey);
    if (edited || NOT_EDITS.has((e as CustomEvent<string>).detail)) return;
    edited = true;
    render();
  };
  addEventListener(KEY_EVENT, onKey);
  const keep = async () => {
    pic.painted = await live.picture();
    pic.sample = false;
    changed();
    showPicture(pic, live.place.writing);
    reset();
  };
  const photoOnly = () => {
    pic.painted = undefined;
    changed();
    showPicture(pic);
    reset();
  };
  const render = () => {
    const writing = live.place.writing;
    paint.setAttribute("aria-pressed", String(!writing));
    write.setAttribute("aria-pressed", String(writing));
    how.textContent = writing
      ? "Type on Purple's screen to write on the picture. The arrows move where the words go. Tab goes back to painting."
      : "Type on Purple's screen to paint on the picture. It's just for trying until you save it.";
    kept.replaceChildren(
      ...(pic.painted ? [h("span", { class: "added" }, "✓ Your edits are saved on this picture")] : []),
      ...(edited ? [h("button", { class: "btn small", onclick: keep }, pic.painted ? "Save again" : "Save your edits in Studio")] : []),
      ...(pic.painted ? [h("button", { class: "linkbtn dim small", onclick: photoOnly }, "Back to just the photo")] : []));
  };
  const element = card("Paint on it in Studio", toggle(paint, write), how, kept,
    h("p", { class: "dim small" }, "When this picture is in your Purple Pack, your kid gets it with what you saved on it."));
  live.onWriting = render;
  render();
  return { element, reset };
}

// The whole photo on the screen, or a canvas-shaped box of it to drag and resize by its corner.
function cropper(pic: Picture, ex: Example | undefined, onCrop: () => void): HTMLElement {
  const { width: W, height: H } = pic.bitmap;
  const handle = h("i", { class: "crop-handle", title: "Drag to resize" }, "⤡");
  const box = h("div", { class: "crop-box" }, h("i", { class: "crop-handle crop-move", title: "Drag to move" }, "✥"), handle);
  const frame = h("div", { class: "cropper" }, h("img", { src: pic.sourceUrl, alt: ex?.alt ?? "" }), box);
  const mode = (label: string, crop: () => Crop | undefined) => h("button", { type: "button", onclick: () => apply(crop()) }, label);
  const whole = mode("Whole picture", () => undefined);
  const fill = mode("Fill the screen", () => pic.crop ?? fillCrop(W, H));
  const hint = h("p", { class: "dim small" });
  const pct = (v: number, of: number) => `${(100 * v) / of}%`;
  const show = (c = pic.crop) => {
    box.hidden = !c;
    hint.textContent = c
      ? "Drag the middle circle to move the box. Drag the corner circle to make it bigger or smaller."
      : "Purple shows all of the picture. Fill the screen picks a part of it to fill Purple's screen.";
    whole.setAttribute("aria-pressed", String(!c));
    fill.setAttribute("aria-pressed", String(!!c));
    if (c) Object.assign(box.style, { left: pct(c.x, W), top: pct(c.y, H), width: pct(c.w, W), height: pct(c.h, H) });
  };
  const apply = (c?: Crop) => {
    if (pic.painted && !confirm("Changing this takes off what you painted and wrote on the picture. Change it anyway?")) return show();
    cropTo(pic, c);
    pic.sample = false;
    show();
    changed();
    onCrop();
    showPicture(pic);
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
  return card("What part shows on Purple", toggle(whole, fill), h("div", { class: "crop-stage" }, frame), hint,
    ex?.credit ? h("p", { class: "dim small" }, ex.credit) : null);
}

function pictureView(pic: Picture): HTMLElement {
  const ex = EXAMPLES.find((e) => e.src === pic.sourceUrl);
  const name = h("input", { type: "text", class: "name-field", value: titleOf(pic), maxLength: 24, "aria-label": "Picture name" });
  name.onchange = () => {
    pic.title = name.value.trim() || titleOf(pic);
    pic.name = pictureName(pic.title, pic);
    pic.sample = false;
    changed();
    history.replaceState(null, "", `#pictures/${encodeURIComponent(pic.name)}`);
  };
  const painted = paintedCard(pic);
  return h("section", {},
    tryBar(pic, () => drop(pic, true)),
    card("Name", null, name, h("p", { class: "dim small" }, "Find it in Art under Open (Esc, then O).")),
    cropper(pic, ex, painted.reset),
    painted.element,
    ...more(pic));
}

const caption = "Type on the keyboard to paint on the picture, the way your kid will. It's just for trying and won't go in your Purple Pack.";

export function picturesView(item: string | null): View {
  // Purple's screen shows the picture painted on, added or not; Open lists only the added ones.
  const setup: RoomSetup = { room: "art" };
  const cleanup = () => (liveScreen().onWriting = () => {});
  const view = (title: string, editor: HTMLElement, text = caption): View => ({ title, editor, live: setup, caption: text, cleanup });
  const pic = item ? draft.pictures.find((p) => p.name === item) : null;
  if (pic) {
    setup.picture = onScreen(pic);
    const live = liveScreen();
    return { ...view(titleOf(pic), pictureView(pic), "Paint or write on the picture, the way your kid will. Only what you save goes in your Purple Pack."),
      mounted: () => { live.prompt("Type to paint on it!"); live.engage(); },
      cleanup: () => { cleanup(); live.prompt(null); } };
  }
  const first = draft.pictures.find((p) => p.kept) ?? draft.pictures[0];
  setup.picture = first && onScreen(first);
  // With nothing of their own yet, the screen shows one of ours without trying it.
  const here = location.hash;
  if (!first) void examplePicture(EXAMPLES[0]).then((p) => {
    if (location.hash !== here) return;
    setup.picture = onScreen(p);
    liveScreen().show(setup);
  });
  return view("Pictures", h("section", {},
    h("p", { class: "lead" }, "A photo, or a drawing your kid made, becomes a painting in the Art room. Then your kid paints right on top of it: give the dog a hat, color in the dinosaur, add a sun."),
    ...more(null)));
}
