// Purple's keyboard stickers (cards/make_keyboard_sticker_sheet.py): a purple ring, the key's
// color inside, its letter on top in whichever of black or white reads better. Drawn the same on
// the pretend laptop, the Voice key picker, and the Colors page, in the family's colors when the
// draft has some.
import { KEY_COLORS, contrast, rowColors } from "@sdk";
import { draft } from "../state";
import { h } from "./dom";

const SHIFT: Record<string, string> = { "1": "!", "2": "@", "3": "#", "4": "$", "5": "%", "6": "^", "7": "&", "8": "×", "9": "(", "0": ")", ";": ":", "'": '"', "/": "?" };
const LABEL: Record<string, string> = { "=": "+", "/": "÷" };

export const PURPLE_STICKERS = KEY_COLORS;
export const keyLabel = (key: string) => LABEL[key] ?? key.toUpperCase();

export function stickerColors(): Record<string, string> {
  return draft.theme ? { ...KEY_COLORS, ...rowColors(draft.theme.hues) } : KEY_COLORS;
}

export const ink = (bg: string) => (contrast(bg, "#ffffff") >= contrast(bg, "#000000") ? "#ffffff" : "#000000");

export function sticker(key: string, colors = stickerColors()): HTMLElement {
  const bg = colors[key] ?? "#aaaaaa";
  const shift = SHIFT[key];
  return h("span", { class: "sticker", style: `--key:${bg};--ink:${ink(bg)}` },
    shift ? h("small", {}, shift) : null,
    h("b", {}, keyLabel(key)));
}

export const hasSticker = (key: string) => key in KEY_COLORS;
