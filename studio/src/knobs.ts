// A room's knobs: the ALL_CAPS settings at the top of its Python, each written as a plain value (words,
// numbers, lists, dicts, or one of the pack's pictures as picture("name")). Studio shows them as a form and writes edits back in place, so the rest of the
// Python, hand edits included, is never touched. A "# Labels: page, picture, words" line above a knob names
// the parts of each entry: its key first, then each part of its value.

export type Lit =
  | { t: "str"; v: string }
  | { t: "picture"; v: string }
  | { t: "num"; v: number }
  | { t: "bool"; v: boolean }
  | { t: "none" }
  | { t: "list" | "tuple"; items: Lit[] }
  | { t: "dict"; entries: [Lit, Lit][] };

// One setting: its name, the comment right above it, its labels, where its value sits in the source, and the value as
// last written, so an unchanged one keeps the room's own line breaks.
export interface Knob { name: string; about: string; labels: string[]; value: Lit; start: number; end: number; multiline: boolean; written: string }

class Parser {
  constructor(private s: string, public i: number) {}

  private skip() {
    for (;;) {
      while (/\s/.test(this.s[this.i] ?? "")) this.i++;
      if (this.s[this.i] !== "#") return;
      while (this.i < this.s.length && this.s[this.i] !== "\n") this.i++;
    }
  }

  private eat(c: string): boolean {
    this.skip();
    if (this.s[this.i] !== c) return false;
    this.i++;
    return true;
  }

  value(): Lit {
    this.skip();
    const c = this.s[this.i];
    if (c === '"' || c === "'") return { t: "str", v: this.string(c) };
    if (c === "[") return { t: "list", items: this.items("]") };
    if (c === "(") return { t: "tuple", items: this.items(")") };
    if (c === "{") return this.dict();
    if (this.s.startsWith("picture(", this.i)) return this.picture();
    const word = /^(True|False|None|-?\d+(\.\d+)?)\b/.exec(this.s.slice(this.i))?.[0];
    if (!word) throw new Error("not a plain value");
    this.i += word.length;
    return word === "None" ? { t: "none" } : word === "True" || word === "False" ? { t: "bool", v: word === "True" } : { t: "num", v: Number(word) };
  }

  private string(q: string): string {
    let out = "";
    for (this.i++; this.s[this.i] !== q; this.i++) {
      const c = this.s[this.i];
      if (c === undefined || c === "\n") throw new Error("unclosed string");
      if (c !== "\\") out += c;
      else out += ({ n: "\n", t: "\t" } as Record<string, string>)[this.s[++this.i]] ?? this.s[this.i];
    }
    this.i++;
    return out;
  }

  private picture(): Lit {
    this.i += "picture(".length;
    this.skip();
    const q = this.s[this.i];
    if (q !== '"' && q !== "'") throw new Error("expected a picture's name");
    const v = this.string(q);
    if (!this.eat(")")) throw new Error("expected )");
    return { t: "picture", v };
  }

  private items(close: string): Lit[] {
    this.i++;
    const out: Lit[] = [];
    while (!this.eat(close)) {
      out.push(this.value());
      if (!this.eat(",") && !this.eat(close)) throw new Error(`expected , or ${close}`);
      else if (this.s[this.i - 1] === close) break;
    }
    return out;
  }

  private dict(): Lit {
    this.i++;
    const entries: [Lit, Lit][] = [];
    while (!this.eat("}")) {
      const k = this.value();
      if (!this.eat(":")) throw new Error("expected :");
      entries.push([k, this.value()]);
      if (!this.eat(",") && !this.eat("}")) throw new Error("expected , or }");
      else if (this.s[this.i - 1] === "}") break;
    }
    return { t: "dict", entries };
  }
}

// A knob whose comment says out loud: Purple says its words, and the family can record them.
export const isLoud = (k: Knob) => /\bout loud\b/i.test(k.about);

