// Emoji in the purple sticker sheet's shades (cards/make_studio_icons.py), for the ones Studio has
// drawn that way; a key shows as its keyboard sticker; any other emoji shows as itself.
import { h } from "./dom";
import { PURPLE_STICKERS, hasSticker, sticker } from "./stickers";

const ICONS = import.meta.glob<string>("../icons/*.svg", { eager: true, query: "?url", import: "default" });
const code = (emoji: string) => [...emoji].filter((c) => c !== "️").map((c) => c.codePointAt(0)!.toString(16)).join("-");

export function purpleEmoji(emoji: string, cls = ""): HTMLElement {
  if (hasSticker(emoji)) { const el = sticker(emoji, PURPLE_STICKERS); el.classList.add(...cls.split(" ").filter(Boolean)); return el; }
  const src = ICONS[`../icons/${code(emoji)}.svg`];
  return src ? h("img", { class: `purple-emoji ${cls}`, src, alt: "" }) : h("span", { class: cls }, emoji);
}
