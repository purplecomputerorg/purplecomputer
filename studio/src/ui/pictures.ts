import type { RoomSetup } from "../live/boot";
import { canvasOrigin } from "@sdk/purple/art";
import { CANVAS_SHAPE, EXAMPLES, clampCrop, cropTo, examplePicture, fillCrop, letterPx, onScreen, pictureFromFile, wordLetters, wordsAt, type Crop, type Example, type Picture } from "../photo";
import { changed, draft, freeName, titleOf, withSample } from "../state";
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

const showPicture = (pic: Picture) => liveScreen().show({ room: "art", picture: onScreen(pic) });

// A picture edit: it's the family's now, and Purple's screen shows it.
function edited(pic: Picture) {
  pic.sample = false;
  changed();
  showPicture(pic);
}

// The words drawn over the photo as Purple writes them, one letter per cell, and dragged a cell at a time.
function wordsOverlay(pic: Picture, frame: HTMLElement): { element: HTMLElement; render: (crop?: Crop) => void } {
  const { width: W, height: H } = pic.bitmap;
  const element = h("div", { class: "crop-words" });
  const pct = (v: number, of: number) => `${(100 * v) / of}%`;
  // The photo's cells in its own pixels: the crop, or all of it.
  const grid = (crop = pic.crop) => {
    const r = crop ?? { x: 0, y: 0, w: W, h: H };
    const [rows, cols] = [pic.cells.length, pic.cells[0].length];
    return { ...r, cw: r.w / cols, ch: r.h / rows, origin: canvasOrigin(cols, rows) };
  };
  const cellPx = () => grid().cw * (frame.clientWidth / W);
  // Room above the words for the move handle, in screen pixels.
  const HANDLE_ROOM = 34;
  // crop: the crop box while it's being dragged, before it's applied.
  const render = (crop?: Crop) => {
    const { x: rx, y: ry, cw, ch, origin: [x0, y0] } = grid(crop);
    // An element over cells of the photo, from cell (x, y), w by h cells.
    const over = <T extends HTMLElement>(el: T, x: number, y: number, w = 1, hh = 1) =>
      (Object.assign(el.style, { left: pct(rx + x * cw, W), top: pct(ry + y * ch, H), width: pct(w * cw, W), height: pct(hh * ch, H) }), el);
    element.style.fontSize = `${letterPx(cellPx())}px`;
    const letters = wordLetters(pic).map(([x, y, char, ink]) => {
      const span = over(h("span", {}, char), x - x0, y - y0);
      span.style.color = ink;
      return span;
    });
    const at = wordsAt(pic);
    const below = !!at && (ry + at.y * ch) * (frame.clientHeight / H) < HANDLE_ROOM;
    const box = at && over(h("div", { class: `words-box${below ? " below" : ""}`, title: "Drag to move the words" },
      h("i", { class: "crop-handle words-grab" }, "✥")), at.x, at.y, Math.max(...at.lines.map((l) => l.length)), at.lines.length);
    element.replaceChildren(...letters, ...(box ? [box] : []));
  };
  element.onpointerdown = (e: PointerEvent) => {
    const start = wordsAt(pic);
    if (!start) return;
    e.preventDefault();
    const move = (m: PointerEvent) => {
      const [dx, dy] = [m.clientX - e.clientX, m.clientY - e.clientY].map((d) => Math.round(d / cellPx()));
      pic.words = { ...pic.words!, x: start.x + dx, y: start.y + dy };
      const { x, y } = wordsAt(pic)!;
      pic.words = { ...pic.words, x, y };
      render();
    };
    // On the window, since each move draws the letters anew.
    const up = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      edited(pic);
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
  };
  new ResizeObserver(() => render()).observe(frame);
  return { element, render };
}

// The whole photo on the screen, or a canvas-shaped box of it to drag and resize by its corner, and words to write on it.
function cropper(pic: Picture, ex: Example | undefined): HTMLElement {
  const { width: W, height: H } = pic.bitmap;
  const handle = h("i", { class: "crop-handle", title: "Drag to resize" }, "⤡");
  const box = h("div", { class: "crop-box" }, h("i", { class: "crop-handle crop-move", title: "Drag to move" }, "✥"), handle);
  const frame = h("div", { class: "cropper" }, h("img", { src: pic.sourceUrl, alt: ex?.alt ?? "" }), box);
  const words = wordsOverlay(pic, frame);
  frame.append(words.element);
  const text = h("textarea", { class: "words-field", maxLength: 200, placeholder: "Happy birthday!", "aria-label": "Words on the picture" });
  text.value = pic.words?.text ?? "";
  text.oninput = () => {
    pic.words = { ...pic.words, text: text.value };
    words.render();
    edited(pic);
  };
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
    cropTo(pic, c);
    show();
    words.render();
    edited(pic);
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
      words.render(crop);
    };
    box.setPointerCapture(e.pointerId);
    box.onpointermove = move;
    box.onpointerup = () => { box.onpointermove = box.onpointerup = null; apply(crop); };
  };
  box.onpointerdown = drag;
  show();
  return card("What shows on Purple", toggle(whole, fill), h("div", { class: "crop-stage" }, frame), hint,
    ex?.credit ? h("p", { class: "dim small" }, ex.credit) : null,
    h("h3", {}, "Words on the picture (if you like)"), text,
    h("p", { class: "dim small" }, "They show in Purple's own letters, the size they'll be on the screen. Drag the words or their circle on the picture to move them."));
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
  return h("section", {},
    tryBar(pic, () => drop(pic, true)),
    card("Name", null, name, h("p", { class: "dim small" }, "Find it in Art under Open (Esc, then O).")),
    cropper(pic, ex),
    ...more(pic));
}

const caption = "Type on the keyboard to paint on the picture, the way your kid will. It's just for trying and won't go in your Purple Pack.";

export function picturesView(item: string | null): View {
  // Purple's screen shows the picture painted on, added or not; Open lists only the added ones.
  const setup: RoomSetup = { room: "art" };
  const view = (title: string, editor: HTMLElement): View => ({ title, editor, live: setup, caption });
  const pic = item ? draft.pictures.find((p) => p.name === item) : null;
  if (pic) {
    setup.picture = onScreen(pic);
    const live = liveScreen();
    return { ...view(titleOf(pic), pictureView(pic)),
      mounted: () => { live.prompt("Type to paint on it!"); live.engage(); },
      cleanup: () => live.prompt(null) };
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
