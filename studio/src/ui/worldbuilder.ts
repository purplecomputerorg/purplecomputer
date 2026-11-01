// The explore room's builder: the hero (drawn square by square, or an emoji or photo), everything in the world as
// cards, the maps to paint (big when wanted), and the sounds. Letters stay in the Python: each new thing gets a
// free one, and nothing here shows them.
import type { Knob, Lit } from "../knobs";
import { ask, h, removeButton } from "./dom";
import { emojiCell, isEmoji, searchEmoji } from "./emojipicker";
import { isMap, isWorld, legendNames, lettersIn, mapPainter } from "./mappainter";
import { roomPicture } from "./roomfiles";
import { select } from "./rulesform";
import { COLOR, isFace, isStr, knobNamed, section, soundRow, str, tupleOf, wordsIn, type Dict, type Face, type Str, type Tuple } from "./builderkit";

const KINDS: [string, string][] = [["friend", "A friend who talks"], ["find", "Something to find"], ["wall", "A wall"], ["ground", "Ground to walk on"], ["home", "Home, open once all is found"]];
// Letters a new thing can take, plainest first; never a number (a door), . (grass) or Y (the hero's start).
const FREE = "ABCDEGIJKLMNOPQSUVWXZabcdefghijklmnopqrstuvwxz@%&+=?!";
const HERO_FREE = "ABCDEFGHIJKLMNOPQRSTUVWXZ";
const COLORS = ["#e44444", "#2e6ae1", "#2e9e4f", "#e0a020", "#9b4dca", "#e0457b", "#1fa5a5", "#8a5a2b"];
const START = "Y";
type Thing = [Str, Tuple];
type Rows = { t: "list"; items: Str[] };

const isThings = (v: Lit | undefined): v is Dict => v?.t === "dict" && v.entries.every(([k, x]) => isStr(k) && [...k.v].length === 1 && tupleOf(x, isFace, isStr, isStr));
const isColors = (v: Lit | undefined): v is Dict => v?.t === "dict" && v.entries.every(([k, x]) => isStr(k) && [...k.v].length === 1 && tupleOf(x, isStr, isStr));

export function worldParts(knobs: Knob[]) {
  const v = (name: string) => knobNamed(knobs, name)?.value;
  const [world, things, hero, colors, picture, ground] = ["WORLD", "THINGS", "HERO", "HERO_COLORS", "HERO_PICTURE", "GROUND"].map(v);
  const ok = world && isWorld(world) && isThings(things) && hero && isMap(hero) && isColors(colors) && isFace(picture)
    && ground?.t === "tuple" && ground.items.every((c) => isStr(c) && COLOR.test(c.v));
  return ok ? { world: world as Dict, things: things as Dict, hero: hero as Rows, colors: colors as Dict, ground: ground as Tuple } : null;
}

// The hero as drawn: each letter a color square, . see-through.
function heroArt(rows: Str[], colors: Dict, size: number): HTMLCanvasElement {
  const w = Math.max(...rows.map((r) => [...r.v].length));
  const c = h("canvas", { class: "hero-art", width: w, height: rows.length });
  c.style.width = `${size}px`;
  const ctx = c.getContext("2d")!;
  const palette = new Map(colors.entries.map(([k, x]) => [(k as Str).v, ((x as Tuple).items[1] as Str).v]));
  rows.forEach((r, y) => [...r.v].forEach((l, x) => {
    const color = palette.get(l);
    if (color) { ctx.fillStyle = color; ctx.fillRect(x, y, 1, 1); }
  }));
  return c;
}

