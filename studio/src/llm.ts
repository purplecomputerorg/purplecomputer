// The one thing in Studio that talks to the internet, and only when a parent pastes their own
// key and presses a button: a direct call from the browser to the Claude API. Nothing about the
// family is sent except the description typed into the box. Purple itself never touches this.
import { PURPLE } from "@sdk";

export const MODEL = "claude-sonnet-5";
const KEY_STORAGE = "purple-studio-claude-key";

export function loadKey(): string {
  try { return localStorage.getItem(KEY_STORAGE) ?? ""; } catch { return ""; }
}

export function storeKey(key: string | null): void {
  try { key ? localStorage.setItem(KEY_STORAGE, key) : localStorage.removeItem(KEY_STORAGE); } catch { /* private window */ }
}

export async function ask(key: string, system: string, user: string): Promise<string> {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
    },
    body: JSON.stringify({ model: MODEL, max_tokens: 4000, system, messages: [{ role: "user", content: user }] }),
  });
  if (!res.ok) throw new Error(`The API said ${res.status}: ${(await res.text()).slice(0, 300)}`);
  const data = await res.json();
  return (data.content ?? []).filter((c: { type: string }) => c.type === "text").map((c: { text: string }) => c.text).join("");
}

export function extractJson(text: string): unknown {
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(text);
  const body = fenced ? fenced[1] : text;
  const start = body.search(/[[{]/);
  return JSON.parse(body.slice(start));
}

export const WORDS_SYSTEM = `You help a parent add words to their child's Purple Computer, an offline computer for kids aged 3 to 10 where typing a word shows its emoji.
Reply with JSON only: {"words": [{"word": "...", "emoji": "..."}], "synonyms": [{"alias": "...", "word": "..."}]}.
Words are lowercase, one or two words, things a kid would type. Each emoji is a single emoji character. Synonyms are nicknames or misspellings that should show the same emoji as "word". Give 8 to 20 words. No commentary.`;

export const ROOM_SYSTEM = `You write a room for Purple Computer, an offline keyboard-only computer for kids aged 3 to 10. A room is a JSON program that Purple interprets; nothing else runs. Reply with the JSON program only, no commentary, no code fences.

Format (version ${PURPLE.room.format}):
{"name": "<lowercase-dashes>", "title": "<Short Title>", "background": "#rrggbb" (optional), "rules": [{"when": EVENT, "do": [ACTION, ...]}, ...]}

EVENT: {"event": "start"} | {"event": "key", "key": "<one character or one of ${PURPLE.room.special_keys.join(", ")}>"} | {"event": "any_key"} | {"event": "every", "seconds": <0.5 to 60>}

ACTION:
{"do": "show", "text": VALUE}   big in the middle of the screen, replaces what was there (emoji work well)
{"do": "add", "text": VALUE}    appends to a line that fills up
{"do": "say", "text": VALUE}    Purple speaks it
{"do": "play", "note": VALUE, "instrument": "marimba"|"ukulele"|"accordion"|"glockenspiel"}   note like "C4", "F#3"; C1 to D7
{"do": "drum", "name": one of ${PURPLE.room.drums.join(", ")}}
{"do": "clear"}
{"do": "background", "color": "#rrggbb"}
{"do": "wait", "seconds": VALUE}   at most ${PURPLE.room.limits.wait_seconds}
{"do": "set", "var": "<name>", "value": VALUE}
{"do": "change", "var": "<name>", "by": VALUE}
{"do": "if", "test": TEST, "then": [ACTION...], "else": [ACTION...]}
{"do": "repeat", "times": VALUE, "body": [ACTION...]}

VALUE: a number | a string | {"var": "<name>"} | {"key": true} (the key just pressed) | {"pick": [VALUE...]} (one at random) | {"join": [VALUE...]} | {"random": {"from": VALUE, "to": VALUE}} | {"math": "+"|"-"|"*"|"/", "a": VALUE, "b": VALUE}
TEST: {"compare": "="|"!="|"<"|">", "a": VALUE, "b": VALUE} | {"and": [TEST...]} | {"or": [TEST...]} | {"not": TEST}

Design rules: calm, no scores or rewards, no losing, nothing that needs reading to enjoy. Every key a kid might press should do something pleasant (use any_key). Keep it under 12 rules. Prefer emoji, single spoken words, and notes.

Example:
${JSON.stringify({ name: "farm", title: "Farm", rules: [
  { when: { event: "start" }, do: [{ do: "show", text: "🐄 🐖 🐑" }, { do: "say", text: "farm" }] },
  { when: { event: "key", key: "c" }, do: [{ do: "show", text: "🐄" }, { do: "say", text: "cow" }, { do: "play", note: "C4", instrument: "marimba" }] },
  { when: { event: "key", key: "p" }, do: [{ do: "show", text: "🐖" }, { do: "say", text: "pig" }, { do: "play", note: "E4", instrument: "marimba" }] },
  { when: { event: "any_key" }, do: [{ do: "add", text: { pick: ["🌾", "🌻", "🐝"] } }, { do: "drum", name: "woodblock" }] },
] })}`;
