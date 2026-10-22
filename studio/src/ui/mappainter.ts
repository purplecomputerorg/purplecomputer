// A map knob (rows of letters, all one length), or a world (a dict of maps by name), as grids to paint on. Each
// letter shows as what the room's legend (a dict of one-letter keys, like THINGS) makes it. Painting keeps every row
// the same length, and a letter the world has just one of and the legend doesn't name (where the hero starts) moves
// instead of spreading. A number joins the two squares holding it, so each should be on the world exactly twice.
import type { Lit } from "../knobs";
import { addRowButton, h, removeButton } from "./dom";
import { roomPicture } from "./roomfiles";
import { textIn } from "./rulesform";

type Str = Extract<Lit, { t: "str" }>;
type Face = Extract<Lit, { t: "str" | "picture" }>;
type Dict = Extract<Lit, { t: "dict" }>;
const COLOR = /^#[0-9a-f]{6}$/i;
const lettersOf = (rows: Str[]) => rows.map((r) => [...r.v]);
let down = false;

export const isMap = (v: Lit): boolean => {
  if (v.t !== "list" || v.items.length < 3 || !v.items.every((x) => x.t === "str")) return false;
  const widths = new Set(v.items.map((x) => [...(x as Str).v].length));
  return widths.size === 1 && [...widths][0] >= 3 && v.items.every((x) => /^[!-~]+$/.test((x as Str).v));
};

export const isWorld = (v: Lit): boolean => v.t === "dict" && v.entries.length > 0 && v.entries.every(([k, x]) => k.t === "str" && isMap(x));

// The maps of a map or world knob: a world's come with their names.
const mapsOf = (v: Lit): { name?: Str; rows: Str[] }[] =>
  isWorld(v) ? (v as Dict).entries.map(([k, x]) => ({ name: k as Str, rows: (x as { items: Str[] }).items })) : [{ rows: (v as { items: Str[] }).items }];

type Legend = Extract<Lit, { t: "dict" }>;
const isLegend = (v: Lit): v is Legend =>
  v.t === "dict" && v.entries.length > 0 && v.entries.every(([k, x]) => k.t === "str" && [...k.v].length === 1 && (x.t === "str" || x.t === "picture"));

// The dict of one-letter keys that names the most letters on the map or world.
export function legendFor(map: Lit, values: Lit[]): Legend | undefined {
  const used = lettersIn(map);
  const hits = (d: Legend) => d.entries.filter(([k]) => used.has((k as Str).v)).length;
  return values.filter(isLegend).filter((d) => hits(d) > 0).sort((a, b) => hits(b) - hits(a))[0];
}

// Every letter on the map or world's squares.
export const lettersIn = (v: Lit) => new Set(mapsOf(v).flatMap((m) => lettersOf(m.rows).flat()));

export const legendNames = (d: Legend | undefined) => new Map(d?.entries.map(([k, x]) => [(k as Str).v, x as Face]));

// The numbers that don't join two squares: they lead nowhere, or it's unclear where.
export const lonelyNumbers = (v: Lit): string[] => {
  const all = mapsOf(v).flatMap((m) => lettersOf(m.rows).flat()).filter((l) => /\d/.test(l));
  return [...new Set(all)].filter((n) => all.filter((l) => l === n).length !== 2).sort();
};

// A new map the size of the first, walled with its corner letter.
function blankMap(world: Dict): Lit {
  const rows = mapsOf(world)[0].rows.map((r) => [...r.v]);
  const wall = rows[0][0];
  const items = rows.map((line, r) => ({ t: "str", v: line.map((_, c) => (r % (rows.length - 1) && c % (line.length - 1) ? "." : wall)).join("") }) as Str);
  return { t: "list", items };
}

// A number the legend doesn't name looks like the first one it does, so a new way between maps needs no new picture.
const faceOf = (letter: string, legend: Map<string, Face>) =>
  legend.get(letter) ?? (/\d/.test(letter) ? [...legend].find(([k]) => /\d/.test(k))?.[1] : undefined);

function look(el: HTMLElement, letter: string, legend: Map<string, Face>) {
  const shown = faceOf(letter, legend);
  const color = shown?.t === "str" && COLOR.test(shown.v);
  el.style.background = color ? shown.v : "";
  el.replaceChildren(color ? "" : shown ? (shown.t === "picture" && roomPicture(shown.v)) || shown.v : letter === "." ? "" : letter);
  el.classList.toggle("letter", !shown && letter !== ".");
  // A door's number is the one letter that matters while painting: it says which doors lead to each other.
  if (shown && /\d/.test(letter)) el.append(h("span", { class: "map-num" }, letter));
}

