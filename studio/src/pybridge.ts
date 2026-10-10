// What Studio's Python page can reach: a handful of functions over the draft, each one
// validating the way Purple would. Pure, so tests can drive it under Pyodide in Node.
import { ROOM_NAME } from "@sdk/pack";
import { BASES, defaults, type BaseName } from "@sdk/purple/synth";
import { changed, draft, pieces, slug, type RoomDraft } from "./state";

export function addRoom(name: string, source: string, made: Pick<RoomDraft, "blocks" | "template"> = { blocks: null, template: null }): RoomDraft {
  const room: RoomDraft = { name, source, ...made };
  draft.rooms = [...draft.rooms.filter((r) => r.name !== name), room];
  changed();
  return room;
}

export const bridge = {
  add_word(word: string, emoji: string) {
    draft.words = [...draft.words.filter((w) => w.word !== word), { word, emoji }];
    changed();
  },
  add_synonym(alias: string, word: string) {
    draft.synonyms = [...draft.synonyms.filter((s) => s.alias !== alias), { alias, word }];
    changed();
  },
  rank(word: string) {
    if (!draft.ranked.includes(word)) draft.ranked = [...draft.ranked, word];
    changed();
  },
  add_instrument(name: string, base: string, paramsJson: string): string {
    if (!(base in BASES)) return `base must be one of ${Object.keys(BASES).join(", ")}`;
    const params = JSON.parse(paramsJson) as Record<string, unknown>;
    const allowed = defaults(base as BaseName);
    for (const [k, v] of Object.entries(params)) {
      if (!(k in allowed)) return `${base} has no parameter ${k}`;
      if (typeof v !== "number") return `${k} must be a number`;
    }
    const id = slug(name) || `my-${base}`;
    draft.instruments = [...draft.instruments.filter((i) => i.name !== id), { name: id, base: base as BaseName, params: { ...allowed, ...(params as Record<string, number>) } }];
    changed();
    return "";
  },
  add_room(name: string, source: string): string {
    if (!ROOM_NAME.test(name)) return "a room name is lowercase letters, digits, and dashes";
    addRoom(name, source);
    return "";
  },
  summary(): string {
    return JSON.stringify(Object.fromEntries(pieces().map((p) => [p.label.replace(/ /g, "_"), p.count])));
  },
};