export function worldBuilder(knobs: Knob[], onEdit: () => void): HTMLElement | null {
  const parts = worldParts(knobs);
  if (!parts) return null;
  const { world, things, hero, colors, ground } = parts;
  const pictureKnob = knobNamed(knobs, "HERO_PICTURE")!;
  const el = h("div", { class: "card knobs builder world-builder" });
  const list = () => things.entries as Thing[];
  const thingParts = (t: Thing) => t[1].items as [Face, Str, Str];
  const maps = () => world.entries.map(([, x]) => (x as Rows).items);
  // Which map and brush are picked, kept across redraws and shared with the big map.
  const view = { map: 0, brush: "." };
  // The painters showing (the page's, and the big one while it's open), redrawn when a look changes.
  const painters = new Set<() => void>();
  let small: (() => void) | null = null;
  const repaint = () => painters.forEach((p) => p());
  const edited = () => { onEdit(); repaint(); };
  const changed = () => { draw(); edited(); };

  const heroLook = (size: number): Node => {
    const p = pictureKnob.value as Face;
    if (p.v) return (p.t === "picture" && roomPicture(p.v)) || h("span", { class: "hero-emoji", style: `font-size: ${size * 0.8}px` }, p.v);
    return heroArt(hero.items, colors, size);
  };
  const legend = () => legendNames(things);

  // The hero on a patch of the room's grass, as Purple shows them, so they're easy to spot there.
  const scene = h("div", { class: "hero-scene", title: "How the hero looks on Purple" });
  const drawScene = () => scene.replaceChildren(...Array.from({ length: 9 }, (_, i) =>
    h("div", { style: `background: ${(ground.items[(i + Math.floor(i / 3)) % 2] as Str).v}` }, i === 4 ? heroLook(26) : null)));
  painters.add(drawScene);

  // Every square with this letter, on every map, turned to grass.
  const unpaint = (letter: string) => maps().forEach((rows) => rows.forEach((r) => { r.v = [...r.v].map((l) => (l === letter ? "." : l)).join(""); }));
  const onMap = (letter: string) => maps().flat().reduce((n, r) => n + [...r.v].filter((l) => l === letter).length, 0);

  const addThing = () => {
    const taken = new Set([...lettersIn(world), ...list().map(([k]) => k.v)]);
    const letter = [...FREE].find((l) => !taken.has(l));
    if (!letter) return;
    const face = searchEmoji("", 1, list().map((t) => thingParts(t)[0].v))[0]?.emoji ?? "🐰";
    things.entries.push([str(letter), { t: "tuple", items: [str(face), str("friend"), str("")] }]);
    view.brush = letter;
    changed();
    (document.querySelector<HTMLElement>(".big-map .thing-detail .emoji-cell") ?? el.querySelector<HTMLElement>(".thing-detail .emoji-cell"))?.click();
  };

  // The picked thing, under the brushes: how it looks, what it is, and what it says.
  const thingDetail = (t: Thing, i: number) => {
    const [face, kind, says] = thingParts(t);
    const door = /\d/.test(t[0].v);
    const color = face.t === "str" && COLOR.test(face.v);
    const look = color
      ? h("input", { type: "color", value: face.v, oninput: (e: Event) => { face.v = (e.target as HTMLInputElement).value; onEdit(); }, onchange: repaint })
      : h("span", { class: "emoji-wrap" }, emojiCell(face.v, () => "", (e) => { Object.assign(face, { t: isEmoji(e) ? "str" : "picture", v: e }); edited(); }, { pictures: true }));
    const swap = h("button", { class: "linkbtn dim small", onclick: () => { Object.assign(face, color ? { t: "str", v: "🌼" } : { t: "str", v: COLORS[i % COLORS.length] }); changed(); } },
      color ? "Use a picture" : "Use a color");
    const n = onMap(t[0].v);
    const drop = removeButton(async () => {
      if (n && !(await ask(`Take it off the map too? It's on the map ${n === 1 ? "once" : `${n} times`}.`, "Take it off"))) return;
      unpaint(t[0].v);
      things.entries.splice(i, 1);
      view.brush = ".";
      changed();
    });
    return h("div", { class: "thing-detail" },
      h("div", { class: "thing-top" }, look,
        door ? h("span", { class: "dim small" }, "A door: two with the same number lead to each other.") : select(KINDS, kind.v, (k) => { kind.v = k; changed(); }),
        list().length > 1 && !door ? drop : h("span")),
      kind.v === "friend" ? wordsIn(says, onEdit, "What they say when the hero bumps into them") : null,
      h("div", { class: "thing-links" }, swap, n ? null : h("span", { class: "bad small" }, "Not on the map yet")));
  };
  const note = (text: string, ...more: Node[]) => h("div", { class: "thing-detail" }, h("span", { class: "dim small" }, text), ...more);
  const detail = (letter: string): Node | null => {
    const i = list().findIndex(([k]) => k.v === letter);
    if (i >= 0) return thingDetail(list()[i], i);
    if (letter === START) return note("Where the hero starts. Paint it somewhere else to move them.");
    if (letter === ".") return note("Grass", ...(ground.items as Str[]).map((c) => h("input", { type: "color", value: c.v, oninput: (e: Event) => { c.v = (e.target as HTMLInputElement).value; onEdit(); } })));
    return /\d/.test(letter) ? note("A door: two with the same number lead to each other.") : null;
  };
  const painterOpts = {
    view,
    detail,
    more: () => [h("button", { type: "button", class: "map-brush map-add", title: "Add something new", onclick: addThing }, "+ Add")],
    special: () => new Map([[START, () => heroLook(20)]]),
    names: () => new Map<string, string>([[START, "Where the hero starts"], [".", "Grass"],
      ...list().map(([k, x]): [string, string] => [k.v, KINDS.find(([kind]) => kind === (x.items[1] as Str).v)?.[1] ?? "A door"])]),
  };

  // The hero: an emoji or photo, or a little drawing painted a square at a time.
  const heroPart = () => {
    const p = pictureKnob.value as Face;
    const drawn = !p.v;
    const mode = h("span", { class: "seg" },
      h("button", { "aria-pressed": String(drawn), onclick: () => { pictureKnob.value = str(""); changed(); } }, "🎨 Draw"),
      h("button", { "aria-pressed": String(!drawn), onclick: () => { if (drawn) { pictureKnob.value = str("🦸"); changed(); } } }, "🖼️ Emoji or photo"));
    drawScene();
    const top = h("div", { class: "hero-top" }, mode, h("div", { class: "hero-onpurple" }, scene, h("span", { class: "dim small" }, "On Purple")));
    if (!drawn) {
      const cell = emojiCell(p.v, () => "", (e) => { pictureKnob.value = isEmoji(e) ? str(e) : { t: "picture", v: e }; changed(); }, { pictures: true });
      return section("The hero", "Who walks around the world.", top, h("div", { class: "hero-row" }, h("div", { class: "hero-big" }, heroLook(160)),
        h("span", { class: "emoji-wrap" }, cell)));
    }
    return section("The hero", "Who walks around the world.", top, heroPainter(hero, colors, edited, changed));
  };

  const mapPart = () => {
    const [painter, redraw] = mapPainter(world, legend, onEdit, { ...painterOpts, atMap: () => h("button", { class: "btn small map-big", onclick: openBig }, "⛶ Make it big") });
    if (small) painters.delete(small);
    painters.add(small = redraw);
    return section("The world", "Pick something to change it, or to paint it on the map. + Add makes something new: an animal, a friend, a treasure, anything.", painter);
  };

  // The world as large as the window, over everything.
  const openBig = () => {
    const [painter, redraw] = mapPainter(world, legend, onEdit, painterOpts);
    painters.add(redraw);
    const close = () => {
      painters.delete(redraw);
      layer.remove();
      removeEventListener("keydown", onKey);
      repaint();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !document.querySelector(".emoji-pop") && close();
    const layer = h("div", { class: "big-map", role: "dialog", "aria-label": "The world, big" },
      h("div", { class: "big-map-inner" }, h("div", { class: "big-map-head" }, h("b", {}, "The world"), h("button", { class: "btn small", onclick: close }, "Done")), painter));
    addEventListener("keydown", onKey);
    document.body.append(layer);
  };

  const draw = () => el.replaceChildren(
    heroPart(),
    mapPart(),
    section("Sounds", "Quiet unless you pick one.",
      ...[["When something is found", "FIND_SOUND"], ["Going through a door", "DOOR_SOUND"], ["Bumping into a wall", "BUMP_SOUND"], ["Getting home", "HOME_SOUND"]]
        .map(([label, name]) => soundRow(label, knobNamed(knobs, name), onEdit))));
  draw();
  return el;
}

// The hero's drawing as big squares to paint, and its colors as a palette: click a color to paint with it, click it
// again to change it. Each color's name stays in the Python and shows on hover.
function heroPainter(hero: Rows, colors: Dict, onPaint: () => void, onChange: () => void): HTMLElement {
  let brush = colors.entries[0] ? (colors.entries[0][0] as Str).v : ".";
  let down = false;
  const entries = () => colors.entries as [Str, Tuple][];
  const colorOf = (l: string) => ((entries().find(([k]) => k.v === l)?.[1].items[1]) as Str | undefined)?.v;
  const width = Math.max(...hero.items.map((r) => [...r.v].length));
  const letterAt = (x: number, y: number) => [...hero.items[y].v.padEnd(width, ".")][x];
  const cells = hero.items.map((_, y) => Array.from({ length: width }, (_, x) => {
    const cell = h("div", { class: "hero-cell" });
    const show = (letter: string) => { cell.style.background = colorOf(letter) ?? ""; };
    show(letterAt(x, y));
    const paint = () => {
      if (letterAt(x, y) === brush) return;
      const row = [...hero.items[y].v.padEnd(width, ".")];
      row[x] = brush;
      hero.items[y].v = row.join("");
      show(brush);
      onPaint();
    };
    cell.addEventListener("pointerdown", (e) => {
      down = true;
      addEventListener("pointerup", () => { down = false; }, { once: true });
      cell.releasePointerCapture(e.pointerId);
      paint();
    });
    cell.addEventListener("pointerenter", () => down && paint());
    return cell;
  }));
  const recolor = (letter: string, color: string) => cells.forEach((row, y) => row.forEach((c, x) => { if (letterAt(x, y) === letter) c.style.background = color; }));
  const palette = h("div", { class: "hero-palette" });
  const mark = () => palette.querySelectorAll<HTMLElement>("[data-brush]").forEach((b) => b.classList.toggle("on", b.dataset.brush === brush));

  const swatch = ([k, x]: [Str, Tuple], i: number) => {
    const [name, color] = x.items as [Str, Str];
    const dot = h("button", { type: "button", class: "hero-swatch", "data-brush": k.v, title: name.v, "aria-label": name.v, style: `background: ${color.v}` });
    const picker = h("input", { type: "color", value: color.v, tabindex: -1, "aria-hidden": "true", oninput: () => {
      color.v = picker.value;
      dot.style.background = color.v;
      recolor(k.v, color.v);
      onPaint();
    } });
    dot.addEventListener("click", () => {
      if (brush !== k.v) { brush = k.v; return mark(); }
      try { picker.showPicker(); } catch { picker.click(); }
    });
    const drop = entries().length > 1 ? h("button", { type: "button", class: "hero-drop", title: "Remove this color", "aria-label": "Remove this color", onclick: () => {
      hero.items.forEach((r) => { r.v = [...r.v].map((l) => (l === k.v ? "." : l)).join(""); });
      colors.entries.splice(i, 1);
      if (brush === k.v) brush = ".";
      onChange();
    } }, "×") : null;
    return h("span", { class: "hero-swatch-wrap" }, dot, picker, drop);
  };
  const eraser = h("button", { type: "button", class: "hero-swatch see-through", "data-brush": ".", title: "Eraser", "aria-label": "Eraser", onclick: () => { brush = "."; mark(); } });
  const add = h("button", { type: "button", class: "hero-swatch hero-add", title: "Add a color", "aria-label": "Add a color", onclick: () => {
    const taken = new Set([...entries().map(([k]) => k.v), ...hero.items.flatMap((r) => [...r.v])]);
    const letter = [...HERO_FREE].find((l) => !taken.has(l));
    if (!letter) return;
    colors.entries.push([str(letter), { t: "tuple", items: [str("color"), str(COLORS.find((c) => !entries().some(([, x]) => (x.items[1] as Str).v === c)) ?? COLORS[0])] }]);
    brush = letter;
    onChange();
  } }, "+");
  palette.replaceChildren(...entries().map(swatch), eraser, add);
  mark();
  return h("div", { class: "hero-paint" }, palette, h("div", { class: "hero-grid", style: `--cols: ${width}` }, ...cells.flat()));
}
