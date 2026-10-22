// The lines a room always says the same way: say("...") with one plain string literal. Studio speaks
// these in the room voice ahead of time (content/room-voice/); lines built while the room runs fall
// back to Purple's own voice on the laptop.
import exported from "./purple/export.json";
import { voiceClipFilename } from "./purple/sounds";

// family_room.TEXT_MAX, which Purple cuts a say to before looking for its clip.
const SAY_MAX: number = exported.room.say_max;
const SAY = /(?<![\w])say\s*\(\s*([rRuU]?)("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')\s*\)/g;
const ESCAPES: Record<string, string> = { n: "\n", t: "\t", r: "\r", "\\": "\\", "'": "'", '"': '"', "\n": "", a: "\x07", b: "\b", f: "\f", v: "\v", "0": "\0" };

// A Python string literal's value; null for escapes this doesn't read (\N{...}, octal), so the line is skipped.
function unquote(prefix: string, quoted: string): string | null {
  const body = quoted.slice(1, -1);
  if (/r/i.test(prefix)) return body;
  let ok = true;
  const out = body.replace(/\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|[\s\S])/g, (_, e: string) => {
    if (e.length > 1) return String.fromCodePoint(parseInt(e.slice(1), 16));
    if (e in ESCAPES) return ESCAPES[e];
    ok = false;
    return "";
  });
  return ok ? out : null;
}

// What Purple will look a line up as: cut to SAY_MAX characters, and only names a file system can hold.
export const asSaid = (text: string) => [...text].slice(0, SAY_MAX).join("");
export const fits = (text: string) => !!text.trim() && new TextEncoder().encode(voiceClipFilename(text)).length <= 255;

export function fixedSays(source: string): string[] {
  const lines = [...source.matchAll(SAY)].map(([, prefix, quoted]) => unquote(prefix, quoted)).filter((t): t is string => t !== null);
  return [...new Map(lines.map(asSaid).filter(fits).map((t) => [voiceClipFilename(t), t])).values()];
}