// Returns the painter and its redraw, for when the legend changes.
export function mapPainter(knob: Lit, legend: () => Map<string, Face>, onEdit: () => void): [HTMLElement, () => void] {
  const world = isWorld(knob) ? (knob as Dict) : undefined;
  let brush = ".";
  const el = h("div", { class: "map-painter" });

  const redraw = () => {
    const maps = mapsOf(knob);
    const grids = maps.map((m) => lettersOf(m.rows));
    const names = legend();
    const count = (l: string) => grids.flat(2).filter((c) => c === l).length;
    const only = (l: string) => !names.has(l) && !/[.\d]/.test(l) && count(l) === 1;
    const used = [...new Set([...names.keys(), ".", ...grids.flat(2)])];
    // Once the world has a number, the next free one is ready to paint a new way between two places.
    const next = used.some((l) => /\d/.test(l)) ? [..."123456789"].find((n) => !used.includes(n)) : undefined;
    const letters = next ? [...used, next] : used;
    const blank = grids.flat(2).includes(".") ? "." : letters[0];
    const note = h("p", { class: "bad small" });
    const lonely = () => {
      const said = (n: string) => {
        const face = faceOf(n, names);
        const what = `${face?.t === "str" && !COLOR.test(face.v) ? `${face.v} ` : ""}${n}`;
        return count(n) === 1
          ? `The ${what} doesn't go anywhere yet. Paint another ${n} where it should take you, on this map or another one.`
          : `There are ${count(n)} squares with ${n}, so the hero won't know which one to go to. Keep just two.`;
      };
      note.textContent = lonelyNumbers(knob).map(said).join(" ");
    };

    const paint = (m: number, r: number, c: number) => {
      const was = grids[m][r][c];
      if (was === brush || only(was)) return;
      const set = (mm: number, rr: number, cc: number, l: string) => {
        grids[mm][rr][cc] = l;
        look(cells[mm][rr][cc], l, names);
        maps[mm].rows[rr].v = grids[mm][rr].join("");
      };
      if (only(brush)) grids.forEach((g, mm) => g.forEach((line, rr) => line.forEach((l, cc) => l === brush && set(mm, rr, cc, blank))));
      set(m, r, c, brush);
      lonely();
      onEdit();
    };

    const cells = grids.map((grid, m) => grid.map((line, r) => line.map((l, c) => {
      const cell = h("div", { class: "map-cell" });
      look(cell, l, names);
      cell.addEventListener("pointerdown", (e) => {
        down = true;
        window.addEventListener("pointerup", () => { down = false; }, { once: true });
        // Touch captures the pointer to the first cell; letting go lets a drag reach the others.
        cell.releasePointerCapture(e.pointerId);
        paint(m, r, c);
      });
      cell.addEventListener("pointerenter", () => { if (down) paint(m, r, c); });
      return cell;
    })));

    const board = (m: number) => {
      const b = h("div", { class: "map-grid" }, ...cells[m].flat());
      b.style.setProperty("--cols", String(grids[m][0].length));
      const name = maps[m].name;
      if (!name || !world) return b;
      const nameIn = textIn(name.v, (s) => {
        name.v = s;
        nameIn.classList.toggle("bad", !s || maps.filter((o) => o.name!.v === s).length > 1);
        onEdit();
      }, { class: "inline map-name" });
      // The map holding the hero's start stays, so the room always has somewhere to begin.
      const keep = maps.length === 1 || grids[m].flat().some(only);
      const drop = () => { world.entries.splice(m, 1); onEdit(); redraw(); };
      return h("div", { class: "map-one" }, h("div", { class: "map-head" }, nameIn, keep ? "" : removeButton(drop)), b);
    };

    const add = () => {
      if (!world) return "";
      const taken = new Set(maps.map((m) => m.name!.v));
      let n = maps.length + 1;
      while (taken.has(`map${n}`)) n++;
      return addRowButton("Add a map", () => { world.entries.push([{ t: "str", v: `map${n}` }, blankMap(world)]); onEdit(); redraw(); });
    };

    const swatches = letters.map((l) => {
      const face = h("span", { class: "map-cell" });
      look(face, l, names);
      return h("button", {
        type: "button", class: `map-brush${l === brush ? " on" : ""}`,
        title: only(l) ? "There's just one of these. Paint to move it." : "",
        onclick: () => { brush = l; redraw(); },
      }, face);
    });
    lonely();
    el.replaceChildren(h("div", { class: "map-brushes" }, ...swatches), ...maps.map((_, m) => board(m)), add(), note,
      h("p", { class: "dim small" }, "Pick something above, then click or drag on the map to paint it."));
  };

  redraw();
  return [el, redraw];
}
