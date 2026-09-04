import { encodeWav } from "./audio";
import { previewPng } from "./photo";
import { generateRowGradient, ASDF_ROW, QWERTY_ROW, ZXCV_ROW } from "./purple/art";
import exported from "./purple/export.json";
import { SAMPLE_PITCHES, voiceClipFilename } from "./purple/sounds";
import { SYNTH_RATE, renderNote } from "./purple/synth";
import { draft, packId, type Draft } from "./state";
import { gzip, tar, type TarEntry } from "./tar";

const enc = new TextEncoder();
const text = (path: string, body: string): TarEntry => ({ path, data: enc.encode(body) });
const json = (path: string, value: unknown) => text(path, JSON.stringify(value, null, 2) + "\n");

// Manifest as purple_tui.pack_manager validates it; `format` is the layout version this pack targets.
export function manifest(d: Draft = draft) {
  return {
    id: packId(d),
    name: d.familyName ? `${d.familyName}${/s$/i.test(d.familyName) ? "'" : "'s"} Purple` : "Our Purple",
    version: "1.0.0",
    type: "emoji",
    format: exported.pack_format,
    description: "Made with Purple Studio.",
  };
}

export function emojiEntries(d: Draft = draft): TarEntry[] {
  const out: TarEntry[] = [];
  if (d.words.length) out.push(json("content/emoji.json", Object.fromEntries(d.words.map((w) => [w.word, w.emoji]))));
  if (d.synonyms.length) out.push(json("content/synonyms.json", Object.fromEntries(d.synonyms.map((s) => [s.alias, s.word]))));
  if (d.ranked.length) out.push(text("content/rankings.txt", d.ranked.join("\n") + "\n"));
  return out;
}

export function themeJson(d: Draft = draft) {
  const t = d.theme!;
  return {
    background: t.background,
    surface: t.surface,
    keys: {
      ...generateRowGradient(t.hues.qwerty, QWERTY_ROW),
      ...generateRowGradient(t.hues.asdf, ASDF_ROW),
      ...generateRowGradient(t.hues.zxcv, ZXCV_ROW),
    },
  };
}

const yieldToUi = () => new Promise((r) => setTimeout(r, 0));

export async function buildEntries(d: Draft = draft, onProgress?: (msg: string) => void): Promise<TarEntry[]> {
  const entries: TarEntry[] = [json("manifest.json", manifest(d)), ...emojiEntries(d)];

  for (const [key, clip] of Object.entries(d.letters)) entries.push({ path: `content/letters/${key}.wav`, data: encodeWav(clip) });
  for (const p of d.phrases) entries.push({ path: `content/voice/${voiceClipFilename(p.text)}`, data: encodeWav(p.clip) });

  for (const pic of d.pictures) {
    onProgress?.(`Saving ${pic.name}`);
    entries.push(json(`content/pictures/${pic.name}.json`, { name: pic.name, ops: pic.ops }));
    entries.push({ path: `content/pictures/${pic.name}.png`, data: await previewPng(pic.cells) });
  }

  for (const inst of d.instruments) {
    entries.push(json(`content/instruments/${inst.name}.json`, { name: inst.name, base: inst.base, params: inst.params }));
    for (const pitch of SAMPLE_PITCHES) {
      onProgress?.(`Rendering ${inst.name}: ${pitch.note}${pitch.octave}`);
      await yieldToUi();
      const samples = renderNote(inst.base, inst.params, pitch.freq);
      entries.push({ path: `content/${inst.name}/${pitch.file}.wav`, data: encodeWav({ samples, rate: SYNTH_RATE }) });
    }
  }

  if (d.theme) entries.push(json("content/theme.json", themeJson(d)));
  return entries;
}

export async function buildPack(onProgress?: (msg: string) => void): Promise<Blob> {
  const entries = await buildEntries(draft, onProgress);
  onProgress?.("Packing");
  return new Blob([(await gzip(tar(entries))) as BlobPart], { type: "application/gzip" });
}

export const packFilename = () => `${packId()}.purplepack`;
