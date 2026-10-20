// A map knob (rows of letters, all one length) as a grid to paint on. Each letter shows as what the room's
// legend (a dict of one-letter keys, like THINGS) makes it. Painting keeps every row the same length, and a
// letter the map has just one of and the legend doesn't name (where the hero starts) moves instead of spreading.
import type { Lit } from "../knobs";
import { h } from "./dom";

type Str = Extract<Lit, { t: "str" }>;
const COLOR = /^#[0-9a-f]{6}$/i;
const lettersOf = (rows: Str[]) => rows.map((r) => [...r.v]);
let down = false;

export const isMap = (v: Lit): boolean => {
  if (v.t !== "list" || v.items.length < 3 || !v.items.every((x) => x.t === "str")) return false;
  const widths = new Set(v.items.map((x) => [...(x as Str).v].length));
  return widths.size === 1 && [...widths][0] >= 3 && v.items.every((x) => /^[!-~]+$/.test((x as Str).v));
};

type Legend = Extract<Lit, { t: "dict" }>;
const isLegend = (v: Lit): v is Legend =>
  v.t === "dict" && v.entries.length > 0 && v.entries.every(([k, x]) => k.t === "str" && [...k.v].length === 1 && x.t === "str");

// The dict of one-letter keys that names the most letters on the map.
export function legendFor(map: { items: Lit[] }, values: Lit[]): Legend | undefined {
  const used = new Set(lettersOf(map.items as Str[]).flat());
  const hits = (d: Legend) => d.entries.filter(([k]) => used.has((k as Str).v)).length;
  return values.filter(isLegend).filter((d) => hits(d) > 0).sort((a, b) => hits(b) - hits(a))[0];
}

export const legendNames = (d: Legend | undefined) => new Map(d?.entries.map(([k, x]) => [(k as Str).v, (x as Str).v]));

function look(el: HTMLElement, letter: string, legend: Map<string, string>) {
  const shown = legend.get(letter);
  const color = shown && COLOR.test(shown);
  el.style.background = color ? shown : "";
  el.textContent = color ? "" : shown ?? (letter === "." ? "" : letter);
  el.classList.toggle("letter", !shown && letter !== ".");
}

// Returns the painter and its redraw, for when the legend changes.
export function mapPainter(map: { items: Lit[] }, legend: () => Map<string, string>, onEdit: () => void): [HTMLElement, () => void] {
  const rows = map.items as Str[];
  let brush = ".";
  const el = h("div", { class: "map-painter" });

  const redraw = () => {
    const grid = lettersOf(rows);
    const names = legend();
    const count = (l: string) => grid.flat().filter((c) => c === l).length;
    const only = (l: string) => !names.has(l) && l !== "." && count(l) === 1;
    const letters = [...new Set([...names.keys(), ".", ...grid.flat()])];
    const blank = grid.flat().includes(".") ? "." : letters[0];

    const paint = (r: number, c: number, cell: HTMLElement) => {
      const was = grid[r][c];
      if (was === brush || only(was)) return;
      if (only(brush)) {
        grid.forEach((line, rr) => line.forEach((l, cc) => { if (l === brush) { line[cc] = blank; look(cells[rr][cc], blank, names); } }));
      }
      grid[r][c] = brush;
      look(cell, brush, names);
      grid.forEach((line, i) => { rows[i].v = line.join(""); });
      onEdit();
    };

    const cells = grid.map((line, r) => line.map((l, c) => {
      const cell = h("div", { class: "map-cell" });
      look(cell, l, names);
      cell.addEventListener("pointerdown", (e) => {
        down = true;
        window.addEventListener("pointerup", () => { down = false; }, { once: true });
        // Touch captures the pointer to the first cell; letting go lets a drag reach the others.
        cell.releasePointerCapture(e.pointerId);
        paint(r, c, cell);
      });
      cell.addEventListener("pointerenter", () => { if (down) paint(r, c, cell); });
      return cell;
    }));
    const board = h("div", { class: "map-grid" }, ...cells.flat());
    board.style.setProperty("--cols", String(grid[0].length));

    const swatches = letters.map((l) => {
      const face = h("span", { class: "map-cell" });
      look(face, l, names);
      return h("button", {
        type: "button", class: `map-brush${l === brush ? " on" : ""}`,
        title: only(l) ? "There's just one of these. Paint to move it." : "",
        onclick: () => { brush = l; redraw(); },
      }, face, h("code", {}, l));
    });
    el.replaceChildren(h("div", { class: "map-brushes" }, ...swatches), board,
      h("p", { class: "dim small" }, "Pick something above, then click or drag on the map to paint it."));
  };

  redraw();
  return [el, redraw];
}
