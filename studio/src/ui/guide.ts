// The Room guide: everything a room can do, in plain words, for parents. Written once as data
// and rendered twice, as the page and as the plain text "Copy the guide" puts on the clipboard.
import { PURPLE } from "@sdk";
import { EXAMPLES } from "../examples";
import { h } from "./dom";
import type { View } from "./view";

const [W, H] = PURPLE.room.grid as [number, number];

type Section = { heading: string; text?: string; items?: [string, string][]; code?: { label: string; source: string }[] };

const SECTIONS: Section[] = [
  {
    heading: "What a room is",
    text: "A room is one Python file. It starts with `from purple import *`, and everything in it runs inside a box on Purple: it can ask Purple to show things, say things, and play sounds, and it can't touch anything else on the computer. The top of the file runs once when your kid opens the room. After that, Purple calls `on_key(key)` every time a key is pressed, and runs any timers the room set up. Esc always belongs to Purple, so your kid can always leave.",
  },
  {
    heading: "What a room can call",
    items: [
      ["show(text)", "Big in the middle of the screen, replacing what was there. Emoji look great here."],
      ["write(text)", "A line of text under the middle. The last few lines stay, which is good for stories and questions."],
      ["clear()", "Empties the screen: the middle, the lines, and the grid."],
      ["background(\"#2a1845\")", "Changes the room's color. Use a color written as # and six letters or numbers."],
      ["say(text)", "Purple says it out loud."],
      ["play(\"C4\", \"marimba\")", "Plays a note. Instruments: marimba, ukulele, accordion, glockenspiel, or one you made in this pack."],
      ["drum(\"snare\")", `Plays a drum sound: ${PURPLE.room.drums.join(", ")}.`],
      ["ask(\"Your answer\")", "Waits for your kid to type something and press Enter, then gives back what they typed."],
      [`grid.set(x, y, thing)`, `The screen is also a grid, ${W} squares across and ${H} down, counting from 0 at the top left. A square can hold an emoji, a letter, or a color like "#5ec46a". Going off one edge comes back on the other.`],
      ["grid.get(x, y), grid.erase(x, y), grid.clear()", "Look at a square, empty one, or empty them all. grid.random_empty() picks an empty square."],
      ["every(seconds, fn)", "Calls fn over and over, that many seconds apart. after(seconds, fn) calls it once. Both give back a timer you can .stop()."],
      ["game_over(text)", "Stops the timers and shows text. The next key starts the room over from the top."],
    ],
  },
  {
    heading: "Keys on_key receives",
    text: "A letter, number, or symbol, always lowercase: \"a\", \"7\", \"?\". Or one of these words: " + PURPLE.room.keys.join(", ") + ". Esc never reaches the room.",
  },
  {
    heading: "Two examples",
    code: EXAMPLES.map((e) => ({ label: `${e.label}: ${e.about}`, source: e.source })),
  },
  {
    heading: "Making it feel like Purple",
    items: [
      ["Calm", "Nothing flashing, nothing rushing. Purple is a quiet place."],
      ["Every key does something", "Little kids press everything. Make any key do something pleasant, even if it is just a sound or a color."],
      ["No scores needed", "Playing is the point. Scores, timers, and losing are optional, and usually better left out."],
      ["Pictures over words for little ones", "Kids who don't read yet should be able to enjoy the room without reading. Emoji, sounds, and colors carry it."],
      ["ask() is for older kids", "Typing answers is great for readers. For younger kids, react to single keys with on_key instead."],
    ],
  },
  {
    heading: "If something breaks",
    text: "The preview on the right stops and shows which line of the file the problem is on, with the error Python gave. Fix that line, or press Restart. On Purple, a broken room shows a calm \"this room needs fixing\" card, and the rest of the computer keeps working.",
  },
];

function plainText(): string {
  const out = ["Purple Room guide", ""];
  for (const s of SECTIONS) {
    out.push(s.heading.toUpperCase(), "");
    if (s.text) out.push(s.text, "");
    for (const [a, b] of s.items ?? []) out.push(`- ${a}: ${b}`);
    if (s.items) out.push("");
    for (const c of s.code ?? []) out.push(c.label, "", c.source.trimEnd(), "");
  }
  return out.join("\n");
}

// `code` spans in prose.
function prose(text: string): (Node | string)[] {
  return text.split(/(`[^`]+`)/).map((part) => (part.startsWith("`") ? h("span", { class: "mono" }, part.slice(1, -1)) : part));
}

export function guideView(): View {
  const status = h("span", { class: "dim small" });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(plainText());
      status.textContent = "Copied.";
    } catch {
      status.textContent = "Your browser did not allow copying. Select the page text instead.";
    }
  };
  return {
    title: "Room guide",
    editor: h(
      "section",
      { class: "guide" },
      h("p", { class: "row" }, h("button", { class: "btn small", onclick: copy }, "Copy the guide"), status),
      ...SECTIONS.flatMap((s) => [
        h("h3", {}, s.heading),
        s.text ? h("p", {}, ...prose(s.text)) : null,
        s.items ? h("dl", {}, ...s.items.flatMap(([a, b]) => [h("dt", { class: "mono" }, a), h("dd", {}, b)])) : null,
        ...(s.code ?? []).flatMap((c) => [h("p", { class: "dim small" }, c.label), h("pre", {}, c.source.trimEnd())]),
      ]),
    ),
    stage: () => null,
  };
}