// The words a room's out-loud knobs say: their text, not emoji, colors, or the names of the entries they point at.
export function loudLines(source: string): string[] {
  return readKnobs(source).filter(isLoud).flatMap(({ value }) => {
    const names = new Set(value.t === "dict" ? value.entries.map(([k]) => (k.t === "str" ? k.v : "")) : []);
    const words = (v: Lit): string[] => (v.t === "str" ? (/\p{L}/u.test(v.v) && !/^#[0-9a-f]{6}$/i.test(v.v) && !names.has(v.v) ? [v.v] : [])
      : v.t === "list" || v.t === "tuple" ? v.items.flatMap(words) : v.t === "dict" ? v.entries.flatMap(([, x]) => words(x)) : []);
    return words(value);
  });
}

const SETTING = /^([A-Z][A-Z0-9_]*)[ \t]*=[ \t]*/;
const LABELS = /^Labels:\s*/;
const PASSING = /^\s*(#.*)?$|^(from|import) /;

// The settings at the top of the file, up to the first line that isn't one (or a comment or an import).
export function readKnobs(source: string): Knob[] {
  const knobs: Knob[] = [];
  let about: string[] = [];
  for (let at = 0; at < source.length;) {
    const eol = source.indexOf("\n", at) < 0 ? source.length : source.indexOf("\n", at);
    const text = source.slice(at, eol);
    const m = SETTING.exec(text);
    if (m) {
      const p = new Parser(source, at + m[0].length);
      try {
        const value = p.value();
        const rest = source.slice(p.i, source.indexOf("\n", p.i) < 0 ? source.length : source.indexOf("\n", p.i));
        if (!/^\s*(#.*)?$/.test(rest)) break;
        const start = at + m[0].length;
        const multiline = source.slice(start, p.i).includes("\n");
        const hint = about.find((l) => LABELS.test(l));
        knobs.push({ name: m[1], about: about.filter((l) => l !== hint).join(" "), labels: hint?.replace(LABELS, "").split(",").map((l) => l.trim()) ?? [], value, start, end: p.i, multiline, written: literal(value, multiline) });
        at = p.i;
        about = [];
        continue;
      } catch {
        break;
      }
    }
    if (!PASSING.test(text)) break;
    about = text.trim().startsWith("#") ? [...about, text.trim().replace(/^#\s?/, "")] : [];
    at = eol + 1;
  }
  return knobs;
}

const INDENT = "    ";

export function literal(v: Lit, multiline = false): string {
  switch (v.t) {
    case "str": return JSON.stringify(v.v);
    case "picture": return `picture(${JSON.stringify(v.v)})`;
    case "num": return String(v.v);
    case "bool": return v.v ? "True" : "False";
    case "none": return "None";
    case "dict": {
      const parts = v.entries.map(([k, x]) => `${literal(k)}: ${literal(x)}`);
      return multiline && parts.length ? `{\n${parts.map((p) => `${INDENT}${p},\n`).join("")}}` : `{${parts.join(", ")}}`;
    }
    default: {
      const [open, close] = v.t === "list" ? ["[", "]"] : ["(", ")"];
      const parts = v.items.map((x) => literal(x));
      if (multiline && parts.length) return `${open}\n${parts.map((p) => `${INDENT}${p},\n`).join("")}${close}`;
      return `${open}${parts.join(", ")}${v.t === "tuple" && parts.length === 1 ? "," : ""}${close}`;
    }
  }
}

// The source with every knob's value written back; each knob's place is updated to match.
export function writeKnobs(source: string, knobs: Knob[]): string {
  let out = "";
  let from = 0;
  for (const k of knobs) {
    out += source.slice(from, k.start);
    const text = literal(k.value, k.multiline);
    const kept = text === k.written ? source.slice(k.start, k.end) : text;
    from = k.end;
    k.start = out.length;
    out += kept;
    k.end = out.length;
    k.written = text;
  }
  return out + source.slice(from);
}
